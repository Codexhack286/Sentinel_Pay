"""SentinelPay Gateway middleware: orchestrates normalization, policy evaluation, verification, and attestation issuance."""

from typing import Optional

from pydantic import BaseModel

from sentinelpay.intent.hasher import hash_intent
from sentinelpay.intent.models import CanonicalIntent, PaymentIntent
from sentinelpay.intent.normalizer import IntentNormalizer
from sentinelpay.policy.evaluator import PolicyEvaluator
from sentinelpay.policy.models import AgentPolicy, PolicyDecision
from sentinelpay.verifier.attestation import Attestation
from sentinelpay.verifier.verifier import IntentVerifier, LocalSemanticVerifier
from sentinelpay.tracing import traceable


class GatewayResponse(BaseModel):
    """Response returned to agent or payment tool."""
    status: str  # "authorized", "denied", "authorization_required"
    payment_intent_id: str
    amount: int
    currency: str
    destination: str
    reason: str
    decision: PolicyDecision
    attestation: Optional[Attestation] = None
    canonical_intent: Optional[CanonicalIntent] = None
    intent_hash: Optional[str] = None


class SentinelPayGateway:
    """
    Core security gateway protecting economic execution.
    Enforces that no payment transaction can be constructed or authorized
    without passing deterministic policy checks and semantic intent verification.
    """

    def __init__(
        self,
        policy_evaluator: Optional[PolicyEvaluator] = None,
        verifier: Optional[IntentVerifier] = None,
    ):
        self.policy_evaluator = policy_evaluator or PolicyEvaluator()
        self.verifier = verifier or LocalSemanticVerifier()

    @traceable(name="sentinelpay_gateway_process_payment_request", tags=["sentinelpay", "gateway"], metadata={"component": "gateway"})
    def process_payment_request(
        self,
        intent: PaymentIntent,
        policy: AgentPolicy,
    ) -> GatewayResponse:
        # Step 1: Normalize intent to canonical isolated form
        canonical = IntentNormalizer.normalize(intent, policy_id=policy.policy_id)
        i_hash = hash_intent(canonical)

        # Step 2: Deterministic Policy Evaluation (Hard Limits, Allowlists, Expiry)
        policy_result = self.policy_evaluator.evaluate(canonical, policy)
        if policy_result.decision != PolicyDecision.ALLOW:
            return GatewayResponse(
                status="denied",
                payment_intent_id=intent.intent_id,
                amount=intent.amount,
                currency=intent.currency,
                destination=intent.destination,
                reason=f"Policy violation: {policy_result.reason}",
                decision=PolicyDecision.DENY,
                canonical_intent=canonical,
                intent_hash=i_hash,
            )

        # Step 3: Semantic Verification (Task Scope Alignment & Injection Check)
        verif_result = self.verifier.verify(canonical, i_hash, policy)
        if not verif_result.approved or not verif_result.attestation:
            return GatewayResponse(
                status="denied",
                payment_intent_id=intent.intent_id,
                amount=intent.amount,
                currency=intent.currency,
                destination=intent.destination,
                reason=f"Verifier rejected intent: {verif_result.reason}",
                decision=PolicyDecision.DENY,
                canonical_intent=canonical,
                intent_hash=i_hash,
            )

        # Step 4: Record spend locally. Deliberately recorded at authorization
        # time rather than after settlement: if the payment later fails, this
        # over-counts, which denies too eagerly. The reverse ordering would
        # under-count and let a burst of concurrent requests slip past the cap.
        # The authoritative counter is the contract's on-chain `spend_today`.
        self.policy_evaluator.record_spend(canonical.agent_id, canonical.amount)

        # Step 5: Return Authorized Response with Signed Attestation
        return GatewayResponse(
            status="authorized",
            payment_intent_id=intent.intent_id,
            amount=intent.amount,
            currency=intent.currency,
            destination=intent.destination,
            reason="Authorized by SentinelPay policy engine and verifier.",
            decision=PolicyDecision.ALLOW,
            attestation=verif_result.attestation,
            canonical_intent=canonical,
            intent_hash=i_hash,
        )
