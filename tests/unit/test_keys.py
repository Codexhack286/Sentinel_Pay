"""
Tests for the shared verifier identity (sentinelpay/keys.py).

The bug these guard against: every process used to mint its own ephemeral
Ed25519 key, so an attestation signed by the verifier service could never be
validated by the resource server, and a restart silently invalidated every
outstanding attestation.
"""

import pytest

from sentinelpay import keys
from sentinelpay.verifier.attestation import Attestation, AttestationSigner


@pytest.fixture
def configured_key(monkeypatch):
    signer = AttestationSigner()
    monkeypatch.setattr(keys.settings, "VERIFIER_PRIVATE_KEY", signer.private_key_b64)
    monkeypatch.setattr(keys.settings, "VERIFIER_PUBLIC_KEY", signer.public_key_b64)
    return signer


def test_configured_key_round_trips(configured_key):
    assert keys.load_signer().public_key_b64 == configured_key.public_key_b64


def test_two_independent_loads_produce_the_same_identity(configured_key):
    """Two processes reading the same .env must be able to verify each other."""
    issuer = keys.load_signer()
    checker_public_key = keys.configured_public_key()

    attestation = issuer.sign(
        Attestation(
            intent_hash="hash",
            agent_id="agent-1",
            policy_id="policy-1",
            tool_name="paid_research",
            destination="MERCHANT_ADDR",
            amount=1000,
            currency="uALGO",
        )
    )

    assert AttestationSigner.verify_attestation(attestation, checker_public_key) is True


def test_unpadded_base64_from_env_still_loads(monkeypatch, configured_key):
    # Some .env parsers and shells strip trailing '=' padding.
    monkeypatch.setattr(
        keys.settings, "VERIFIER_PRIVATE_KEY", configured_key.private_key_b64.rstrip("=")
    )
    assert keys.load_signer().public_key_b64 == configured_key.public_key_b64


def test_missing_key_warns_but_still_works_offline(monkeypatch):
    monkeypatch.setattr(keys.settings, "VERIFIER_PRIVATE_KEY", None)
    with pytest.warns(RuntimeWarning, match="ephemeral"):
        assert keys.load_signer().public_key_b64


def test_missing_key_is_fatal_when_required(monkeypatch):
    """On-chain paths must never sign with a key the contract does not know."""
    monkeypatch.setattr(keys.settings, "VERIFIER_PRIVATE_KEY", None)
    with pytest.raises(RuntimeError, match="VERIFIER_PRIVATE_KEY"):
        keys.load_signer(required=True)


def test_wrong_length_key_is_rejected(monkeypatch):
    monkeypatch.setattr(keys.settings, "VERIFIER_PRIVATE_KEY", "dG9vLXNob3J0")
    with pytest.raises(ValueError, match="32-byte"):
        keys.load_signer()
