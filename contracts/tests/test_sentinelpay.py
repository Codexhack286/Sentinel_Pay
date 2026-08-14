"""Unit tests for SentinelPay smart contract logic and atomic group rules."""

import pytest
from sentinelpay.verifier.attestation import Attestation, AttestationSigner
from contracts.sentinelpay import SentinelPayContractLogic, ContractState


@pytest.fixture
def signer():
    return AttestationSigner()


@pytest.fixture
def contract_state(signer):
    return ContractState(
        admin_address="ADMIN_ADDR_AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA",
        verifier_public_key_b64=signer.public_key_b64,
        max_daily_spend=1000000,  # 1.0 ALGO
    )


def test_valid_atomic_group(signer, contract_state):
    logic = SentinelPayContractLogic(contract_state)
    attestation = Attestation(
        intent_hash="abc123hash",
        agent_id="agent-1",
        policy_id="p1",
        tool_name="paid_tool",
        destination="MERCHANT_ADDR_AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA",
        amount=100000,
        currency="uALGO",
        nonce="nonce-001",
    )
    signed_attestation = signer.sign(attestation)

    payment_tx = {
        "receiver": "MERCHANT_ADDR_AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA",
        "amount": 100000,
    }
    app_call_tx = {"args": ["validate_and_pay"]}
    payload = {
        "signing_bytes": signed_attestation.signing_bytes(),
        "destination": signed_attestation.destination,
        "amount": signed_attestation.amount,
        "nonce": signed_attestation.nonce,
    }

    ok, msg = logic.validate_atomic_group(
        payment_tx=payment_tx,
        app_call_tx=app_call_tx,
        attestation_payload=payload,
        attestation_signature_b64=signed_attestation.signature,
    )
    assert ok is True
    assert "validated successfully" in msg
    assert "nonce-001" in contract_state.consumed_nonces


def test_replay_rejection(signer, contract_state):
    logic = SentinelPayContractLogic(contract_state)
    attestation = Attestation(
        intent_hash="abc123hash",
        agent_id="agent-1",
        policy_id="p1",
        tool_name="paid_tool",
        destination="MERCHANT_ADDR_AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA",
        amount=100000,
        currency="uALGO",
        nonce="nonce-replay-001",
    )
    signed_attestation = signer.sign(attestation)

    payment_tx = {"receiver": "MERCHANT_ADDR_AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA", "amount": 100000}
    app_call_tx = {"args": ["validate_and_pay"]}
    payload = {
        "signing_bytes": signed_attestation.signing_bytes(),
        "destination": signed_attestation.destination,
        "amount": signed_attestation.amount,
        "nonce": signed_attestation.nonce,
    }

    # 1st payment passes
    ok1, _ = logic.validate_atomic_group(payment_tx, app_call_tx, payload, signed_attestation.signature)
    assert ok1 is True

    # 2nd payment with same attestation/nonce fails
    ok2, msg2 = logic.validate_atomic_group(payment_tx, app_call_tx, payload, signed_attestation.signature)
    assert ok2 is False
    assert "Replay rejected" in msg2


def test_destination_tamper_rejection(signer, contract_state):
    logic = SentinelPayContractLogic(contract_state)
    attestation = Attestation(
        intent_hash="abc123hash",
        agent_id="agent-1",
        policy_id="p1",
        tool_name="paid_tool",
        destination="LEGITIMATE_MERCHANT_ADDR",
        amount=100000,
        currency="uALGO",
        nonce="nonce-tamper-001",
    )
    signed = signer.sign(attestation)

    # Attacker tries to divert funds to attacker address
    payment_tx = {"receiver": "ATTACKER_ADDR", "amount": 100000}
    app_call_tx = {"args": ["validate_and_pay"]}
    payload = {
        "signing_bytes": signed.signing_bytes(),
        "destination": signed.destination,
        "amount": signed.amount,
        "nonce": signed.nonce,
    }

    ok, msg = logic.validate_atomic_group(payment_tx, app_call_tx, payload, signed.signature)
    assert ok is False
    assert "Destination mismatch" in msg
