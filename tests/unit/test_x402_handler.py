"""
Direct unit tests for X402PaymentHandler (sentinelpay/payments/x402.py).

The integration test (tests/integration/test_payment_flow.py) only exercises
the happy path end-to-end. These tests isolate parse_402_response,
construct_settlement_proof, and the individual rejection branches of
verify_settlement_proof (bad scheme, replay, destination/amount/currency
mismatch, signature tamper) that weren't covered anywhere else.
"""

import time

import pytest

from sentinelpay.payments.requests import PaymentRequirement
from sentinelpay.payments.x402 import X402PaymentHandler
from sentinelpay.verifier.attestation import Attestation, AttestationSigner


@pytest.fixture
def signer():
    return AttestationSigner()


@pytest.fixture
def requirement():
    return PaymentRequirement(
        scheme="algorand",
        network="testnet",
        asset="uALGO",
        amount=100000,
        pay_to="MERCHANT_ADDR_AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA",
        resource_id="dataset-1",
    )


def signed_attestation(signer, requirement, **overrides):
    fields = dict(
        intent_hash="hash123",
        agent_id="agent-1",
        policy_id="policy-1",
        tool_name="paid_research",
        destination=requirement.pay_to,
        amount=requirement.amount,
        currency=requirement.asset,
    )
    fields.update(overrides)
    return signer.sign(Attestation(**fields))


# --- parse_402_response ---

def test_parse_402_response_from_json_body_payment_requirements():
    body = {
        "payment_requirements": {
            "amount": 5000,
            "pay_to": "ADDR",
            "resource_id": "res-1",
        }
    }
    req = X402PaymentHandler.parse_402_response(headers={}, body=body)
    assert req is not None
    assert req.amount == 5000
    assert req.pay_to == "ADDR"


def test_parse_402_response_falls_back_to_flat_body():
    body = {"amount": 7000, "pay_to": "ADDR2", "resource_id": "res-2"}
    req = X402PaymentHandler.parse_402_response(headers={}, body=body)
    assert req is not None
    assert req.amount == 7000


def test_parse_402_response_returns_none_when_no_data():
    req = X402PaymentHandler.parse_402_response(headers={}, body=None)
    assert req is None


# --- construct_settlement_proof ---

def test_construct_settlement_proof_has_correct_scheme_prefix(signer, requirement):
    attestation = signed_attestation(signer, requirement)
    header = X402PaymentHandler.construct_settlement_proof(
        attestation=attestation, tx_id="tx1", group_id="group1"
    )
    assert header.startswith("SentinelPay-AVM ")


def test_construct_settlement_proof_accepts_dict_or_model(signer, requirement):
    attestation = signed_attestation(signer, requirement)
    header_from_model = X402PaymentHandler.construct_settlement_proof(
        attestation=attestation, tx_id="tx1", group_id="group1"
    )
    header_from_dict = X402PaymentHandler.construct_settlement_proof(
        attestation=attestation.model_dump(), tx_id="tx1", group_id="group1"
    )
    assert header_from_model.startswith("SentinelPay-AVM ")
    assert header_from_dict.startswith("SentinelPay-AVM ")


# --- verify_settlement_proof: happy path ---

def test_verify_settlement_proof_accepts_valid_proof(signer, requirement):
    attestation = signed_attestation(signer, requirement)
    header = X402PaymentHandler.construct_settlement_proof(attestation, "tx1", "group1")

    valid, reason, returned_attestation = X402PaymentHandler.verify_settlement_proof(
        payment_proof_header=header,
        expected_requirement=requirement,
        verifier_public_key=signer.public_key_b64,
        consumed_nonces=set(),
    )
    assert valid is True
    assert returned_attestation.attestation_id == attestation.attestation_id


# --- verify_settlement_proof: rejection branches ---

def test_verify_settlement_proof_rejects_wrong_scheme(requirement, signer):
    valid, reason, attestation = X402PaymentHandler.verify_settlement_proof(
        payment_proof_header="Bearer sometoken",
        expected_requirement=requirement,
        verifier_public_key=signer.public_key_b64,
        consumed_nonces=set(),
    )
    assert valid is False
    assert "SentinelPay-AVM" in reason
    assert attestation is None


def test_verify_settlement_proof_rejects_replayed_nonce(signer, requirement):
    attestation = signed_attestation(signer, requirement)
    header = X402PaymentHandler.construct_settlement_proof(attestation, "tx1", "group1")

    valid, reason, _ = X402PaymentHandler.verify_settlement_proof(
        payment_proof_header=header,
        expected_requirement=requirement,
        verifier_public_key=signer.public_key_b64,
        consumed_nonces={attestation.nonce},  # already consumed
    )
    assert valid is False
    assert "replay" in reason.lower()


def test_verify_settlement_proof_rejects_destination_mismatch(signer, requirement):
    attestation = signed_attestation(signer, requirement, destination="OTHER_ADDR")
    header = X402PaymentHandler.construct_settlement_proof(attestation, "tx1", "group1")

    valid, reason, _ = X402PaymentHandler.verify_settlement_proof(
        payment_proof_header=header,
        expected_requirement=requirement,
        verifier_public_key=signer.public_key_b64,
        consumed_nonces=set(),
    )
    assert valid is False
    assert "destination" in reason.lower()


