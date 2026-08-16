"""
Tests for on-chain settlement verification (sentinelpay/payments/settlement.py).

The gap this closes: the resource server used to accept a signed attestation as
proof of payment. A signature only proves an authorization was *issued*. These
tests pin the three outcomes that matter — settled, not settled, and unknown —
and specifically that "unknown" fails closed.

A fake ChainReader keeps the suite offline.
"""

import pytest

from sentinelpay.payments.settlement import (
    ChainUnavailable,
    _is_not_found,
    verify_settled_on_chain,
)
from sentinelpay.verifier.attestation import Attestation, AttestationSigner

APP_ID = 769368669


class FakeChain:
    def __init__(self, consumed=(), raises: bool = False):
        self.consumed = set(consumed)
        self.raises = raises
        self.calls = []

    def nonce_consumed(self, app_id: int, nonce: bytes) -> bool:
        self.calls.append((app_id, nonce))
        if self.raises:
            raise ChainUnavailable("algod unreachable")
        return nonce in self.consumed


@pytest.fixture
def attestation():
    return AttestationSigner().sign(
        Attestation(
            intent_hash="c" * 64,
            agent_id="agent-1",
            policy_id="policy-1",
            tool_name="paid_research",
            destination="MERCHANT_ADDR",
            amount=100_000,
            currency="uALGO",
        )
    )


def test_consumed_nonce_proves_settlement(attestation):
    chain = FakeChain(consumed=[attestation.nonce_bytes()])

    ok, reason = verify_settled_on_chain(attestation, APP_ID, chain)

    assert ok is True
    assert "confirmed on-chain" in reason
    assert chain.calls == [(APP_ID, attestation.nonce_bytes())]


def test_missing_box_means_the_payment_never_settled(attestation):
    """A bare payment writes no box, so it lands here."""
    ok, reason = verify_settled_on_chain(attestation, APP_ID, FakeChain())

    assert ok is False
    assert "never settled" in reason or "without the required" in reason


def test_unreachable_chain_fails_closed(attestation):
    """An outage must not become an open door."""
    ok, reason = verify_settled_on_chain(attestation, APP_ID, FakeChain(raises=True))

    assert ok is False
    assert "refusing to serve" in reason


def test_missing_app_id_fails_closed_when_required(attestation):
    ok, reason = verify_settled_on_chain(attestation, 0, FakeChain())

    assert ok is False
    assert "SENTINELPAY_APP_ID" in reason


def test_missing_chain_reader_fails_closed_when_required(attestation):
    ok, reason = verify_settled_on_chain(attestation, APP_ID, None)

    assert ok is False
    assert "chain reader" in reason


def test_skipped_check_says_so_rather_than_claiming_success(attestation):
    """Offline mode must be legible, not silently indistinguishable from a pass."""
    ok, reason = verify_settled_on_chain(attestation, 0, None, required=False)

    assert ok is True
    assert "skipped" in reason.lower()


@pytest.mark.parametrize(
    "message, expected",
    [
        ("box not found", True),
        ("404 Client Error", True),
        ("no such box", True),
        ("connection refused", False),
        ("500 internal server error", False),
        ("timed out", False),
    ],
)
def test_not_found_detection_distinguishes_absence_from_outage(message, expected):
    """Misreading an outage as absence is the dangerous direction."""
    assert _is_not_found(Exception(message)) is expected
