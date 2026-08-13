"""x402 protocol challenge and settlement handler."""

import base64
import json
import uuid
from typing import Dict, Any, Optional, Union
from pydantic import BaseModel
from sentinelpay.payments.requests import PaymentRequirement, PaymentExecutionResult
from sentinelpay.verifier.attestation import Attestation, AttestationSigner


class X402Challenge(BaseModel):
    """x402 challenge representation."""
    status_code: int = 402
    header_name: str = "WWW-Authenticate"
    header_value: str
    requirement: PaymentRequirement

    @classmethod
    def create(cls, requirement: PaymentRequirement) -> "X402Challenge":
        header_val = f'x402 scheme="{requirement.scheme}", network="{requirement.network}", pay_to="{requirement.pay_to}", amount="{requirement.amount}", asset="{requirement.asset}", resource="{requirement.resource_id}"'
        return cls(
            header_value=header_val,
            requirement=requirement,
        )


class X402PaymentHandler:
    """
    Handles parsing x402 headers, constructing payment settlement proofs,
    and verifying atomic group payment conditions against SentinelPay contract invariants.
    """

    @staticmethod
    def parse_402_response(headers: Dict[str, str], body: Optional[Dict[str, Any]] = None) -> Optional[PaymentRequirement]:
        """Parses payment requirement from HTTP 402 response headers or JSON body."""
        if body and "payment_requirements" in body:
            req_data = body["payment_requirements"]
            return PaymentRequirement(**req_data)
        
        # Fallback to WWW-Authenticate or custom x402 header
        auth_header = headers.get("www-authenticate") or headers.get("WWW-Authenticate") or headers.get("x-payment-required")
        if not auth_header and body:
            try:
                return PaymentRequirement(**body)
            except Exception:
                pass
        return None

    @staticmethod
    def construct_settlement_proof(attestation: Union[Attestation, Dict[str, Any]], tx_id: str, group_id: str) -> str:
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
        consumed_nonces: set,
    ) -> (bool, str, Optional[Attestation]):
        """
        Server-side validation of incoming payment proof:
        Ensures settlement proof contains valid signed attestation matching requirement and unconsumed nonce.
        """
        if not payment_proof_header.startswith("SentinelPay-AVM "):
            return False, "Invalid authorization scheme; SentinelPay-AVM required.", None

        encoded = payment_proof_header.split(" ", 1)[1]
        try:
            payload = json.loads(base64.b64decode(encoded).decode("utf-8"))
            attestation_data = payload.get("attestation")
            if not attestation_data:
                return False, "Missing attestation in settlement proof.", None

            attestation = Attestation(**attestation_data)

            # 1. Cryptographic signature check
            if not AttestationSigner.verify_attestation(attestation, verifier_public_key):
                return False, "Attestation signature verification failed.", None

            # 2. Replay check
            if attestation.nonce in consumed_nonces:
                return False, f"Attestation nonce {attestation.nonce} has already been consumed (replay detected).", None

            # 3. Destination match
            if attestation.destination != expected_requirement.pay_to:
                return False, f"Destination mismatch: expected {expected_requirement.pay_to}, got {attestation.destination}", None

            # 4. Amount match
            if attestation.amount != expected_requirement.amount:
                return False, f"Amount mismatch: expected {expected_requirement.amount}, got {attestation.amount}", None

            # 5. Currency match
            if attestation.currency.upper() != expected_requirement.asset.upper():
                return False, f"Asset mismatch: expected {expected_requirement.asset}, got {attestation.currency}", None

            # Mark nonce as consumed
            consumed_nonces.add(attestation.nonce)
            return True, "Settlement proof and authorization verified successfully.", attestation
        except Exception as e:
            return False, f"Failed to decode or verify settlement proof: {str(e)}", None
