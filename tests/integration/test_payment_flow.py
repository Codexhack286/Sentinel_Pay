"""Integration test for full x402 + SentinelPay payment flow."""

from fastapi.testclient import TestClient
from services.api.app import app, SERVER_VERIFIER_PUBLIC_KEY, _default_signer
from sentinelpay.intent.models import PaymentIntent
from sentinelpay.policy.models import AgentPolicy
from sentinelpay.gateway.middleware import SentinelPayGateway
from sentinelpay.verifier.verifier import LocalSemanticVerifier
from sentinelpay.payments.x402 import X402PaymentHandler

client = TestClient(app)


def test_end_to_end_authorized_payment_flow():
    # 1. Access paid endpoint without payment -> Expect 402 Payment Required
    resp1 = client.get("/paid-dataset")
    assert resp1.status_code == 402
    assert "WWW-Authenticate" in resp1.headers
    req_body = resp1.json()
    assert req_body["amount"] == 100000
    assert req_body["asset"] == "uALGO"

    # 2. Configure Gateway with the same signer as the server for end-to-end demo
    verifier = LocalSemanticVerifier(signer=_default_signer)
    gateway = SentinelPayGateway(verifier=verifier)

    policy = AgentPolicy(
        policy_id="policy-integration-01",
        agent_id="deep-agent-researcher-01",
        max_per_transaction=200000,
        daily_spend_limit=1000000,
        allowed_tools=["paid_research"],
        allowed_destinations=[req_body["pay_to"]],
        allowed_categories=["research", "energy", "dataset"],
    )

    intent = PaymentIntent(
        agent_id="deep-agent-researcher-01",
        declared_goal="Purchase renewable energy dataset for solar research",
        tool_name="paid_research",
        resource=req_body["resource_id"],
        destination=req_body["pay_to"],
        amount=req_body["amount"],
        currency=req_body["asset"],
    )

    # 3. Process payment intent through SentinelPay Gateway
    gateway_resp = gateway.process_payment_request(intent, policy)
    assert gateway_resp.status == "authorized"
    assert gateway_resp.attestation is not None

    # 4. Construct settlement proof header
    proof_header = X402PaymentHandler.construct_settlement_proof(
        attestation=gateway_resp.attestation,
        tx_id="tx_algorand_mock_001",
        group_id="group_algorand_mock_001",
    )

    # 5. Access paid endpoint with SentinelPay proof -> Expect 200 OK + Data
    resp2 = client.get("/paid-dataset", headers={"Authorization": proof_header})
    assert resp2.status_code == 200
    data = resp2.json()
    assert data["status"] == "success"
    assert "confidential_metrics" in data["data"]
