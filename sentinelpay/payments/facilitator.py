"""
Client for the GoPlausible Algorand x402-avm facilitator
(https://facilitator.goplausible.xyz).

RESOLVED RISK (see SentinelPay_Project_Review.docx Section 5, "Facilitator
single point of failure", and docs/status.md): the open question was whether
GoPlausible's facilitator supports atomic transaction groups containing more
than just the bare payment leg — i.e. whether our [payment, app-call] group
shape is compatible with their verify()/settle() flow.

Per GoPlausible's own protocol documentation (Algorand x402 Facilitator
README, "Transaction Group with composability" and "Algorand-Specific
Advantages" sections):
    - Atomic groups of up to 16 transactions are supported end-to-end.
    - `paymentGroup` is explicitly documented as extensible: "can include
      additional transactions beyond the payment and fee transactions,"
      naming "integrating with other smart contracts on Algorand" as a
      supported use case.
    - `verify()` decodes every transaction in the group, enforces group-ID
      consistency, and applies safety checks (no keyreg/rekey/closeRemainderTo)
      across the whole group, but only *requires* specific fields on the
      transaction at `paymentIndex` — it does not reject extra signed
      transactions from the client.
So: YES — SentinelPay's [payment, SentinelPay app-call] group fits the
facilitator's model. The app-call transaction is the client's own signed
transaction sitting alongside the payment at `paymentIndex`, same as any
other "additional transaction" the docs describe.

This client wraps the two core facilitator endpoints:
    POST /verify  - validate a signed payment group before settlement
    POST /settle  - broadcast (and, if using fee abstraction, co-sign) the group

It intentionally does NOT depend on the `x402-avm` PyPI package so the core
SentinelPay engine has no required third-party payment SDK; swap in the
official SDK (`pip install x402-avm[avm,httpx]`) if/when the team wants richer
type coverage than this thin client provides.
"""

from typing import Any, Dict, List, Optional

import httpx
from pydantic import BaseModel, ConfigDict, Field

FACILITATOR_BASE_URL = "https://facilitator.goplausible.xyz"

ALGORAND_TESTNET_CAIP2 = "algorand:SGO1GKSzyE7IEPItTxCByw9x8FmnrCDexi9/cOUJOiI="
ALGORAND_MAINNET_CAIP2 = "algorand:wGHE2Pwdvd7S12BL5FaOP20EGYesN73ktiC1qzkkit8="

MAX_ATOMIC_GROUP_SIZE = 16


class PaymentRequirementsV2(BaseModel):
    """x402 V2 payment requirements, as returned in the initial 402 challenge."""
    model_config = ConfigDict(populate_by_name=True)

    scheme: str = "exact"
    network: str = ALGORAND_TESTNET_CAIP2
    asset: str
    amount: str
    pay_to: str = Field(alias="payTo")
    max_timeout_seconds: int = Field(default=60, alias="maxTimeoutSeconds")
    extra: Dict[str, Any] = {}


class ExactAvmPayload(BaseModel):
    """
    The X-PAYMENT payload body. `payment_group` holds base64-encoded msgpack
    transactions forming one atomic group; `payment_index` says which one is
    the actual payment leg. SentinelPay adds its own app-call transaction as
    one of the "additional transactions" the group format explicitly allows
    (see module docstring) — its index is tracked separately by the caller,
    the facilitator does not need to know about it.
    """
    payment_group: List[str]
    payment_index: int = 0


class XPaymentHeader(BaseModel):
    x402_version: int = 2
    scheme: str = "exact"
    network: str = ALGORAND_TESTNET_CAIP2
    payload: ExactAvmPayload

    def to_header_dict(self) -> Dict[str, Any]:
        return {
            "x402Version": self.x402_version,
            "scheme": self.scheme,
            "network": self.network,
            "payload": {
                "paymentGroup": self.payload.payment_group,
                "paymentIndex": self.payload.payment_index,
            },
        }


class FacilitatorVerifyResult(BaseModel):
    is_valid: bool
    invalid_reason: Optional[str] = None
    raw: Dict[str, Any] = {}


class FacilitatorSettleResult(BaseModel):
    success: bool
    transaction: Optional[str] = None  # settled tx ID
    network: Optional[str] = None
    error: Optional[str] = None
    raw: Dict[str, Any] = {}


class GoPlausibleFacilitatorClient:
    """Thin HTTP client for the public GoPlausible x402-avm facilitator."""

    def __init__(self, base_url: str = FACILITATOR_BASE_URL, timeout: float = 15.0):
        self.base_url = base_url.rstrip("/")
        self._client = httpx.AsyncClient(base_url=self.base_url, timeout=timeout)

    async def health(self) -> Dict[str, Any]:
        resp = await self._client.get("/health")
        resp.raise_for_status()
        return resp.json()

    async def supported(self) -> Dict[str, Any]:
        """Schemes and networks the facilitator currently accepts."""
        resp = await self._client.get("/supported")
        resp.raise_for_status()
        return resp.json()

    async def verify(
        self,
        x_payment: XPaymentHeader,
        requirements: PaymentRequirementsV2,
    ) -> FacilitatorVerifyResult:
        """
        Validate a signed payment group before settlement. Does not broadcast
        anything on-chain; the facilitator simulates the group against algod.
        """
        body = {
            "x402Version": x_payment.x402_version,
            "paymentPayload": x_payment.to_header_dict(),
            "paymentRequirements": requirements.model_dump(by_alias=True),
        }
        resp = await self._client.post("/verify", json=body)
        resp.raise_for_status()
        data = resp.json()
        return FacilitatorVerifyResult(
            is_valid=bool(data.get("isValid")),
            invalid_reason=data.get("invalidReason"),
            raw=data,
        )

    async def settle(
        self,
        x_payment: XPaymentHeader,
        requirements: PaymentRequirementsV2,
    ) -> FacilitatorSettleResult:
        """
        Re-verify, co-sign any facilitator-managed legs (e.g. fee payer), and
        broadcast the full atomic group to Algorand. Returns the settled
        payment transaction ID on success.
        """
        body = {
            "x402Version": x_payment.x402_version,
            "paymentPayload": x_payment.to_header_dict(),
            "paymentRequirements": requirements.model_dump(by_alias=True),
        }
        resp = await self._client.post("/settle", json=body)
        resp.raise_for_status()
        data = resp.json()
        return FacilitatorSettleResult(
            success=bool(data.get("success")),
            transaction=data.get("transaction"),
            network=data.get("network"),
            error=data.get("error"),
            raw=data,
        )

    async def aclose(self) -> None:
        await self._client.aclose()

    async def __aenter__(self) -> "GoPlausibleFacilitatorClient":
        return self

    async def __aexit__(self, *exc_info: Any) -> None:
        await self.aclose()
