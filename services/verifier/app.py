"""
SentinelPay Verifier Service.
Exposes REST endpoints to normalize, verify, and cryptographically sign payment attestations.
"""

from fastapi import FastAPI, HTTPException, status
from pydantic import BaseModel

from sentinelpay.intent.models import PaymentIntent, CanonicalIntent
from sentinelpay.policy.models import AgentPolicy
from sentinelpay.gateway.middleware import SentinelPayGateway, GatewayResponse
from sentinelpay.config import settings

app = FastAPI(
    title="SentinelPay Verifier Service",
    version="0.1.0",
    description="Independent verification and attestation issuance node for SentinelPay.",
)

gateway = SentinelPayGateway()


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
def verify_payment(req: VerificationRequest):
    """
    Evaluates payment intent against policy and returns authorization or denial.
    """
    response = gateway.process_payment_request(req.intent, req.policy)
    return response


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=settings.VERIFIER_PORT)
