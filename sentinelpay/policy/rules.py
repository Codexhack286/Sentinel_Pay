"""Deterministic policy rules.

Every rule is a pure function returning ``(passed, human_readable_reason)``.
Reasons are surfaced verbatim in denial messages, so they must never contain
secret material.
"""

import time
from typing import Tuple

from sentinelpay.policy.models import AgentPolicy


def check_tool_allowed(tool_name: str, policy: AgentPolicy) -> Tuple[bool, str]:
    if not policy.allowed_tools:
        return True, "All tools allowed by policy."
    if tool_name in policy.allowed_tools:
        return True, f"Tool '{tool_name}' is in allowed tools list."
    return False, f"Tool '{tool_name}' is NOT authorized by policy."


def check_destination_allowed(destination: str, policy: AgentPolicy) -> Tuple[bool, str]:
    if not policy.allowed_destinations:
        return True, "All destinations allowed by policy."
    if destination in policy.allowed_destinations:
        return True, f"Destination '{destination}' is in allowed destinations list."
    return False, f"Destination '{destination}' is NOT authorized by policy."


def check_currency_allowed(currency: str, policy: AgentPolicy) -> Tuple[bool, str]:
    allowed_upper = [c.upper() for c in policy.allowed_currencies]
    if currency.upper() in allowed_upper:
        return True, f"Currency '{currency}' is allowed."
    return False, f"Currency '{currency}' is NOT supported or allowed by policy."


def check_action_not_blocked(declared_goal: str, policy: AgentPolicy) -> Tuple[bool, str]:
    """Deny goals describing an action the policy forbids outright.

    Deterministic and independent of the semantic verifier, so a payment like
    "upgrade to the premium subscription" is refused on its own terms even if it
    happens to share vocabulary with the authorized task.
    """
    if not policy.blocked_actions:
        return True, "No blocked actions configured."
    goal_lower = declared_goal.lower()
    for action in policy.blocked_actions:
        if action.lower() in goal_lower:
            return False, f"Declared goal describes a blocked action: '{action}'."
    return True, "Declared goal contains no blocked action."


def check_per_transaction_limit(amount: int, policy: AgentPolicy) -> Tuple[bool, str]:
    if amount <= 0:
        return False, f"Amount {amount} is not a positive micro-unit value."
    if amount <= policy.max_per_transaction:
        return True, f"Amount {amount} is within per-transaction cap ({policy.max_per_transaction})."
    return False, f"Amount {amount} exceeds max per-transaction limit ({policy.max_per_transaction})."


def check_cumulative_spend_limit(
    amount: int, current_cumulative_spend: int, policy: AgentPolicy
) -> Tuple[bool, str]:
    projected = current_cumulative_spend + amount
    if projected <= policy.daily_spend_limit:
        return True, f"New cumulative spend {projected} is within daily limit ({policy.daily_spend_limit})."
    return False, f"Cumulative spend {projected} would exceed daily limit ({policy.daily_spend_limit})."


def check_expiry(expiry_timestamp: int) -> Tuple[bool, str]:
    now = int(time.time())
    if expiry_timestamp > now:
        return True, f"Intent timestamp is valid (expires in {expiry_timestamp - now}s)."
    return False, f"Intent has expired ({now - expiry_timestamp}s ago)."


def check_intent_lifetime(
    issued_timestamp: int, expiry_timestamp: int, policy: AgentPolicy
) -> Tuple[bool, str]:
    """Reject intents that claim an unreasonably long validity window.

    A long-lived attestation widens the replay window between issuance and
    on-chain consumption, so the policy caps it rather than trusting whatever
    the agent asked for.
    """
    lifetime = expiry_timestamp - issued_timestamp
    if lifetime <= 0:
        return False, f"Intent expiry ({expiry_timestamp}) is not after its issue time ({issued_timestamp})."
    if lifetime <= policy.max_intent_lifetime_seconds:
        return True, f"Intent lifetime {lifetime}s is within the {policy.max_intent_lifetime_seconds}s cap."
    return False, (
        f"Intent lifetime {lifetime}s exceeds the maximum allowed "
        f"{policy.max_intent_lifetime_seconds}s."
    )
