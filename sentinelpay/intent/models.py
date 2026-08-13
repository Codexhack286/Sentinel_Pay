"""Pydantic models for raw and canonical payment intents."""

import time
import uuid
from typing import Any, Dict, Optional
from pydantic import BaseModel, Field


class PaymentIntent(BaseModel):
    """Raw structured payment intent requested by an agent."""
    intent_id: str = Field(default_factory=lambda: f"intent_{uuid.uuid4().hex[:12]}")
    policy_id: str = "default_policy"
    agent_id: str
    declared_goal: str
    tool_name: str
    resource: str
    destination: str
    amount: int = Field(..., description="Amount in micro-units (e.g. micro-ALGO)")
    currency: str = "uALGO"
    timestamp: int = Field(default_factory=lambda: int(time.time()))
    expiry: int = Field(default_factory=lambda: int(time.time()) + 300)
    metadata: Dict[str, Any] = Field(default_factory=dict)


class CanonicalIntent(BaseModel):
    """Normalized, canonical intent structure with security-isolated fields."""
    version: str = "1.0"
    policy_id: str
    agent_id: str
    declared_goal: str
    tool_name: str
    resource_id: str
    destination: str
    amount: int
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
            "tool_name": self.tool_name.strip(),
            "resource_id": self.resource_id.strip(),
            "destination": self.destination.strip(),
            "amount": self.amount,
            "currency": self.currency.strip().upper(),
            "timestamp": self.timestamp,
            "expiry": self.expiry,
        }
