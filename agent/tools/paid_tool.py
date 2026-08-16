"""Protected paid tool that routes payments through SentinelPay gateway."""

from typing import Dict, Any, Optional
from sentinelpay.intent.models import PaymentIntent
from sentinelpay.policy.models import AgentPolicy
from sentinelpay.gateway.middleware import SentinelPayGateway, GatewayResponse


class PaidResearchTool:
    """
    Paid research tool that interacts with x402 endpoints.
    Never holds unrestricted wallet signing keys; requests payment authorization through SentinelPay.
    """

    def __init__(self, gateway: Optional[SentinelPayGateway] = None, policy: Optional[AgentPolicy] = None):
        self.name = "paid_research"
        self.description = "Accesses high-value paid research datasets via x402 payment."
        self.gateway = gateway
        self.policy = policy

    def request_payment_intent(
        self,
        agent_id: str,
        declared_goal: str,
        amount: int,
        destination: str,
        task_scope: str = "",
        resource: str = "energy-dataset-2026",
        currency: str = "uALGO",
    ) -> Dict[str, Any]:
        """
        Creates a structured payment intent.
        If no gateway is attached (initial scaffold mode), returns 'authorization_required' placeholder.
        When gateway is present, evaluates authorization and returns signed attestation or denial.
        """
        intent = PaymentIntent(
            agent_id=agent_id,
            declared_goal=declared_goal,
            task_scope=task_scope,
            tool_name=self.name,
            resource=resource,
            destination=destination,
            amount=amount,
            currency=currency,
        )

        if not self.gateway or not self.policy:
            return {
                "status": "authorization_required",
                "payment_intent_id": intent.intent_id,
                "amount": intent.amount,
                "currency": intent.currency,
                "destination": intent.destination,
                "reason": "Awaiting SentinelPay policy evaluation",
            }

        response: GatewayResponse = self.gateway.process_payment_request(intent, self.policy)
        return response.model_dump()
