"""Unit tests for Attestation signing and cryptographic verification."""

import time

import pytest
from algosdk.encoding import decode_address, encode_address

from sentinelpay.verifier.attestation import (
    AVM_BLOB_LEN,
    AVM_MAGIC,
    AVM_OFFSET_AMOUNT,
    AVM_OFFSET_DESTINATION,
    AVM_OFFSET_EXPIRES_AT,
    AVM_OFFSET_NONCE,
    Attestation,
    AttestationSigner,
    to_32_bytes,
)

REAL_ADDRESS = encode_address(bytes([0x11] * 32))


def test_attestation_signing_and_verification():
    signer = AttestationSigner()
    attestation = Attestation(
        intent_hash="112233445566778899aabbccddeeff00112233445566778899aabbccddeeff00",
        agent_id="agent-01",
        policy_id="policy-01",
        tool_name="paid_tool",
        destination="MERCHANT_ADDRESS_123",
        amount=100000,
        currency="uALGO",
    )

    signed = signer.sign(attestation)
    assert len(signed.signature) > 0

    is_valid = AttestationSigner.verify_attestation(signed, signer.public_key_b64)
    assert is_valid is True


def test_attestation_tampering_detection():
    signer = AttestationSigner()
    attestation = Attestation(
        intent_hash="112233445566778899aabbccddeeff00112233445566778899aabbccddeeff00",
        agent_id="agent-01",
        policy_id="policy-01",
        tool_name="paid_tool",
        destination="MERCHANT_ADDRESS_123",
        amount=100000,
        currency="uALGO",
    )

    signed = signer.sign(attestation)

    # Tamper with amount
    signed.amount = 999999
    is_valid = AttestationSigner.verify_attestation(signed, signer.public_key_b64)
    assert is_valid is False


# --- AVM blob: the bytes the Algorand contract actually verifies ---------------


def avm_attestation(signer: AttestationSigner, **overrides) -> Attestation:
    fields = dict(
        intent_hash="a" * 64,
        agent_id="agent-01",
        policy_id="policy-01",
        tool_name="paid_research",
        destination=REAL_ADDRESS,
        amount=100_000,
        currency="uALGO",
        expires_at=int(time.time()) + 300,
    )
    fields.update(overrides)
    return signer.sign(Attestation(**fields))


def test_avm_blob_has_the_layout_the_contract_parses():
    attestation = avm_attestation(AttestationSigner())
    blob = attestation.avm_signing_bytes()

    assert len(blob) == AVM_BLOB_LEN
    assert blob[: len(AVM_MAGIC)] == AVM_MAGIC
    assert blob[AVM_OFFSET_DESTINATION : AVM_OFFSET_DESTINATION + 32] == decode_address(REAL_ADDRESS)
    assert int.from_bytes(blob[AVM_OFFSET_AMOUNT : AVM_OFFSET_AMOUNT + 8], "big") == 100_000
    assert blob[AVM_OFFSET_NONCE : AVM_OFFSET_NONCE + 32] == attestation.nonce_bytes()
    assert (
        int.from_bytes(blob[AVM_OFFSET_EXPIRES_AT : AVM_OFFSET_EXPIRES_AT + 8], "big")
        == attestation.expires_at
    )


def test_avm_signature_verifies_against_the_verifier_key():
    signer = AttestationSigner()
    attestation = avm_attestation(signer)

    assert attestation.avm_signature != ""
    assert AttestationSigner.verify_avm_attestation(attestation, signer.public_key_b64) is True


def test_avm_signature_does_not_verify_under_another_key():
    attestation = avm_attestation(AttestationSigner())

    assert (
        AttestationSigner.verify_avm_attestation(
            attestation, AttestationSigner().public_key_b64
        )
        is False
    )


def test_changing_the_amount_invalidates_the_avm_signature():
    """The binding that makes on-chain enforcement meaningful."""
    signer = AttestationSigner()
    attestation = avm_attestation(signer)

    attestation.amount = 900_000

    assert AttestationSigner.verify_avm_attestation(attestation, signer.public_key_b64) is False


def test_changing_the_destination_invalidates_the_avm_signature():
    signer = AttestationSigner()
    attestation = avm_attestation(signer)

    attestation.destination = encode_address(bytes([0xA7] * 32))

    assert AttestationSigner.verify_avm_attestation(attestation, signer.public_key_b64) is False


def test_placeholder_destination_gets_no_avm_signature():
    """Off-chain demo attestations must not look settleable."""
    signer = AttestationSigner()
    attestation = signer.sign(
        Attestation(
            intent_hash="hash",
            agent_id="a",
            policy_id="p",
            tool_name="t",
            destination="NOT_AN_ALGORAND_ADDRESS",
            amount=1,
            currency="uALGO",
        )
    )

    assert attestation.signature != ""
    assert attestation.avm_signature == ""
    with pytest.raises(ValueError):
        attestation.avm_signing_bytes()


def test_nonce_bytes_are_always_32_bytes():
    assert len(Attestation.model_construct(nonce="short").nonce_bytes()) == 32
    assert len(to_32_bytes("f" * 64)) == 32
    assert to_32_bytes("f" * 64) == bytes.fromhex("f" * 64)


def test_expiry_helper_tracks_the_clock():
    now = int(time.time())
    assert Attestation.model_construct(expires_at=now + 10).is_expired(now) is False
    assert Attestation.model_construct(expires_at=now).is_expired(now) is True
