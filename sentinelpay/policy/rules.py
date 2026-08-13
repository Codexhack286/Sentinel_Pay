"""Deterministic policy rules."""

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


def check_per_transaction_limit(amount: int, policy: AgentPolicy) -> Tuple[bool, str]:
    if amount <= policy.max_per_transaction:
        return True, f"Amount {amount} is within per-transaction cap ({policy.max_per_transaction})."
    return False, f"Amount {amount} exceeds max per-transaction limit ({policy.max_per_transaction})."


def check_cumulative_spend_limit(
    amount: int, current_cumulative_spend: int, policy: AgentPolicy
) -> Tuple[bool, str]:
    if current_cumulative_spend + amount <= policy.daily_spend_limit:
        return True, f"New cumulative spend {current_cumulative_spend + amount} is within daily limit ({policy.daily_spend_limit})."
    return False, f"Cumulative spend {current_cumulative_spend + amount} would exceed daily limit ({policy.daily_spend_limit})."


def check_expiry(expiry_timestamp: int) -> Tuple[bool, str]:
    now = int(time.time())
    if expiry_timestamp > now:
        return True, f"Intent timestamp is valid (expires in {expiry_timestamp - now}s)."
    return False, f"Intent has expired ({now - expiry_timestamp}s ago)."
