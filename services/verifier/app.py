"""
SentinelPay Verifier Service.
Exposes REST endpoints to normalize, verify, and cryptographically sign payment
attestations.
"""

from fastapi import FastAPI
from pydantic import BaseModel

from sentinelpay.config import settings
from sentinelpay.gateway.middleware import GatewayResponse, SentinelPayGateway
from sentinelpay.intent.models import PaymentIntent
from sentinelpay.keys import load_signer
from sentinelpay.policy.models import AgentPolicy
from sentinelpay.tracing import traceable
from sentinelpay.verifier.verifier import LocalSemanticVerifier

app = FastAPI(
    title="SentinelPay Verifier Service",
    version="0.1.0",
    description="Independent verification and attestation issuance node for SentinelPay.",
)

# Same configured identity the resource server validates against — without this
# the two services mint independent keys and can never interoperate.
gateway = SentinelPayGateway(verifier=LocalSemanticVerifier(signer=load_signer()))


class VerificationRequest(BaseModel):
    intent: PaymentIntent
    policy: AgentPolicy


@app.get("/")
def health():
    return {
        "status": "online",
        "service": "SentinelPay Verifier",
        "public_key": gateway.verifier.public_key_b64,
    }


@app.post("/verify", response_model=GatewayResponse)
@traceable(name="verifier_service_verify_payment", tags=["sentinelpay", "service"], metadata={"component": "verifier_service"})
def verify_payment(req: VerificationRequest) -> GatewayResponse:
    """Evaluate a payment intent against policy and return authorization or denial."""
    return gateway.process_payment_request(req.intent, req.policy)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=settings.VERIFIER_PORT)
