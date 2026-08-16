"""
x402 Paid Resource API Server.

Implements the HTTP 402 Payment Required challenge and serves the protected
dataset only once two independent things hold:

  1. the presented attestation is validly signed, unexpired, and matches this
     resource's exact price and payee; and
  2. the corresponding authorization was consumed on-chain by the SentinelPay
     contract, which by the contract's invariants means a matching payment
     actually settled.

(2) is the part that makes this a paywall rather than a signature check. See
sentinelpay/payments/settlement.py.
"""

import logging
from typing import Optional, Set

from fastapi import FastAPI, Header, HTTPException, Response, status

from sentinelpay.config import settings
from sentinelpay.keys import configured_public_key, load_signer
from sentinelpay.payments.requests import PaymentRequirement
from sentinelpay.payments.settlement import (
    AlgodChainReader,
    ChainReader,
    verify_settled_on_chain,
)
from sentinelpay.payments.x402 import X402Challenge, X402PaymentHandler

logger = logging.getLogger(__name__)

app = FastAPI(
    title="SentinelPay x402 Paid Resource Endpoint",
    version="0.4.0",
    description="Sample x402 API demonstrating SentinelPay Algorand authorization enforcement.",
)

DEMO_RESOURCE_ID = "energy-dataset-2026"

# Falls back to an ephemeral key only when VERIFIER_PRIVATE_KEY is unset, which
# `load_signer` warns about. Exported so tests and single-process demos can sign
# with the identity this server checks against.
_default_signer = load_signer()
SERVER_VERIFIER_PUBLIC_KEY = configured_public_key(fallback=_default_signer)

# Serve-once guard. Distinct from the on-chain consumed-nonce record: the box
# proves the payment settled exactly once ever, this set stops the same settled
# authorization from being redeemed for the content twice. Process-local, so it
# resets on restart — acceptable because it cannot authorize anything, only
# withhold. The money side is authoritative on-chain.
_consumed_nonces: Set[str] = set()


def _build_chain_reader() -> Optional[ChainReader]:
    if not settings.SENTINELPAY_APP_ID:
        return None
    try:
        from algosdk.v2client import algod

        return AlgodChainReader(
            algod.AlgodClient(settings.ALGOD_TOKEN, settings.ALGOD_ADDRESS, headers={})
        )
    except Exception as e:  # pragma: no cover - only on a broken algosdk install
        logger.warning("Could not construct an algod client: %s", e)
        return None


# Rebindable so tests can inject a fake reader without a network.
chain_reader: Optional[ChainReader] = _build_chain_reader()


def settlement_required() -> bool:
    """On-chain proof is required whenever an app is actually deployed.

    With no SENTINELPAY_APP_ID the server runs in offline demo mode and says so
    in every response, rather than quietly accepting signature-only proofs while
    looking like it enforces settlement.
    """
    return bool(settings.SENTINELPAY_APP_ID)


def _requirement() -> PaymentRequirement:
    return PaymentRequirement(
        scheme="algorand",
        network="testnet",
        asset="uALGO",
        amount=settings.RESOURCE_PRICE_UALGO,
        pay_to=settings.RESOURCE_OWNER_ADDRESS,
        resource_id=DEMO_RESOURCE_ID,
        description="2026 Global Renewable Energy and Solar Grid Historical Dataset",
    )


@app.get("/")
def health():
    return {
        "status": "online",
        "service": "SentinelPay x402 Resource Server",
        "resource_endpoint": "/paid-dataset",
        "verifier_public_key": SERVER_VERIFIER_PUBLIC_KEY,
        "sentinelpay_app_id": settings.SENTINELPAY_APP_ID,
        "enforces_onchain_settlement": settlement_required(),
    }


@app.get("/paid-dataset")
def get_paid_dataset(
    authorization: Optional[str] = Header(None, alias="Authorization"),
    x_payment: Optional[str] = Header(None, alias="X-Payment"),
):
    """Protected x402 dataset endpoint."""
    requirement = _requirement()

    proof = authorization or x_payment
    if not proof:
        challenge = X402Challenge.create(requirement)
        return Response(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            content=requirement.model_dump_json(),
            media_type="application/json",
            headers={"WWW-Authenticate": challenge.header_value},
        )

    # Stage 1 — the authorization itself: signature, decision, expiry, and an
    # exact match against what this resource charges.
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

    # Stage 2 — did it actually settle? A signature proves an authorization was
    # issued, not that money moved.
    required = settlement_required()
    settled, settlement_reason = verify_settled_on_chain(
        attestation,
        app_id=settings.SENTINELPAY_APP_ID,
        chain=chain_reader,
        required=required,
    )
    if not settled:
        # Stage 1 consumed the nonce from the serve-once set. Put it back:
        # the resource was never served, so a genuine retry after the payment
        # confirms must not be locked out by this failed attempt.
        _consumed_nonces.discard(attestation.nonce)
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail=f"Payment not settled: {settlement_reason}",
        )

    return {
        "status": "success",
        "resource_id": DEMO_RESOURCE_ID,
        "message": "x402 payment validated through SentinelPay on Algorand.",
        "attestation_id": attestation.attestation_id,
        "settlement_verified": required,
        "settlement_detail": settlement_reason,
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
