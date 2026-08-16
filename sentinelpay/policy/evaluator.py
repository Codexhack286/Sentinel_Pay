"""Policy evaluator executing deterministic checks against payment intent."""

import time
from typing import TYPE_CHECKING, Dict, List, Optional, Tuple

from sentinelpay.policy.models import AgentPolicy, PolicyDecision, PolicyEvaluationResult
from sentinelpay.policy.rules import (
    check_action_not_blocked,
    check_currency_allowed,
    check_cumulative_spend_limit,
    check_destination_allowed,
    check_expiry,
    check_intent_lifetime,
    check_per_transaction_limit,
    check_tool_allowed,
)

if TYPE_CHECKING:
    from sentinelpay.intent.models import CanonicalIntent


class PolicyEvaluator:
    """Evaluates canonical intent against deterministic policy rules.

    Spend tracking is timestamped so ``daily_spend_limit`` really is a rolling
    window rather than a counter that grows forever. Authoritative cumulative
    state still lives on-chain (the contract's ``spend_today``); this tracker is
    the local fast-path that lets the gateway deny before a transaction is ever
    constructed.
    """

    def __init__(self, cumulative_spend_tracker: Optional[Dict[str, List[Tuple[int, int]]]] = None):
        # {agent_id: [(unix_timestamp, amount), ...]}
        self._spend_log: Dict[str, List[Tuple[int, int]]] = cumulative_spend_tracker or {}

    def _prune(self, agent_id: str, window_seconds: int, now: int) -> List[Tuple[int, int]]:
        cutoff = now - window_seconds
        entries = [(ts, amt) for ts, amt in self._spend_log.get(agent_id, []) if ts > cutoff]
        self._spend_log[agent_id] = entries
        return entries

    def get_cumulative_spend(self, agent_id: str, window_seconds: int = 86_400) -> int:
        return sum(amt for _, amt in self._prune(agent_id, window_seconds, int(time.time())))

    def record_spend(self, agent_id: str, amount: int) -> None:
        self._spend_log.setdefault(agent_id, []).append((int(time.time()), amount))

    def evaluate(self, intent: "CanonicalIntent", policy: AgentPolicy) -> PolicyEvaluationResult:
        checks_passed: List[str] = []
        checks_failed: List[str] = []

        current_spend = self.get_cumulative_spend(intent.agent_id, policy.spend_window_seconds)

        results = [
            check_tool_allowed(intent.tool_name, policy),
            check_action_not_blocked(intent.declared_goal, policy),
            check_destination_allowed(intent.destination, policy),
            check_currency_allowed(intent.currency, policy),
            check_per_transaction_limit(intent.amount, policy),
            check_cumulative_spend_limit(intent.amount, current_spend, policy),
            check_expiry(intent.expiry),
            check_intent_lifetime(intent.timestamp, intent.expiry, policy),
        ]
        for ok, msg in results:
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
