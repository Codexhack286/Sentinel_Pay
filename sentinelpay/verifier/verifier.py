"""Verifier interface and local verifier implementations.

The verifier is *trusted but fallible*: it is the last soft check before an
attestation is signed, and it never gets to widen what the deterministic policy
engine and the on-chain contract already allow. Its job is narrow — decide
whether the declared goal genuinely belongs to the user-authorized task — and
its inputs are narrow to match: only canonical, length-bounded fields, never raw
tool output or fetched web content.
"""

import re
import time
from typing import Optional, Protocol, Set

from pydantic import BaseModel

from sentinelpay.intent.models import CanonicalIntent
from sentinelpay.policy.models import AgentPolicy, PolicyDecision
from sentinelpay.tracing import traceable
from sentinelpay.verifier.attestation import Attestation, AttestationSigner, to_32_bytes

# Phrases that only ever appear when something is trying to talk the agent out
# of its task. Keyword matching is a coarse first filter, not the security
# boundary — the policy engine and the contract are.
ADVERSARIAL_INDICATORS = (
    "system override",
    "ignore previous instructions",
    "ignore all instructions",
    "disregard previous",
    "send all funds",
    "drain wallet",
    "lockdown emergency transfer",
    "urgent security audit transfer",
    "attacker",
    "bypass policy",
    "override policy",
    "as an exception",
)

# Words that carry no topical signal, so they must not be what makes a proposed
# goal look aligned with the authorized task.
_STOPWORDS = frozenset(
    """
    a an and are as at be by for from has have in into is it its of on or that the
    their there these this to was were will with your you our we us do does did
    please immediately urgent now must should need needs required
    """.split()
)

_TOKEN_RE = re.compile(r"[a-z0-9]+")

# Fraction of the authorized task's meaningful words the declared goal must
# share before it counts as on-task.
#
# Was 0.2, which on a seven-word task scope required a single shared word — so
# "Purchase a premium energy trading subscription upgrade" counted as aligned
# with an energy research task on the strength of the word "energy" alone. At
# 0.34 the goal has to overlap the task in more than one place. Still coarse by
# design: this is a soft check that can only ever *deny*, and every hard limit
# lives in the policy engine and the contract.
DEFAULT_TASK_ALIGNMENT_RATIO = 0.34
MIN_OVERLAPPING_TERMS = 2


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


def tokenize(text: str) -> Set[str]:
    """Lowercase content words, stopwords removed."""
    return {t for t in _TOKEN_RE.findall(text.lower()) if t not in _STOPWORDS and len(t) > 2}


class LocalSemanticVerifier:
    """
    Zero-cost local verifier.
    Performs deterministic task alignment without requiring external paid LLM APIs.
    """

    def __init__(
        self,
        signer: Optional[AttestationSigner] = None,
        verifier_id: str = "sentinelpay_local_verifier",
        task_alignment_ratio: float = DEFAULT_TASK_ALIGNMENT_RATIO,
    ):
        self.signer = signer or AttestationSigner()
        self.verifier_id = verifier_id
        self.task_alignment_ratio = task_alignment_ratio

    @property
    def public_key_b64(self) -> str:
        return self.signer.public_key_b64

    def _deny(self, reason: str) -> VerificationResult:
        return VerificationResult(approved=False, decision=PolicyDecision.DENY, reason=reason)

    def _check_adversarial(self, intent: CanonicalIntent) -> Optional[str]:
        haystacks = (
            intent.declared_goal.lower(),
            intent.resource_id.lower(),
            intent.tool_name.lower(),
        )
        for indicator in ADVERSARIAL_INDICATORS:
            if any(indicator in field for field in haystacks):
                return f"Adversarial instruction or prompt injection detected: contains '{indicator}'."
        return None

    def _check_categories(self, intent: CanonicalIntent, policy: AgentPolicy) -> Optional[str]:
        """Match categories against the declared goal only.

        Matching against ``tool_name`` too used to make this check vacuous: a
        tool named ``paid_research`` satisfied the ``research`` category no
        matter what the agent claimed it was buying, so an off-task purchase
        sailed through. Only the goal — the thing the agent actually asserts
        about this payment — is evidence of category.
        """
        if not policy.allowed_categories:
            return None
        goal_lower = intent.declared_goal.lower()
        goal_tokens = tokenize(goal_lower)
        for category in policy.allowed_categories:
            category_lower = category.lower()
            if (
                category_lower in goal_tokens
                or f"{category_lower}s" in goal_tokens  # tolerate simple plurals
                or (" " in category_lower and category_lower in goal_lower)
            ):
                return None
        return (
            f"Declared task '{intent.declared_goal}' does not align with authorized "
            f"policy categories ({policy.allowed_categories})."
        )

    def _check_task_alignment(self, intent: CanonicalIntent) -> Optional[str]:
        """Require the declared goal to overlap the user-authorized task scope.

        This is the check that catches an agent which has been talked into a
        *plausible-sounding but different* purchase — the case keyword filters
        and category allowlists both miss.
        """
        if not intent.task_scope:
            return None
        scope_tokens = tokenize(intent.task_scope)
        if not scope_tokens:
            return None
        goal_tokens = tokenize(intent.declared_goal)
        overlap = scope_tokens & goal_tokens
        # Floor at two terms so a single incidental word shared with the task
        # cannot carry an otherwise unrelated purchase, however short the scope.
        required = max(
            min(MIN_OVERLAPPING_TERMS, len(scope_tokens)),
            int(len(scope_tokens) * self.task_alignment_ratio),
        )
        if len(overlap) >= required:
            return None
        return (
            f"Declared goal '{intent.declared_goal}' does not match the authorized "
            f"task scope '{intent.task_scope}' "
            f"({len(overlap)} shared terms, {required} required)."
        )

    @traceable(name="local_semantic_verifier_verify", tags=["sentinelpay", "verifier"], metadata={"component": "verifier", "verifier": "local_semantic"})
    def verify(
        self,
        intent: CanonicalIntent,
        intent_hash: str,
        policy: AgentPolicy,
    ) -> VerificationResult:
        if not intent.declared_goal.strip():
            return self._deny("Declared goal is empty; task alignment cannot be verified.")

        for check in (
            self._check_adversarial(intent),
            self._check_categories(intent, policy),
            self._check_task_alignment(intent),
        ):
            if check:
                return self._deny(check)

        # The attestation must never outlive the intent it authorizes, and must
        # respect the policy's lifetime cap even if the intent asked for longer.
        now = int(time.time())
        expires_at = min(intent.expiry, now + policy.max_intent_lifetime_seconds)
        if expires_at <= now:
            return self._deny("Intent expiry is in the past; no attestation issued.")

        attestation = Attestation(
            intent_hash=intent_hash,
            task_scope_hash=to_32_bytes(intent.task_scope).hex() if intent.task_scope else "",
            agent_id=intent.agent_id,
            policy_id=policy.policy_id,
            tool_name=intent.tool_name,
            destination=intent.destination,
            amount=intent.amount,
            currency=intent.currency,
            issued_at=now,
            expires_at=expires_at,
            decision="ALLOW",
            verifier_id=self.verifier_id,
        )

        return VerificationResult(
            approved=True,
            decision=PolicyDecision.ALLOW,
            reason="Semantic intent aligns with policy and declared task scope.",
            attestation=self.signer.sign(attestation),
        )
