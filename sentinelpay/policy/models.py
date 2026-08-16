"""Pydantic models for SentinelPay policies and evaluation decisions."""

from enum import Enum
from typing import List

from pydantic import BaseModel, Field, model_validator


class PolicyDecision(str, Enum):
    ALLOW = "ALLOW"
    DENY = "DENY"
    REVIEW = "REVIEW"


class AgentPolicy(BaseModel):
    """Deterministic policy rules assigned to an agent or task scope."""

    policy_id: str
    agent_id: str
    max_per_transaction: int = Field(
        ..., gt=0, description="Maximum amount in micro-units allowed per single transaction."
    )
    daily_spend_limit: int = Field(
        ..., gt=0, description="Maximum cumulative spend in micro-units allowed in 24h."
    )
    spend_window_seconds: int = Field(
        default=86_400, gt=0, description="Rolling window the cumulative limit applies over."
    )
    allowed_tools: List[str] = Field(
        default_factory=list, description="Allowlist of tool names permitted to trigger payment."
    )
    allowed_destinations: List[str] = Field(
        default_factory=list, description="Allowlist of recipient Algorand addresses."
    )
    allowed_currencies: List[str] = Field(
        default_factory=lambda: ["uALGO", "USDC"],
        description="Allowlist of acceptable assets/currencies.",
    )
    allowed_categories: List[str] = Field(
        default_factory=lambda: ["research", "weather", "search", "dataset"],
        description="Allowed business categories, matched against the declared goal.",
    )
    blocked_actions: List[str] = Field(
        default_factory=lambda: [
            "subscription",
            "subscribe",
            "upgrade",
            "transfer",
            "withdraw",
            "donate",
            "invest",
            "gift",
        ],
        description=(
            "Action words that deny a payment outright, matched against the declared "
            "goal. Note the deviation from the specification's example list, which "
            "also blocks 'purchase': purchasing the requested resource is this "
            "product's whole sanctioned action, so blocking that word would deny "
            "every legitimate payment. What is blocked here is open-ended or "
            "value-transferring commitments, which no research task needs."
        ),
    )
    require_verification_above: int = Field(
        default=0,
        ge=0,
        description=(
            "Amounts at or below this threshold may take the deterministic-only "
            "path; anything above always requires semantic verification."
        ),
    )
    max_intent_lifetime_seconds: int = Field(
        default=300,
        gt=0,
        description="Longest expiry window an intent may declare, bounding replay exposure.",
    )

    @model_validator(mode="after")
    def _per_transaction_within_daily(self) -> "AgentPolicy":
        if self.max_per_transaction > self.daily_spend_limit:
            raise ValueError(
                f"max_per_transaction ({self.max_per_transaction}) exceeds "
                f"daily_spend_limit ({self.daily_spend_limit}); the per-call cap "
                "would never be reachable and the policy is contradictory."
            )
        return self


class PolicyEvaluationResult(BaseModel):
    """Result of policy evaluation."""

    decision: PolicyDecision
    reason: str
    policy_id: str
    checks_passed: List[str] = Field(default_factory=list)
    checks_failed: List[str] = Field(default_factory=list)
