"""Cryptographic hashing for canonical intents."""

import hashlib
import json
from sentinelpay.intent.models import CanonicalIntent


def hash_intent(canonical_intent: CanonicalIntent) -> str:
    """
    Produces deterministic SHA-256 hex digest of the canonical intent.
    Sorts dictionary keys to guarantee reproducible serialization.
    """
    serialized = json.dumps(
        canonical_intent.canonical_dict(),
        sort_keys=True,
        separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(serialized).hexdigest()
