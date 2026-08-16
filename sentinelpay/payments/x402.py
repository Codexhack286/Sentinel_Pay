"""x402 protocol challenge and settlement handler."""

import base64
import json
import re
import time
from typing import Any, Dict, Optional, Set, Tuple, Union

from pydantic import BaseModel

from sentinelpay.payments.requests import PaymentRequirement
from sentinelpay.verifier.attestation import Attestation, AttestationSigner

_HEADER_PARAM_RE = re.compile(r'(\w+)\s*=\s*"([^"]*)"')


class X402Challenge(BaseModel):
    """x402 challenge representation."""

    status_code: int = 402
    header_name: str = "WWW-Authenticate"
    header_value: str
    requirement: PaymentRequirement

    @classmethod
    def create(cls, requirement: PaymentRequirement) -> "X402Challenge":
        header_val = (
            f'x402 scheme="{requirement.scheme}", network="{requirement.network}", '
            f'pay_to="{requirement.pay_to}", amount="{requirement.amount}", '
            f'asset="{requirement.asset}", resource="{requirement.resource_id}"'
        )
        return cls(header_value=header_val, requirement=requirement)


class X402PaymentHandler:
    """
    Handles parsing x402 headers, constructing payment settlement proofs,
    and verifying atomic group payment conditions against SentinelPay contract invariants.
    """

    @staticmethod
    def parse_402_response(
        headers: Dict[str, str], body: Optional[Dict[str, Any]] = None
    ) -> Optional[PaymentRequirement]:
        """Parses payment requirement from HTTP 402 response headers or JSON body."""
        if body and "payment_requirements" in body:
            return PaymentRequirement(**body["payment_requirements"])

        if body:
            try:
                return PaymentRequirement(**body)
            except Exception:
                pass

        # Header fallback: `x402 scheme="...", pay_to="...", amount="...", ...`
        # Previously this branch read the header and then threw it away, so a
        # server that advertised requirements *only* via WWW-Authenticate looked
        # to the client like a server with no requirements at all.
        lowered = {k.lower(): v for k, v in headers.items()}
        auth_header = lowered.get("www-authenticate") or lowered.get("x-payment-required")
        if not auth_header:
            return None

        params = {k.lower(): v for k, v in _HEADER_PARAM_RE.findall(auth_header)}
        if "pay_to" not in params or "amount" not in params:
            return None
        try:
            return PaymentRequirement(
                scheme=params.get("scheme", "algorand"),
                network=params.get("network", "testnet"),
                asset=params.get("asset", "uALGO"),
                amount=int(params["amount"]),
                pay_to=params["pay_to"],
                resource_id=params.get("resource", ""),
            )
        except (ValueError, TypeError):
            return None

    @staticmethod
    def construct_settlement_proof(
        attestation: Union[Attestation, Dict[str, Any]], tx_id: str, group_id: str
    ) -> str:
        """Constructs Authorization/X-Payment header value with atomic group proof & attestation."""
        att_dict = attestation if isinstance(attestation, dict) else attestation.model_dump()
        payload = {
            "attestation": att_dict,
            "tx_id": tx_id,
            "group_id": group_id,
            "scheme": "algorand-sentinelpay",
        }
        encoded = base64.b64encode(json.dumps(payload).encode("utf-8")).decode("utf-8")
        return f"SentinelPay-AVM {encoded}"

    @staticmethod
    def verify_settlement_proof(
        payment_proof_header: str,
        expected_requirement: PaymentRequirement,
        verifier_public_key: str,
        consumed_nonces: Set[str],
        now: Optional[int] = None,
    ) -> Tuple[bool, str, Optional[Attestation]]:
        """
        Server-side validation of an incoming payment proof.

        Checks, in order: scheme, decodability, verifier signature, issuing
        decision, expiry, replay, then exact destination/amount/asset match
        against what this resource actually charges. The nonce is only marked
        consumed once every check has passed — a rejected proof must not be able
        to burn a nonce and lock out the legitimate retry.
        """
        if not payment_proof_header.startswith("SentinelPay-AVM "):
            return False, "Invalid authorization scheme; SentinelPay-AVM required.", None

        encoded = payment_proof_header.split(" ", 1)[1]
        try:
            payload = json.loads(base64.b64decode(encoded, validate=True).decode("utf-8"))
            attestation_data = payload.get("attestation")
            if not attestation_data:
                return False, "Missing attestation in settlement proof.", None
            attestation = Attestation(**attestation_data)
        except Exception as e:
            return False, f"Failed to decode or verify settlement proof: {e}", None

        if not AttestationSigner.verify_attestation(attestation, verifier_public_key):
            return False, "Attestation signature verification failed.", None

        if attestation.decision != "ALLOW":
            return False, f"Attestation carries a non-authorizing decision: {attestation.decision}.", None

        now = int(time.time()) if now is None else now
        if attestation.is_expired(now):
            return False, (
                f"Attestation expired {now - attestation.expires_at}s ago "
                f"(expires_at={attestation.expires_at})."
            ), None
        if attestation.issued_at > now + 60:
            return False, "Attestation is issued in the future; clock skew or forgery.", None

        if attestation.nonce in consumed_nonces:
            return False, f"Attestation nonce {attestation.nonce} has already been consumed (replay detected).", None

        if attestation.destination != expected_requirement.pay_to:
            return False, (
                f"Destination mismatch: expected {expected_requirement.pay_to}, "
                f"got {attestation.destination}"
            ), None

        if attestation.amount != expected_requirement.amount:
            return False, (
                f"Amount mismatch: expected {expected_requirement.amount}, got {attestation.amount}"
            ), None

        if attestation.currency.upper() != expected_requirement.asset.upper():
            return False, (
                f"Asset mismatch: expected {expected_requirement.asset}, got {attestation.currency}"
            ), None

        consumed_nonces.add(attestation.nonce)
        return True, "Settlement proof and authorization verified successfully.", attestation
