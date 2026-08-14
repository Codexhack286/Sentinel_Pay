"""Pydantic models for SentinelPay policies and evaluation decisions."""

from enum import Enum
from typing import List, Optional
from pydantic import BaseModel, Field


class PolicyDecision(str, Enum):
    ALLOW = "ALLOW"
    DENY = "DENY"
    REVIEW = "REVIEW"


class AgentPolicy(BaseModel):
    """Deterministic policy rules assigned to an agent or task scope."""
    policy_id: str
    agent_id: str
    max_per_transaction: int = Field(
        ..., description="Maximum amount in micro-units allowed per single transaction."
    )
    daily_spend_limit: int = Field(
        ..., description="Maximum cumulative spend in micro-units allowed in 24h."
    )
    allowed_tools: List[str] = Field(
        default_factory=list, description="Allowlist of tool names permitted to trigger payment."
    )
    allowed_destinations: List[str] = Field(
        default_factory=list, description="Allowlist of recipient Algorand addresses."
    )
    allowed_currencies: List[str] = Field(
        default_factory=lambda: ["uALGO", "USDC"], description="Allowlist of acceptable assets/currencies."
    )
    allowed_categories: List[str] = Field(
        default_factory=lambda: ["research", "weather", "search", "dataset"],
        description="Allowed business categories."
    )
    require_verification_above: int = Field(
        default=0,
        description="Threshold above which semantic verification is mandatory."
    )


class PolicyEvaluationResult(BaseModel):
    """Result of policy evaluation."""
    decision: PolicyDecision
    reason: str
    policy_id: str
    checks_passed: List[str] = Field(default_factory=list)
    checks_failed: List[str] = Field(default_factory=list)
