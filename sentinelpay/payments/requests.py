"""Payment request models."""

from typing import Optional

from pydantic import BaseModel, Field

from sentinelpay.verifier.attestation import Attestation


class PaymentRequirement(BaseModel):
    """Payment requirements returned by an x402 paid resource."""

    scheme: str = "algorand"
    network: str = "testnet"
    asset: str = "uALGO"
    amount: int = Field(..., gt=0, description="Price in micro-units. Must be positive.")
    pay_to: str
    resource_id: str
    description: Optional[str] = None


class PaymentExecutionRequest(BaseModel):
    """Request to settle payment through atomic group with attestation."""
    requirement: PaymentRequirement
    attestation: Attestation
    sender_address: str


class PaymentExecutionResult(BaseModel):
    """Outcome of payment settlement."""
    success: bool
    tx_id: Optional[str] = None
    group_id: Optional[str] = None
    settlement_status: str
    error_message: Optional[str] = None
