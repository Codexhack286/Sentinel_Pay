"""Attack C — Replay Attack Test.
Verifies that reusing an existing attestation or nonce for a new payment fails.
"""

from fastapi.testclient import TestClient
from services.api.app import app, _default_signer
from sentinelpay.intent.models import PaymentIntent
from sentinelpay.policy.models import AgentPolicy
from sentinelpay.gateway.middleware import SentinelPayGateway
from sentinelpay.verifier.verifier import LocalSemanticVerifier
from sentinelpay.payments.x402 import X402PaymentHandler

client = TestClient(app)


def test_attestation_replay_rejected():
    verifier = LocalSemanticVerifier(signer=_default_signer)
    gateway = SentinelPayGateway(verifier=verifier)

    policy = AgentPolicy(
        policy_id="policy-replay-01",
        agent_id="agent-replay-01",
        max_per_transaction=200000,
        daily_spend_limit=1000000,
        allowed_tools=["paid_research"],
        allowed_destinations=["RESOURCE_OWNER_ALGORAND_ADDRESS_AAAAAAAAAAAAAAAAAAAAAAAAAAAA"],
        allowed_categories=["research", "energy"],
    )

    intent = PaymentIntent(
        agent_id="agent-replay-01",
        declared_goal="Legitimate energy research query",
        tool_name="paid_research",
        resource="energy-dataset-2026",
        destination="RESOURCE_OWNER_ALGORAND_ADDRESS_AAAAAAAAAAAAAAAAAAAAAAAAAAAA",
        amount=100000,
        currency="uALGO",
    )

    gateway_resp = gateway.process_payment_request(intent, policy)
    assert gateway_resp.status == "authorized"

    proof_header = X402PaymentHandler.construct_settlement_proof(
        attestation=gateway_resp.attestation,
        tx_id="tx_replay_test_1",
        group_id="group_replay_test_1",
    )

    # First access succeeds
    resp1 = client.get("/paid-dataset", headers={"Authorization": proof_header})
    assert resp1.status_code == 200

    # Second access with identical attestation (replay) must be rejected
    resp2 = client.get("/paid-dataset", headers={"Authorization": proof_header})
    assert resp2.status_code == 403
    assert "already been consumed (replay detected)" in resp2.json()["detail"]
