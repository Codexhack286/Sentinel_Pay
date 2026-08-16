"""On-chain settlement verification for the protected resource.

The resource server used to accept a payment proof on the strength of a verifier
signature alone. That checks an *authorization was issued*, not that a payment
*settled* — a compromised client could replay a signed attestation at the HTTP
layer without ever broadcasting anything, and the server would serve the data.

The binding used here is the contract's own nonce box:

    the nonce box exists  <=>  validate_and_pay ran and approved

and `validate_and_pay` only approves inside an atomic group whose payment leg
matched the signed destination, amount and expiry (contracts/pyteal_contract.py,
invariants 4-8). So a single box lookup transitively proves the payment settled
with exactly the authorized terms. No indexer, no group reconstruction, one call.

A bare payment therefore fails here by construction: it has no application call,
so no box is ever written.

What the box does NOT prove is that *this* HTTP request is the first to present
the authorization — the box says "consumed once, ever". Serve-once is a separate
concern, handled by the caller's `consumed_nonces` set.
"""

from typing import Optional, Protocol, Tuple

from sentinelpay.verifier.attestation import Attestation


class ChainUnavailable(RuntimeError):
    """The chain could not be consulted. Never treat this as 'not settled'."""


class ChainReader(Protocol):
    """Minimal chain access the settlement check needs.

    A protocol rather than a concrete client so tests can substitute a fake and
    the offline suite stays network-free.
    """

    def nonce_consumed(self, app_id: int, nonce: bytes) -> bool:
        """True if the SentinelPay app holds a box under `nonce`."""
        ...


class AlgodChainReader:
    """ChainReader backed by an algod REST client."""

    def __init__(self, client):
        self._client = client

    def nonce_consumed(self, app_id: int, nonce: bytes) -> bool:
        try:
            self._client.application_box_by_name(app_id, nonce)
            return True
        except Exception as e:
            # algod answers 404 for a box that does not exist. Anything else is
            # an availability problem and must not be read as "not settled",
            # which would silently turn an outage into an open door.
            if _is_not_found(e):
                return False
            raise ChainUnavailable(f"algod box lookup failed: {e}") from e


def _is_not_found(exc: Exception) -> bool:
    code = getattr(exc, "code", None)
    if code == 404:
        return True
    text = str(exc).lower()
    return "box not found" in text or "no such box" in text or "404" in text


def verify_settled_on_chain(
    attestation: Attestation,
    app_id: int,
    chain: Optional[ChainReader],
    *,
    required: bool = True,
) -> Tuple[bool, str]:
    """Check that this authorization was consumed by the contract on-chain.

    With `required=False` (no app deployed yet) the check is skipped and the
    caller is told so, rather than being allowed to believe it passed.
    """
    if not required:
        return True, "On-chain settlement check skipped: no SENTINELPAY_APP_ID configured."
    if not app_id:
        return False, "On-chain settlement is required but SENTINELPAY_APP_ID is not set."
    if chain is None:
        return False, "On-chain settlement is required but no chain reader is configured."

    try:
        consumed = chain.nonce_consumed(app_id, attestation.nonce_bytes())
    except ChainUnavailable as e:
        # Fail closed. An unreachable chain means we cannot prove settlement,
        # and an unprovable payment must not unlock a paid resource.
        return False, f"Cannot confirm settlement, refusing to serve: {e}"

    if not consumed:
        return False, (
            "No SentinelPay authorization was consumed on-chain for this attestation. "
            "The payment either never settled or was submitted without the required "
            f"validate_and_pay call to app {app_id}."
        )
    return True, f"Settlement confirmed on-chain: nonce consumed by app {app_id}."
