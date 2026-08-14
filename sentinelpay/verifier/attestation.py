"""Attestation models and cryptographic signing/verification."""

import base64
import json
import time
import uuid
from typing import Dict, Any, Optional
from pydantic import BaseModel, Field
from cryptography.hazmat.primitives.asymmetric import ed25519


class Attestation(BaseModel):
    """Cryptographically signed authorization object."""
    attestation_id: str = Field(default_factory=lambda: f"attest_{uuid.uuid4().hex[:12]}")
    intent_hash: str
    agent_id: str
    policy_id: str
    tool_name: str
    destination: str
    amount: int
    currency: str
    nonce: str = Field(default_factory=lambda: f"nonce_{uuid.uuid4().hex}")
    issued_at: int = Field(default_factory=lambda: int(time.time()))
    expires_at: int = Field(default_factory=lambda: int(time.time()) + 300)
    decision: str = "ALLOW"
    verifier_id: str = "sentinelpay_verifier_1"
    signature: str = ""

    def signing_bytes(self) -> bytes:
        """Deterministic byte representation of fields to sign."""
        payload = {
            "attestation_id": self.attestation_id,
            "intent_hash": self.intent_hash,
            "agent_id": self.agent_id,
            "policy_id": self.policy_id,
            "tool_name": self.tool_name,
            "destination": self.destination,
            "amount": self.amount,
            "currency": self.currency,
            "nonce": self.nonce,
            "issued_at": self.issued_at,
            "expires_at": self.expires_at,
            "decision": self.decision,
            "verifier_id": self.verifier_id,
        }
        return json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")


class AttestationSigner:
    """Manages Ed25519 keypair for signing attestations."""

    def __init__(self, private_key: Optional[ed25519.Ed25519PrivateKey] = None):
        self._private_key = private_key or ed25519.Ed25519PrivateKey.generate()
        self._public_key = self._private_key.public_key()

    @property
    def public_key_b64(self) -> str:
        raw_bytes = self._public_key.public_bytes_raw()
        return base64.b64encode(raw_bytes).decode("utf-8")

    def sign(self, attestation: Attestation) -> Attestation:
        """Sign attestation with Ed25519 private key."""
        data_to_sign = attestation.signing_bytes()
        sig_bytes = self._private_key.sign(data_to_sign)
        attestation.signature = base64.b64encode(sig_bytes).decode("utf-8")
        return attestation

    @staticmethod
    def verify_attestation(attestation: Attestation, public_key_b64: str) -> bool:
        """Verifies signature against public key."""
        try:
            pub_bytes = base64.b64decode(public_key_b64)
            pub_key = ed25519.Ed25519PublicKey.from_public_bytes(pub_bytes)
            sig_bytes = base64.b64decode(attestation.signature)
            pub_key.verify(sig_bytes, attestation.signing_bytes())
            return True
        except Exception:
            return False
