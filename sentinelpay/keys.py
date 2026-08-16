"""Loading the verifier signing identity from configuration.

Every SentinelPay process that issues or checks attestations must agree on one
Ed25519 identity. Before this module existed each process minted its own
ephemeral key at import time, so the resource server could never validate an
attestation the verifier service had signed, and restarting either process
silently invalidated every outstanding attestation.

Set ``VERIFIER_PRIVATE_KEY`` (and the matching ``VERIFIER_PUBLIC_KEY``) in
.env — generate them with ``uv run python scripts/gen_verifier_key.py``.
"""

import base64
import warnings
from typing import Optional

from cryptography.hazmat.primitives.asymmetric import ed25519

from sentinelpay.config import settings
from sentinelpay.verifier.attestation import AttestationSigner, _pad_b64


def signer_from_private_key_b64(private_key_b64: str) -> AttestationSigner:
    """Build a signer from a base64-encoded 32-byte Ed25519 seed."""
    raw = base64.b64decode(_pad_b64(private_key_b64))
    if len(raw) != 32:
        raise ValueError(
            f"VERIFIER_PRIVATE_KEY decodes to {len(raw)} bytes; expected a "
            "32-byte Ed25519 seed. Regenerate with scripts/gen_verifier_key.py."
        )
    return AttestationSigner(private_key=ed25519.Ed25519PrivateKey.from_private_bytes(raw))


def load_signer(*, required: bool = False) -> AttestationSigner:
    """Return the configured verifier signer.

    With ``required=True`` a missing key is a hard error — used by anything that
    touches the chain, where an ephemeral key would produce attestations the
    deployed contract can never validate. Otherwise a throwaway key is minted
    with a warning so local demos and tests still run out of the box.
    """
    configured = settings.VERIFIER_PRIVATE_KEY
    if configured:
        return signer_from_private_key_b64(configured)
    if required:
        raise RuntimeError(
            "VERIFIER_PRIVATE_KEY is not set. Run "
            "`uv run python scripts/gen_verifier_key.py` and add the printed "
            "values to .env before signing attestations for on-chain use."
        )
    warnings.warn(
        "VERIFIER_PRIVATE_KEY is not set; generating an ephemeral verifier key. "
        "Attestations signed with it are not verifiable by other processes or "
        "by the deployed Algorand contract.",
        RuntimeWarning,
        stacklevel=2,
    )
    return AttestationSigner()


def configured_public_key(fallback: Optional[AttestationSigner] = None) -> str:
    """Public key an off-chain verifier should check attestations against."""
    if settings.VERIFIER_PUBLIC_KEY:
        return settings.VERIFIER_PUBLIC_KEY
    if fallback is not None:
        return fallback.public_key_b64
    return load_signer().public_key_b64
