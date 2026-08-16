"""Unit tests for the SentinelPay contract reference model and atomic group rules.

The cases below are the on-chain half of the required test matrix in
SentinelPay_Final_Project_Review.md section 11. They deliberately assume a fully
compromised client: the attacker holds a genuine signed attestation and builds
whatever group they like. The invariant under test is that none of those groups
validates.
"""

import base64
import time

import pytest
from algosdk.encoding import encode_address
from cryptography.hazmat.primitives.asymmetric import ed25519

from contracts.reference_model import (
    ContractState,
    SentinelPayContractLogic,
    parse_avm_blob,
)
from sentinelpay.verifier.attestation import (
    AVM_OFFSET_AMOUNT,
    AVM_OFFSET_DESTINATION,
    Attestation,
    AttestationSigner,
)

MERCHANT_ADDRESS = encode_address(bytes([0x11] * 32))
ATTACKER_ADDRESS = encode_address(bytes([0xA7] * 32))
ADMIN_ADDRESS = encode_address(bytes([0x22] * 32))

MERCHANT_PUBKEY = bytes([0x11] * 32)
ATTACKER_PUBKEY = bytes([0xA7] * 32)


@pytest.fixture
def signer():
    return AttestationSigner()


@pytest.fixture
def contract_state(signer):
    return ContractState(
        admin_address=ADMIN_ADDRESS,
        verifier_public_key_b64=signer.public_key_b64,
        max_daily_spend=1_000_000,  # 1.0 ALGO
    )


@pytest.fixture
def logic(contract_state):
    return SentinelPayContractLogic(contract_state)


def make_attestation(signer, **overrides) -> Attestation:
    fields = dict(
        intent_hash="abc123hash",
        agent_id="agent-1",
        policy_id="p1",
        tool_name="paid_research",
        destination=MERCHANT_ADDRESS,
        amount=100_000,
        currency="uALGO",
        expires_at=int(time.time()) + 300,
    )
    fields.update(overrides)
    return signer.sign(Attestation(**fields))


def app_call(attestation: Attestation, *, blob=None, signature_b64=None) -> dict:
    return {
        "args": [
            "validate_and_pay",
            blob if blob is not None else attestation.avm_signing_bytes(),
            signature_b64 if signature_b64 is not None else attestation.avm_signature,
        ]
    }


def payment(receiver: bytes = MERCHANT_PUBKEY, amount: int = 100_000, **extra) -> dict:
    return {"type": "pay", "receiver": receiver, "amount": amount, **extra}


def splice(blob: bytes, offset: int, replacement: bytes) -> bytes:
    return blob[:offset] + replacement + blob[offset + len(replacement) :]


# --- blob layout ---------------------------------------------------------------

def test_blob_round_trips_through_the_parser(signer):
    attestation = make_attestation(signer)
    parsed = parse_avm_blob(attestation.avm_signing_bytes())

    assert parsed.destination == MERCHANT_PUBKEY
    assert parsed.amount == attestation.amount
    assert parsed.nonce == attestation.nonce_bytes()
    assert parsed.expires_at == attestation.expires_at


def test_blob_with_wrong_length_is_rejected(signer, logic):
    attestation = make_attestation(signer)
    truncated = attestation.avm_signing_bytes()[:-1]

    ok, msg = logic.validate_atomic_group(payment(), app_call(attestation, blob=truncated))
    assert ok is False
    assert "Malformed authorization blob" in msg


def test_blob_with_wrong_magic_is_rejected(signer, logic):
    attestation = make_attestation(signer)
    swapped = splice(attestation.avm_signing_bytes(), 0, b"NOTSPAY!")

    ok, msg = logic.validate_atomic_group(payment(), app_call(attestation, blob=swapped))
    assert ok is False
    assert "magic" in msg


# --- happy path ----------------------------------------------------------------

def test_valid_atomic_group(signer, logic, contract_state):
    attestation = make_attestation(signer)

    ok, msg = logic.validate_atomic_group(payment(), app_call(attestation))

    assert ok is True
    assert "validated successfully" in msg
    assert attestation.nonce_bytes() in contract_state.consumed_nonces
    assert contract_state.current_daily_spend == 100_000


# --- the substitution attacks the old unbound-argument design allowed ----------

def test_amount_substitution_is_rejected(signer, logic):
    """A genuine 100k authorization must not settle a 900k payment."""
    attestation = make_attestation(signer)

    ok, msg = logic.validate_atomic_group(payment(amount=900_000), app_call(attestation))

    assert ok is False
    assert "Amount mismatch" in msg


