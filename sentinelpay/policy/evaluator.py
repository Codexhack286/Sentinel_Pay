"""Policy evaluator executing deterministic checks against payment intent."""

from typing import TYPE_CHECKING
from sentinelpay.policy.models import AgentPolicy, PolicyEvaluationResult, PolicyDecision
from sentinelpay.policy.rules import (
    check_tool_allowed,
    check_destination_allowed,
    check_currency_allowed,
    check_per_transaction_limit,
    check_cumulative_spend_limit,
    check_expiry,
)

if TYPE_CHECKING:
    from sentinelpay.intent.models import CanonicalIntent


class PolicyEvaluator:
    """Evaluates canonical intent against deterministic policy rules."""

    def __init__(self, cumulative_spend_tracker: dict = None):
        # In-memory cumulative spend tracker for local development/testing: {agent_id: total_micro_units}
        self.cumulative_spend_tracker = cumulative_spend_tracker or {}

    def get_cumulative_spend(self, agent_id: str) -> int:
        return self.cumulative_spend_tracker.get(agent_id, 0)

    def record_spend(self, agent_id: str, amount: int):
        self.cumulative_spend_tracker[agent_id] = self.get_cumulative_spend(agent_id) + amount

    def evaluate(self, intent: "CanonicalIntent", policy: AgentPolicy) -> PolicyEvaluationResult:
        checks_passed = []
        checks_failed = []

        # 1. Tool check
        ok, msg = check_tool_allowed(intent.tool_name, policy)
        (checks_passed if ok else checks_failed).append(msg)

        # 2. Destination check
        ok, msg = check_destination_allowed(intent.destination, policy)
        (checks_passed if ok else checks_failed).append(msg)

        # 3. Currency check
        ok, msg = check_currency_allowed(intent.currency, policy)
        (checks_passed if ok else checks_failed).append(msg)

        # 4. Per transaction limit check
        ok, msg = check_per_transaction_limit(intent.amount, policy)
        (checks_passed if ok else checks_failed).append(msg)

        # 5. Daily cumulative spend check
        current_spend = self.get_cumulative_spend(intent.agent_id)
        ok, msg = check_cumulative_spend_limit(intent.amount, current_spend, policy)
        (checks_passed if ok else checks_failed).append(msg)

        # 6. Expiry check
        ok, msg = check_expiry(intent.expiry)
        (checks_passed if ok else checks_failed).append(msg)

        if checks_failed:
            return PolicyEvaluationResult(
                decision=PolicyDecision.DENY,
                reason="; ".join(checks_failed),
                policy_id=policy.policy_id,
                checks_passed=checks_passed,
                checks_failed=checks_failed,
            )

        return PolicyEvaluationResult(
            decision=PolicyDecision.ALLOW,
            reason="All deterministic policy checks passed successfully.",
            policy_id=policy.policy_id,
            checks_passed=checks_passed,
            checks_failed=checks_failed,
        )
