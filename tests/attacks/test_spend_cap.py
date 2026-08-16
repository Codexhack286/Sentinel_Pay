"""Attack D — Spend Cap Exceeded Test.
Verifies that rapid or cumulative payments exceeding the daily limit are rejected.
"""

from sentinelpay.intent.models import PaymentIntent
from sentinelpay.policy.models import AgentPolicy
from sentinelpay.gateway.middleware import SentinelPayGateway
from sentinelpay.verifier.verifier import LocalSemanticVerifier


def test_cumulative_spend_cap_enforced():
    gateway = SentinelPayGateway(verifier=LocalSemanticVerifier())

    # Budget cap: 200,000 uALGO daily limit
    policy = AgentPolicy(
        policy_id="policy-cap-01",
        agent_id="agent-budget-01",
        max_per_transaction=150000,
        daily_spend_limit=200000,
        allowed_tools=["paid_research"],
        allowed_destinations=["MERCHANT_ADDR_1"],
        allowed_categories=["research", "energy"],
    )

    intent1 = PaymentIntent(
        agent_id="agent-budget-01",
        declared_goal="First energy dataset batch",
        tool_name="paid_research",
        resource="dataset-1",
        destination="MERCHANT_ADDR_1",
        amount=120000,
        currency="uALGO",
    )

    # Tx 1 (120k uALGO <= 200k daily) -> Pass
    res1 = gateway.process_payment_request(intent1, policy)
    assert res1.status == "authorized"

    intent2 = PaymentIntent(
        agent_id="agent-budget-01",
        declared_goal="Second energy dataset batch",
        tool_name="paid_research",
        resource="dataset-2",
        destination="MERCHANT_ADDR_1",
        amount=100000,  # 120k + 100k = 220k > 200k daily cap
        currency="uALGO",
    )

    # Tx 2 -> Denied
    res2 = gateway.process_payment_request(intent2, policy)
    assert res2.status == "denied"
    assert "would exceed daily limit" in res2.reason
