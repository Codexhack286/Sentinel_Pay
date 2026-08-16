"""Attack C — Replay.

Two distinct replay surfaces, both covered here:

  - HTTP layer: the same settled authorization redeemed twice for the content.
    Guarded by the server's serve-once set.
  - Chain layer: the same authorization consumed twice for money. Guarded by the
    contract's nonce box, tested in contracts/tests/test_reference_model.py and
    proven live by scripts/verify_attack.py.
"""

import pytest
from fastapi.testclient import TestClient

from sentinelpay.gateway.middleware import SentinelPayGateway
from sentinelpay.intent.models import PaymentIntent
from sentinelpay.payments.x402 import X402PaymentHandler
from sentinelpay.policy.models import AgentPolicy
from sentinelpay.verifier.verifier import LocalSemanticVerifier
from services.api import app as api_module
from services.api.app import _default_signer, app

client = TestClient(app)


class SettledChain:
    """Every nonce it is told about has settled on-chain."""

    def __init__(self, consumed):
        self.consumed = set(consumed)

    def nonce_consumed(self, app_id: int, nonce: bytes) -> bool:
        return nonce in self.consumed


@pytest.fixture(autouse=True)
def isolate_server_state(monkeypatch):
    monkeypatch.setattr(api_module, "_consumed_nonces", set())
    monkeypatch.setattr(api_module, "settlement_required", lambda: True)
    monkeypatch.setattr(api_module.settings, "SENTINELPAY_APP_ID", 769368669)


def test_attestation_replay_rejected(monkeypatch):
    gateway = SentinelPayGateway(verifier=LocalSemanticVerifier(signer=_default_signer))

    # Read the payee and price off the server's own 402 challenge rather than
    # hardcoding them. RESOURCE_OWNER_ADDRESS and RESOURCE_PRICE_UALGO are
    # configurable, so a hardcoded placeholder made this test pass only on
    # machines with no .env.
    requirement = client.get("/paid-dataset").json()

    policy = AgentPolicy(
        policy_id="policy-replay-01",
        agent_id="agent-replay-01",
        max_per_transaction=requirement["amount"] * 2,
        daily_spend_limit=requirement["amount"] * 10,
        allowed_tools=["paid_research"],
        allowed_destinations=[requirement["pay_to"]],
        allowed_categories=["research", "energy"],
    )
    intent = PaymentIntent(
        agent_id="agent-replay-01",
        declared_goal="Legitimate energy research query",
        task_scope="Energy research for the 2026 report",
        tool_name="paid_research",
        resource=requirement["resource_id"],
        destination=requirement["pay_to"],
        amount=requirement["amount"],
        currency=requirement["asset"],
    )

    gateway_resp = gateway.process_payment_request(intent, policy)
    assert gateway_resp.status == "authorized"

    attestation = gateway_resp.attestation
    monkeypatch.setattr(api_module, "chain_reader", SettledChain([attestation.nonce_bytes()]))

    proof_header = X402PaymentHandler.construct_settlement_proof(
        attestation=attestation,
        tx_id="tx_replay_test_1",
        group_id="group_replay_test_1",
    )

    # First access succeeds: authorized, and settled on-chain.
    assert client.get("/paid-dataset", headers={"Authorization": proof_header}).status_code == 200

    # Second access with the identical attestation is a replay. The chain still
    # says the nonce is consumed — that is precisely why the chain check alone
    # cannot carry serve-once, and the server's own set has to.
    resp2 = client.get("/paid-dataset", headers={"Authorization": proof_header})
    assert resp2.status_code == 403
    assert "already been consumed (replay detected)" in resp2.json()["detail"]
