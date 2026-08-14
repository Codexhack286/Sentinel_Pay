"""Intent normalizer that isolates secure fields from raw agent proposals."""

from sentinelpay.intent.models import PaymentIntent, CanonicalIntent


class IntentNormalizer:
    """Normalizes raw payment intents into canonical security-isolated intents."""

    @staticmethod
    def normalize(intent: PaymentIntent, policy_id: str = None) -> CanonicalIntent:
        """
        Extract only required authorization fields and sanitize strings.
        Discards arbitrary large payloads, webpage bodies, or injection vectors.
        """
        return CanonicalIntent(
            version="1.0",
            policy_id=policy_id or intent.policy_id,
            agent_id=intent.agent_id.strip(),
            declared_goal=intent.declared_goal.strip()[:256],  # bounded length
            tool_name=intent.tool_name.strip(),
            resource_id=intent.resource.strip()[:256],
            destination=intent.destination.strip(),
            amount=intent.amount,
            currency=intent.currency.strip().upper(),
            timestamp=intent.timestamp,
            expiry=intent.expiry,
        )
