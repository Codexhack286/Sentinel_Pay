"""Integration test for the full x402 + SentinelPay payment flow.

The server enforces two independent things, so the tests do too: a valid
authorization, and proof that it was consumed on-chain. A fake chain reader
stands in for algod so the suite stays offline.
"""

import pytest
from fastapi.testclient import TestClient

from sentinelpay.gateway.middleware import SentinelPayGateway
from sentinelpay.intent.models import PaymentIntent
from sentinelpay.payments.settlement import ChainUnavailable
from sentinelpay.payments.x402 import X402PaymentHandler
from sentinelpay.policy.models import AgentPolicy
from sentinelpay.verifier.verifier import LocalSemanticVerifier
from services.api import app as api_module
from services.api.app import _default_signer, app

client = TestClient(app)


class FakeChain:
    """Reports whichever nonces the test says settled."""

    def __init__(self, consumed=(), raises: bool = False):
        self.consumed = set(consumed)
        self.raises = raises

    def nonce_consumed(self, app_id: int, nonce: bytes) -> bool:
        if self.raises:
            raise ChainUnavailable("algod unreachable")
        return nonce in self.consumed


@pytest.fixture(autouse=True)
def isolate_server_state(monkeypatch):
    """Each test gets a clean serve-once set."""
    monkeypatch.setattr(api_module, "_consumed_nonces", set())


def authorize(requirement: dict):
    """Run a legitimate intent through the gateway, signed with the server's key."""
    gateway = SentinelPayGateway(verifier=LocalSemanticVerifier(signer=_default_signer))
    policy = AgentPolicy(
        policy_id="policy-integration-01",
        agent_id="deep-agent-researcher-01",
        max_per_transaction=requirement["amount"] * 2,
        daily_spend_limit=requirement["amount"] * 10,
        allowed_tools=["paid_research"],
        allowed_destinations=[requirement["pay_to"]],
        allowed_categories=["research", "energy", "dataset"],
    )
    intent = PaymentIntent(
        agent_id="deep-agent-researcher-01",
        declared_goal="Purchase renewable energy dataset for solar research",
        task_scope="Research renewable energy datasets for 2026",
        tool_name="paid_research",
        resource=requirement["resource_id"],
        destination=requirement["pay_to"],
        amount=requirement["amount"],
        currency=requirement["asset"],
    )
    response = gateway.process_payment_request(intent, policy)
    assert response.status == "authorized"
    return response.attestation


def proof_for(attestation) -> str:
    return X402PaymentHandler.construct_settlement_proof(
        attestation=attestation, tx_id="tx_algorand_mock_001", group_id="group_mock_001"
    )


def require_settlement(monkeypatch) -> None:
    monkeypatch.setattr(api_module, "settlement_required", lambda: True)
    monkeypatch.setattr(api_module.settings, "SENTINELPAY_APP_ID", 769368669)


def test_challenge_is_returned_without_payment():
    resp = client.get("/paid-dataset")

    assert resp.status_code == 402
    assert "WWW-Authenticate" in resp.headers
    body = resp.json()
    assert body["amount"] > 0
    assert body["asset"] == "uALGO"


def test_end_to_end_authorized_and_settled_payment_flow(monkeypatch):
    requirement = client.get("/paid-dataset").json()
    attestation = authorize(requirement)

    require_settlement(monkeypatch)
    monkeypatch.setattr(
        api_module, "chain_reader", FakeChain(consumed=[attestation.nonce_bytes()])
    )

    resp = client.get("/paid-dataset", headers={"Authorization": proof_for(attestation)})

    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "success"
    assert data["settlement_verified"] is True
    assert "confidential_metrics" in data["data"]


def test_valid_authorization_that_never_settled_is_refused(monkeypatch):
    """The heart of it: a perfect signature is not a payment.

    This is also the bare-payment case. A payment broadcast without the
    SentinelPay app call writes no nonce box, so it looks exactly like this.
    """
    requirement = client.get("/paid-dataset").json()
    attestation = authorize(requirement)

    require_settlement(monkeypatch)
    monkeypatch.setattr(api_module, "chain_reader", FakeChain())  # nothing settled

    resp = client.get("/paid-dataset", headers={"Authorization": proof_for(attestation)})

    assert resp.status_code == 402
    assert "not settled" in resp.json()["detail"].lower()


def test_unreachable_chain_fails_closed(monkeypatch):
    """An outage must not become an open door."""
    requirement = client.get("/paid-dataset").json()
    attestation = authorize(requirement)

    require_settlement(monkeypatch)
    monkeypatch.setattr(api_module, "chain_reader", FakeChain(raises=True))

    resp = client.get("/paid-dataset", headers={"Authorization": proof_for(attestation)})

    assert resp.status_code == 402
    assert "refusing to serve" in resp.json()["detail"]


def test_failed_settlement_does_not_burn_the_serve_once_nonce(monkeypatch):
    """A retry after the payment confirms must still work."""
    requirement = client.get("/paid-dataset").json()
    attestation = authorize(requirement)
    header = proof_for(attestation)
    require_settlement(monkeypatch)

    # First attempt: the group has not confirmed yet.
    monkeypatch.setattr(api_module, "chain_reader", FakeChain())
    assert client.get("/paid-dataset", headers={"Authorization": header}).status_code == 402

    # It confirms; the same proof must now be honoured.
    monkeypatch.setattr(
        api_module, "chain_reader", FakeChain(consumed=[attestation.nonce_bytes()])
    )
    assert client.get("/paid-dataset", headers={"Authorization": header}).status_code == 200


def test_health_reports_whether_settlement_is_enforced():
    body = client.get("/").json()

    assert body["status"] == "online"
    assert "enforces_onchain_settlement" in body
