"""Attestation models and cryptographic signing/verification.

Two signing encodings exist, deliberately:

1. ``signing_bytes()`` — canonical JSON. Signed with ``signature``. Consumed by
   off-chain verifiers (the x402 resource server) which can parse JSON cheaply.

2. ``avm_signing_bytes()`` — a fixed-layout 120-byte binary blob. Signed with
   ``avm_signature``. Consumed by the Algorand contract, which cannot parse
   JSON. Every field the contract enforces lives at a constant offset so TEAL
   can ``extract`` it directly.

The fixed layout is what makes the on-chain check sound: the contract derives
destination/amount/nonce/expiry *from the signed bytes themselves* instead of
trusting separate, unsigned application arguments.

AVM blob layout (little of it is optional — offsets are load-bearing):

    offset  len  field
    0       8    magic ``SPAYv1\\x00\\x00``  (domain separation)
    8       32   destination   (raw Algorand public key)
    40      8    amount        (big-endian uint64, micro-units)
    48      32   nonce32       (replay key; also the contract's box key)
    80      8    expires_at    (big-endian uint64, unix seconds)
    88      32   intent_hash32 (binding to the canonical intent)
    ---     ---
    120          total
"""

import base64
import hashlib
import json
import secrets
import time
from typing import Optional

from cryptography.hazmat.primitives.asymmetric import ed25519
from pydantic import BaseModel, Field

AVM_MAGIC = b"SPAYv1\x00\x00"
AVM_BLOB_LEN = 120

AVM_OFFSET_DESTINATION = 8
AVM_OFFSET_AMOUNT = 40
AVM_OFFSET_NONCE = 48
AVM_OFFSET_EXPIRES_AT = 80
AVM_OFFSET_INTENT_HASH = 88


def to_32_bytes(value: str) -> bytes:
    """Coerce an arbitrary identifier string to exactly 32 bytes.

    A 64-character hex string is decoded as-is (so a real SHA-256 intent hash
    survives round-tripping); anything else is hashed. Deterministic either
    way, which is all the contract needs.
    """
    if len(value) == 64:
        try:
            return bytes.fromhex(value)
        except ValueError:
            pass
    return hashlib.sha256(value.encode("utf-8")).digest()


def decode_algorand_address(address: str) -> bytes:
    """Return the raw 32-byte public key behind a base32 Algorand address.

    Raises ValueError for anything that is not a well-formed address. Callers
    that build AVM blobs must use real addresses; placeholder strings used in
    off-chain unit tests deliberately fail here rather than silently producing
    a blob the contract could never match.
    """
    from algosdk.encoding import decode_address, is_valid_address

    if not is_valid_address(address):
        raise ValueError(
            f"{address!r} is not a valid Algorand address; an AVM attestation "
            "blob can only be built for a real on-chain destination."
        )
    return decode_address(address)


class Attestation(BaseModel):
    """Cryptographically signed authorization object."""

    attestation_id: str = Field(default_factory=lambda: f"attest_{secrets.token_hex(6)}")
    intent_hash: str
    task_scope_hash: str = ""
    agent_id: str
    policy_id: str
    tool_name: str
    destination: str
    amount: int
    currency: str
    nonce: str = Field(default_factory=lambda: f"nonce_{secrets.token_hex(32)}")
    issued_at: int = Field(default_factory=lambda: int(time.time()))
    expires_at: int = Field(default_factory=lambda: int(time.time()) + 300)
    decision: str = "ALLOW"
    verifier_id: str = "sentinelpay_verifier_1"
    signature: str = ""
    avm_signature: str = ""

    def signing_bytes(self) -> bytes:
        """Deterministic JSON byte representation of the fields to sign."""
        payload = {
            "attestation_id": self.attestation_id,
            "intent_hash": self.intent_hash,
            "task_scope_hash": self.task_scope_hash,
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

    def nonce_bytes(self) -> bytes:
        """32-byte replay key derived from the nonce. Also the contract box key."""
        return to_32_bytes(self.nonce)

    def avm_signing_bytes(self) -> bytes:
        """Fixed-layout blob the Algorand contract verifies and parses."""
        if self.amount < 0 or self.amount >= 2**64:
            raise ValueError(f"amount {self.amount} does not fit in a uint64")
        blob = (
            AVM_MAGIC
            + decode_algorand_address(self.destination)
            + self.amount.to_bytes(8, "big")
            + self.nonce_bytes()
            + max(self.expires_at, 0).to_bytes(8, "big")
            + to_32_bytes(self.intent_hash)
        )
        assert len(blob) == AVM_BLOB_LEN, "AVM blob layout drifted from the contract"
        return blob

    def is_expired(self, now: Optional[int] = None) -> bool:
        return (now if now is not None else int(time.time())) >= self.expires_at


class AttestationSigner:
    """Manages the Ed25519 keypair used to sign attestations."""

    def __init__(self, private_key: Optional[ed25519.Ed25519PrivateKey] = None):
        self._private_key = private_key or ed25519.Ed25519PrivateKey.generate()
        self._public_key = self._private_key.public_key()

    @property
    def public_key_b64(self) -> str:
        return base64.b64encode(self._public_key.public_bytes_raw()).decode("utf-8")

    @property
    def private_key_b64(self) -> str:
        """Base64 seed. Only ever written to .env — never logged, never committed."""
        return base64.b64encode(self._private_key.private_bytes_raw()).decode("utf-8")

    def sign(self, attestation: Attestation) -> Attestation:
        """Sign the JSON payload, and the AVM blob when the destination is on-chain.

        Off-chain-only tests and demos use placeholder destinations that have no
        AVM representation; those get a JSON signature only, and any attempt to
        settle them on Algorand fails at the contract, which is the correct
        outcome.
        """
        attestation.signature = base64.b64encode(
            self._private_key.sign(attestation.signing_bytes())
        ).decode("utf-8")
        try:
            avm_bytes = attestation.avm_signing_bytes()
        except ValueError:
            attestation.avm_signature = ""
        else:
            attestation.avm_signature = base64.b64encode(
                self._private_key.sign(avm_bytes)
            ).decode("utf-8")
        return attestation

    @staticmethod
    def _verify_raw(message: bytes, signature_b64: str, public_key_b64: str) -> bool:
        try:
            pub_key = ed25519.Ed25519PublicKey.from_public_bytes(
                base64.b64decode(_pad_b64(public_key_b64))
            )
            pub_key.verify(base64.b64decode(_pad_b64(signature_b64)), message)
            return True
        except Exception:
            return False

    @staticmethod
    def verify_attestation(attestation: Attestation, public_key_b64: str) -> bool:
        """Verify the JSON signature."""
        return AttestationSigner._verify_raw(
            attestation.signing_bytes(), attestation.signature, public_key_b64
        )

    @staticmethod
    def verify_avm_attestation(attestation: Attestation, public_key_b64: str) -> bool:
        """Verify the AVM blob signature — the off-chain mirror of the contract check."""
        if not attestation.avm_signature:
            return False
        try:
            avm_bytes = attestation.avm_signing_bytes()
        except ValueError:
            return False
        return AttestationSigner._verify_raw(
            avm_bytes, attestation.avm_signature, public_key_b64
        )


def _pad_b64(value: str) -> str:
    """Restore base64 padding that some .env parsers strip from values."""
    return value + "=" * (-len(value) % 4)
