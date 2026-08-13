"""Unit tests for deterministic policy rules and evaluator."""

import time
import pytest
from sentinelpay.policy.models import AgentPolicy, PolicyDecision
from sentinelpay.policy.evaluator import PolicyEvaluator
from sentinelpay.intent.models import CanonicalIntent


@pytest.fixture
def sample_policy():
    return AgentPolicy(
        policy_id="policy-test-01",
        agent_id="agent-01",
        max_per_transaction=200000,  # 0.2 ALGO
        daily_spend_limit=1000000,    # 1.0 ALGO
        allowed_tools=["paid_research", "weather_query"],
        allowed_destinations=["MERCHANT_ADDR_1", "MERCHANT_ADDR_2"],
        allowed_currencies=["uALGO", "USDC"],
    )


@pytest.fixture
def valid_intent():
    return CanonicalIntent(
        version="1.0",
        policy_id="policy-test-01",
        agent_id="agent-01",
        declared_goal="Analyze solar data",
        tool_name="paid_research",
        resource_id="solar-data-2026",
        destination="MERCHANT_ADDR_1",
        amount=100000,
        currency="uALGO",
        timestamp=int(time.time()),
        expiry=int(time.time()) + 300,
    )


def test_policy_allow(sample_policy, valid_intent):
    evaluator = PolicyEvaluator()
    result = evaluator.evaluate(valid_intent, sample_policy)
    assert result.decision == PolicyDecision.ALLOW
    assert len(result.checks_failed) == 0


def test_policy_reject_per_transaction_cap(sample_policy, valid_intent):
    valid_intent.amount = 500000  # Exceeds max_per_transaction 200000
    evaluator = PolicyEvaluator()
    result = evaluator.evaluate(valid_intent, sample_policy)
    assert result.decision == PolicyDecision.DENY
    assert any("exceeds max per-transaction limit" in msg for msg in result.checks_failed)


def test_policy_reject_unauthorized_tool(sample_policy, valid_intent):
    valid_intent.tool_name = "unauthorized_tool"
    evaluator = PolicyEvaluator()
    result = evaluator.evaluate(valid_intent, sample_policy)
    assert result.decision == PolicyDecision.DENY
    assert any("NOT authorized by policy" in msg for msg in result.checks_failed)


def test_policy_reject_unauthorized_destination(sample_policy, valid_intent):
    valid_intent.destination = "ATTACKER_ADDR_XYZ"
    evaluator = PolicyEvaluator()
    result = evaluator.evaluate(valid_intent, sample_policy)
    assert result.decision == PolicyDecision.DENY
    assert any("NOT authorized by policy" in msg for msg in result.checks_failed)


def test_policy_reject_expired_intent(sample_policy, valid_intent):
    valid_intent.expiry = int(time.time()) - 60  # Expired 60s ago
    evaluator = PolicyEvaluator()
    result = evaluator.evaluate(valid_intent, sample_policy)
    assert result.decision == PolicyDecision.DENY
    assert any("expired" in msg for msg in result.checks_failed)
