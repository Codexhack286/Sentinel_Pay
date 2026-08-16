"""Pydantic models for raw and canonical payment intents."""

import time
import uuid
from typing import Any, Dict, Optional

from pydantic import BaseModel, Field, model_validator

# Default validity window for a freshly created intent. Kept short: it bounds
# how long a signed attestation stays replayable between issuance and on-chain
# consumption.
DEFAULT_INTENT_TTL_SECONDS = 300


class PaymentIntent(BaseModel):
    """Raw structured payment intent requested by an agent."""

    intent_id: str = Field(default_factory=lambda: f"intent_{uuid.uuid4().hex[:12]}")
    policy_id: str = "default_policy"
    agent_id: str
    declared_goal: str
    task_scope: str = Field(
        default="",
        description=(
            "The user-authorized task this payment claims to serve. Set by the "
            "harness from the original user objective, never by the agent's own "
            "reasoning, so the verifier can detect an agent that drifted off task."
        ),
    )
    tool_name: str
    resource: str
    destination: str
    amount: int = Field(
        ..., gt=0, description="Amount in micro-units (e.g. micro-ALGO). Must be positive."
    )
    currency: str = "uALGO"
    timestamp: int = Field(default_factory=lambda: int(time.time()))
    expiry: Optional[int] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _default_expiry_from_timestamp(self) -> "PaymentIntent":
        # Derived from `timestamp`, not from a second time.time() call: two
        # independent clock reads can straddle a second boundary and yield a
        # lifetime one second off the policy cap, which made denial flaky.
        if self.expiry is None:
            self.expiry = self.timestamp + DEFAULT_INTENT_TTL_SECONDS
        return self


class CanonicalIntent(BaseModel):
    """Normalized, canonical intent structure with security-isolated fields."""

    version: str = "1.0"
    policy_id: str
    agent_id: str
    declared_goal: str
    task_scope: str = ""
    tool_name: str
    resource_id: str
    destination: str
    amount: int = Field(..., gt=0)
    currency: str
    timestamp: int
    expiry: int

    def canonical_dict(self) -> Dict[str, Any]:
        """Returns sorted, deterministic dictionary for hashing."""
        return {
            "version": self.version,
            "policy_id": self.policy_id,
            "agent_id": self.agent_id,
            "declared_goal": self.declared_goal.strip(),
            "task_scope": self.task_scope.strip(),
            "tool_name": self.tool_name.strip(),
            "resource_id": self.resource_id.strip(),
            "destination": self.destination.strip(),
            "amount": self.amount,
            "currency": self.currency.strip().upper(),
            "timestamp": self.timestamp,
            "expiry": self.expiry,
        }
