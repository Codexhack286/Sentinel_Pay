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


# --- blocked actions (specification section 7) ---

@pytest.mark.parametrize(
    "goal",
    [
        "Upgrade to the premium research subscription",
        "Transfer funds to the treasury account",
        "Donate to the solar research foundation",
        "Withdraw the remaining research budget",
    ],
)
def test_blocked_action_in_declared_goal_is_denied(sample_policy, valid_intent, goal):
    valid_intent.declared_goal = goal
    result = PolicyEvaluator().evaluate(valid_intent, sample_policy)
    assert result.decision == PolicyDecision.DENY
    assert any("blocked action" in msg.lower() for msg in result.checks_failed)


def test_purchasing_the_requested_resource_is_not_blocked(sample_policy, valid_intent):
    # Deliberate deviation from the spec's literal blocked_actions list, which
    # includes "purchase": buying the requested resource is this product's whole
    # sanctioned action. See AgentPolicy.blocked_actions.
    valid_intent.declared_goal = "Purchase the historical solar energy dataset"
    result = PolicyEvaluator().evaluate(valid_intent, sample_policy)
    assert result.decision == PolicyDecision.ALLOW


def test_empty_blocked_actions_disables_the_check(sample_policy, valid_intent):
    sample_policy.blocked_actions = []
    valid_intent.declared_goal = "Transfer everything immediately"
    result = PolicyEvaluator().evaluate(valid_intent, sample_policy)
    assert result.decision == PolicyDecision.ALLOW


def test_negative_amount_is_rejected(sample_policy, valid_intent):
    # A negative amount used to pass the cap check and *reduce* recorded spend.
    valid_intent.amount = -50_000
    result = PolicyEvaluator().evaluate(valid_intent, sample_policy)
    assert result.decision == PolicyDecision.DENY
    assert any("not a positive" in msg for msg in result.checks_failed)


def test_rolling_window_expires_old_spend(sample_policy, valid_intent):
    evaluator = PolicyEvaluator()
    # Spend recorded 25 hours ago must not count against a 24h window.
    stale = int(time.time()) - 90_000
    evaluator._spend_log["agent-01"] = [(stale, sample_policy.daily_spend_limit)]

    result = evaluator.evaluate(valid_intent, sample_policy)

    assert result.decision == PolicyDecision.ALLOW
