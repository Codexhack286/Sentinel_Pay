"""Intent normalizer that isolates secure fields from raw agent proposals."""

from typing import Optional

from sentinelpay.intent.models import CanonicalIntent, PaymentIntent

# Bound every free-text field the verifier will read. A compromised agent must
# not be able to smuggle a whole injected web page into the verifier's context.
MAX_TEXT_FIELD_LEN = 256


class IntentNormalizer:
    """Normalizes raw payment intents into canonical security-isolated intents."""

    @staticmethod
    def normalize(intent: PaymentIntent, policy_id: Optional[str] = None) -> CanonicalIntent:
        """
        Extract only required authorization fields and sanitize strings.
        Discards arbitrary large payloads, webpage bodies, or injection vectors
        carried in ``metadata``.
        """
        return CanonicalIntent(
            version="1.0",
            policy_id=policy_id or intent.policy_id,
            agent_id=intent.agent_id.strip(),
            declared_goal=intent.declared_goal.strip()[:MAX_TEXT_FIELD_LEN],
            task_scope=intent.task_scope.strip()[:MAX_TEXT_FIELD_LEN],
            tool_name=intent.tool_name.strip(),
            resource_id=intent.resource.strip()[:MAX_TEXT_FIELD_LEN],
            destination=intent.destination.strip(),
            amount=intent.amount,
            currency=intent.currency.strip().upper(),
            timestamp=intent.timestamp,
            expiry=intent.expiry,
        )