def test_destination_substitution_is_rejected(signer, logic):
    attestation = make_attestation(signer)

    ok, msg = logic.validate_atomic_group(
        payment(receiver=ATTACKER_PUBKEY), app_call(attestation)
    )

    assert ok is False
    assert "Destination mismatch" in msg


def test_tampering_the_blob_to_match_the_attack_breaks_the_signature(signer, logic):
    """Editing the signed bytes so they agree with the attacker's payment fails.

    This is the case the previous design could not catch: destination and amount
    used to arrive as unsigned side arguments, so rewriting them cost the
    attacker nothing. Now they live inside the signed blob.
    """
    attestation = make_attestation(signer)
    tampered = splice(
        splice(attestation.avm_signing_bytes(), AVM_OFFSET_DESTINATION, ATTACKER_PUBKEY),
        AVM_OFFSET_AMOUNT,
        (900_000).to_bytes(8, "big"),
    )

    ok, msg = logic.validate_atomic_group(
        payment(receiver=ATTACKER_PUBKEY, amount=900_000),
        app_call(attestation, blob=tampered),
    )

    assert ok is False
    assert "signature verification failed" in msg


def test_forged_signature_from_another_key_is_rejected(signer, logic):
    attestation = make_attestation(signer)
    rogue = ed25519.Ed25519PrivateKey.generate()
    forged = base64.b64encode(rogue.sign(attestation.avm_signing_bytes())).decode()

    ok, msg = logic.validate_atomic_group(
        payment(), app_call(attestation, signature_b64=forged)
    )

    assert ok is False
    assert "signature verification failed" in msg


# --- replay, expiry, caps, group shape -----------------------------------------

def test_replay_rejection(signer, logic):
    attestation = make_attestation(signer)

    ok1, _ = logic.validate_atomic_group(payment(), app_call(attestation))
    ok2, msg2 = logic.validate_atomic_group(payment(), app_call(attestation))

    assert ok1 is True
    assert ok2 is False
    assert "Replay rejected" in msg2


def test_expired_authorization_is_rejected(signer, logic):
    attestation = make_attestation(signer, expires_at=int(time.time()) - 1)

    ok, msg = logic.validate_atomic_group(payment(), app_call(attestation))

    assert ok is False
    assert "expired" in msg


def test_cumulative_spend_cap_is_enforced(signer, logic, contract_state):
    contract_state.current_daily_spend = 950_000  # cap is 1_000_000
    attestation = make_attestation(signer)

    ok, msg = logic.validate_atomic_group(payment(), app_call(attestation))

    assert ok is False
    assert "Spend cap exceeded" in msg


def test_group_without_the_payment_leg_is_rejected(signer, logic):
    attestation = make_attestation(signer)

    ok, msg = logic.validate_atomic_group(payment(), app_call(attestation), group_size=1)

    assert ok is False
    assert "Group size" in msg


def test_payment_that_closes_out_the_sender_is_rejected(signer, logic):
    """An amount-only check would approve this and let the account be drained."""
    attestation = make_attestation(signer)

    ok, msg = logic.validate_atomic_group(
        payment(close_remainder_to=ATTACKER_PUBKEY), app_call(attestation)
    )

    assert ok is False
    assert "closes out" in msg


def test_payment_that_rekeys_the_sender_is_rejected(signer, logic):
    attestation = make_attestation(signer)

    ok, msg = logic.validate_atomic_group(
        payment(rekey_to=ATTACKER_PUBKEY), app_call(attestation)
    )

    assert ok is False
    assert "rekeys" in msg


def test_wrong_selector_is_rejected(signer, logic):
    attestation = make_attestation(signer)
    call = app_call(attestation)
    call["args"][0] = "drain_everything"

    ok, msg = logic.validate_atomic_group(payment(), call)

    assert ok is False
    assert "Invalid app call selector" in msg


# --- admin ---------------------------------------------------------------------

def test_only_admin_can_reset_the_spend_counter(logic, contract_state):
    contract_state.current_daily_spend = 500_000

    denied, _ = logic.admin_reset_spend(sender=ATTACKER_ADDRESS)
    assert denied is False
    assert contract_state.current_daily_spend == 500_000

    allowed, _ = logic.admin_reset_spend(sender=ADMIN_ADDRESS)
    assert allowed is True
    assert contract_state.current_daily_spend == 0