def test_verify_settlement_proof_rejects_amount_mismatch(signer, requirement):
    attestation = signed_attestation(signer, requirement, amount=1)
    header = X402PaymentHandler.construct_settlement_proof(attestation, "tx1", "group1")

    valid, reason, _ = X402PaymentHandler.verify_settlement_proof(
        payment_proof_header=header,
        expected_requirement=requirement,
        verifier_public_key=signer.public_key_b64,
        consumed_nonces=set(),
    )
    assert valid is False
    assert "amount" in reason.lower()


def test_verify_settlement_proof_rejects_currency_mismatch(signer, requirement):
    attestation = signed_attestation(signer, requirement, currency="USDC")
    header = X402PaymentHandler.construct_settlement_proof(attestation, "tx1", "group1")

    valid, reason, _ = X402PaymentHandler.verify_settlement_proof(
        payment_proof_header=header,
        expected_requirement=requirement,
        verifier_public_key=signer.public_key_b64,
        consumed_nonces=set(),
    )
    assert valid is False
    assert "asset" in reason.lower()


def test_verify_settlement_proof_rejects_bad_signature(signer, requirement):
    attestation = signed_attestation(signer, requirement)
    header = X402PaymentHandler.construct_settlement_proof(attestation, "tx1", "group1")

    wrong_signer = AttestationSigner()  # different keypair
    valid, reason, _ = X402PaymentHandler.verify_settlement_proof(
        payment_proof_header=header,
        expected_requirement=requirement,
        verifier_public_key=wrong_signer.public_key_b64,  # mismatched key
        consumed_nonces=set(),
    )
    assert valid is False
    assert "signature" in reason.lower()


def test_verify_settlement_proof_rejects_malformed_base64(requirement, signer):
    valid, reason, attestation = X402PaymentHandler.verify_settlement_proof(
        payment_proof_header="SentinelPay-AVM not-valid-base64!!!",
        expected_requirement=requirement,
        verifier_public_key=signer.public_key_b64,
        consumed_nonces=set(),
    )
    assert valid is False
    assert attestation is None


def test_verify_settlement_proof_rejects_expired_attestation(signer, requirement):
    """An attestation past its expiry used to be accepted forever."""
    now = int(time.time())
    attestation = signed_attestation(signer, requirement, issued_at=now - 600, expires_at=now - 300)
    header = X402PaymentHandler.construct_settlement_proof(attestation, "tx1", "group1")

    valid, reason, _ = X402PaymentHandler.verify_settlement_proof(
        payment_proof_header=header,
        expected_requirement=requirement,
        verifier_public_key=signer.public_key_b64,
        consumed_nonces=set(),
    )
    assert valid is False
    assert "expired" in reason.lower()


def test_verify_settlement_proof_rejects_non_allow_decision(signer, requirement):
    attestation = signed_attestation(signer, requirement, decision="DENY")
    header = X402PaymentHandler.construct_settlement_proof(attestation, "tx1", "group1")

    valid, reason, _ = X402PaymentHandler.verify_settlement_proof(
        payment_proof_header=header,
        expected_requirement=requirement,
        verifier_public_key=signer.public_key_b64,
        consumed_nonces=set(),
    )
    assert valid is False
    assert "non-authorizing decision" in reason


def test_verify_settlement_proof_rejects_future_dated_attestation(signer, requirement):
    now = int(time.time())
    attestation = signed_attestation(
        signer, requirement, issued_at=now + 3600, expires_at=now + 7200
    )
    header = X402PaymentHandler.construct_settlement_proof(attestation, "tx1", "group1")

    valid, reason, _ = X402PaymentHandler.verify_settlement_proof(
        payment_proof_header=header,
        expected_requirement=requirement,
        verifier_public_key=signer.public_key_b64,
        consumed_nonces=set(),
    )
    assert valid is False
    assert "future" in reason.lower()


def test_rejected_proof_does_not_burn_the_nonce(signer, requirement):
    """A failed check must not consume the nonce and lock out a valid retry."""
    attestation = signed_attestation(signer, requirement, amount=1)  # amount mismatch
    header = X402PaymentHandler.construct_settlement_proof(attestation, "tx1", "group1")
    consumed = set()

    valid, _, _ = X402PaymentHandler.verify_settlement_proof(
        payment_proof_header=header,
        expected_requirement=requirement,
        verifier_public_key=signer.public_key_b64,
        consumed_nonces=consumed,
    )
    assert valid is False
    assert consumed == set()


# --- parse_402_response: header fallback ---

def test_parse_402_response_reads_www_authenticate_header():
    headers = {
        "WWW-Authenticate": (
            'x402 scheme="algorand", network="testnet", pay_to="ADDR3", '
            'amount="12345", asset="uALGO", resource="res-3"'
        )
    }
    req = X402PaymentHandler.parse_402_response(headers=headers, body=None)

    assert req is not None
    assert req.pay_to == "ADDR3"
    assert req.amount == 12345
    assert req.resource_id == "res-3"


def test_parse_402_response_ignores_header_without_payment_fields():
    req = X402PaymentHandler.parse_402_response(
        headers={"WWW-Authenticate": 'Bearer realm="api"'}, body=None
    )
    assert req is None
