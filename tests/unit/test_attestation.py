"""Unit tests for Attestation signing and cryptographic verification."""

from sentinelpay.verifier.attestation import Attestation, AttestationSigner


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
