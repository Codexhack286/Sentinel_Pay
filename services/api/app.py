"""
x402 Paid Resource API Server.
Implements HTTP 402 Payment Required challenge and verifies SentinelPay-AVM settlement proofs.
"""

from typing import Dict, Any, Optional
from fastapi import FastAPI, Header, HTTPException, Response, status
from pydantic import BaseModel

from sentinelpay.payments.requests import PaymentRequirement
from sentinelpay.payments.x402 import X402Challenge, X402PaymentHandler
from sentinelpay.verifier.attestation import AttestationSigner
from sentinelpay.config import settings

app = FastAPI(
    title="SentinelPay x402 Paid Resource Endpoint",
    version="0.1.0",
    description="Sample x402 API demonstrating SentinelPay Algorand authorization enforcement.",
)

# Simulated server state
DEMO_PAY_TO_ADDRESS = "RESOURCE_OWNER_ALGORAND_ADDRESS_AAAAAAAAAAAAAAAAAAAAAAAAAAAA"
DEMO_PRICE_UALGO = 100000  # 0.1 ALGO
DEMO_RESOURCE_ID = "energy-dataset-2026"

# Shared signer for local testing if not configured
_default_signer = AttestationSigner()
SERVER_VERIFIER_PUBLIC_KEY = settings.VERIFIER_PUBLIC_KEY or _default_signer.public_key_b64
_consumed_nonces = set()


@app.get("/")
def health():
    return {
        "status": "online",
        "service": "SentinelPay x402 Resource Server",
        "resource_endpoint": "/paid-dataset",
        "verifier_public_key": SERVER_VERIFIER_PUBLIC_KEY,
    }


@app.get("/paid-dataset")
def get_paid_dataset(
    authorization: Optional[str] = Header(None, alias="Authorization"),
    x_payment: Optional[str] = Header(None, alias="X-Payment"),
):
    """
    Protected x402 dataset endpoint.
    If no valid payment proof is provided, returns HTTP 402 with challenge.
    """
    requirement = PaymentRequirement(
        scheme="algorand",
        network="testnet",
        asset="uALGO",
        amount=DEMO_PRICE_UALGO,
        pay_to=DEMO_PAY_TO_ADDRESS,
        resource_id=DEMO_RESOURCE_ID,
        description="2026 Global Renewable Energy and Solar Grid Historical Dataset",
    )

    proof = authorization or x_payment
    if not proof:
        challenge = X402Challenge.create(requirement)
        return Response(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            content=requirement.model_dump_json(),
            media_type="application/json",
            headers={"WWW-Authenticate": challenge.header_value},
        )

    # Validate SentinelPay settlement proof
    valid, reason, attestation = X402PaymentHandler.verify_settlement_proof(
        payment_proof_header=proof,
        expected_requirement=requirement,
        verifier_public_key=SERVER_VERIFIER_PUBLIC_KEY,
        consumed_nonces=_consumed_nonces,
    )

    if not valid:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Payment settlement rejected by SentinelPay rule: {reason}",
        )

    # Payment verified! Serve paid data
    return {
        "status": "success",
        "resource_id": DEMO_RESOURCE_ID,
        "message": "x402 payment validated through SentinelPay on Algorand.",
        "attestation_id": attestation.attestation_id,
        "data": {
            "title": "2026 Global Solar Market Report",
            "capacity_gw": 1820.5,
            "annual_growth_pct": 24.3,
            "confidential_metrics": [
                {"region": "APAC", "efficiency_pct": 22.8},
                {"region": "EMEA", "efficiency_pct": 21.9},
                {"region": "Americas", "efficiency_pct": 23.1},
            ],
        },
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=settings.API_PORT)
