"""Verifier interface and local verifier implementations."""

import time
from typing import Protocol, Optional
from pydantic import BaseModel, Field
from sentinelpay.intent.models import CanonicalIntent
from sentinelpay.policy.models import AgentPolicy, PolicyDecision
from sentinelpay.verifier.attestation import Attestation, AttestationSigner


class VerificationResult(BaseModel):
    """Result returned by an IntentVerifier."""
    approved: bool
    decision: PolicyDecision
    reason: str
    attestation: Optional[Attestation] = None


class IntentVerifier(Protocol):
    """Protocol defining verifier interface for pluggable implementations."""

    def verify(
        self,
        intent: CanonicalIntent,
        intent_hash: str,
        policy: AgentPolicy,
    ) -> VerificationResult:
        """Evaluate intent and issue attestation if approved."""
        ...


class LocalSemanticVerifier:
    """
    Zero-cost local verifier.
    Performs deterministic task alignment without requiring external paid LLM APIs.
    """

    def __init__(self, signer: Optional[AttestationSigner] = None, verifier_id: str = "sentinelpay_local_verifier"):
        self.signer = signer or AttestationSigner()
        self.verifier_id = verifier_id

    @property
    def public_key_b64(self) -> str:
        return self.signer.public_key_b64

    def verify(
        self,
        intent: CanonicalIntent,
        intent_hash: str,
        policy: AgentPolicy,
    ) -> VerificationResult:
        # Check 1: Declared goal cannot be empty or generic bypass keywords
        goal_lower = intent.declared_goal.lower()
        if not goal_lower:
            return VerificationResult(
                approved=False,
                decision=PolicyDecision.DENY,
                reason="Declared goal is empty; task alignment cannot be verified.",
            )

        # Check 2: Prompt injection / suspicious override detection in declared goal
        adversarial_indicators = [
            "system override",
            "ignore previous instructions",
            "send all funds",
            "drain wallet",
            "lockdown emergency transfer",
            "urgent security audit transfer",
            "attacker",
            "bypass policy",
        ]
        for indicator in adversarial_indicators:
            if indicator in goal_lower or indicator in intent.resource_id.lower():
                return VerificationResult(
                    approved=False,
                    decision=PolicyDecision.DENY,
                    reason=f"Adversarial instruction or prompt injection detected: contains '{indicator}'.",
                )

        # Check 3: Check category alignment
        if policy.allowed_categories:
            category_match = any(cat in goal_lower or cat in intent.tool_name.lower() or cat in intent.resource_id.lower() for cat in policy.allowed_categories)
            if not category_match:
                return VerificationResult(
                    approved=False,
                    decision=PolicyDecision.DENY,
                    reason=f"Declared task '{intent.declared_goal}' does not align with authorized policy categories ({policy.allowed_categories}).",
                )

        # If all semantic checks pass, create and sign Attestation
        attestation = Attestation(
            intent_hash=intent_hash,
            agent_id=intent.agent_id,
            policy_id=policy.policy_id,
            tool_name=intent.tool_name,
            destination=intent.destination,
            amount=intent.amount,
            currency=intent.currency,
            issued_at=int(time.time()),
            expires_at=intent.expiry,
            decision="ALLOW",
            verifier_id=self.verifier_id,
        )
        signed_attestation = self.signer.sign(attestation)

        return VerificationResult(
            approved=True,
            decision=PolicyDecision.ALLOW,
            reason="Semantic intent aligns with policy and declared task scope.",
            attestation=signed_attestation,
        )
