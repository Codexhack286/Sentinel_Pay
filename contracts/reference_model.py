"""
Pure-Python reference model of the SentinelPay AVM contract.

Deliberately not a deployable artifact — `contracts/pyteal_contract.py` is.
This model exists so the authorization invariants can be exercised in
milliseconds without a node, and so a reviewer can read the enforcement rules
without reading TEAL. It must stay behaviourally identical to the PyTeal
program; `contracts/tests/test_reference_model.py` and
`contracts/tests/test_pyteal_contract.py` both guard that.

Named `reference_model` rather than `sentinelpay` because the latter shadowed
the top-level `sentinelpay` package whenever `contracts/` landed on sys.path,
which broke `python contracts/compile.py` in a thoroughly confusing way.
"""

import time
from dataclasses import dataclass, field
from typing import Any, Dict, Optional, Set, Tuple

from sentinelpay.verifier.attestation import (
    AVM_BLOB_LEN,
    AVM_MAGIC,
    AVM_OFFSET_AMOUNT,
    AVM_OFFSET_DESTINATION,
    AVM_OFFSET_EXPIRES_AT,
    AVM_OFFSET_NONCE,
    AttestationSigner,
)

SELECTOR_VALIDATE_AND_PAY = "validate_and_pay"
ED25519_SIGNATURE_LEN = 64


@dataclass
class ContractState:
    """Simulated or on-chain state for the SentinelPay smart contract."""

    admin_address: str
    verifier_public_key_b64: str
    max_daily_spend: int
    current_daily_spend: int = 0
    consumed_nonces: Set[bytes] = field(default_factory=set)


@dataclass
class ParsedAuthorization:
    """Fields the contract reads out of the signed blob."""

    destination: bytes
    amount: int
    nonce: bytes
    expires_at: int


def parse_avm_blob(blob: bytes) -> ParsedAuthorization:
    """Decode the fixed-layout signed blob. Raises ValueError on any drift."""
    if len(blob) != AVM_BLOB_LEN:
        raise ValueError(f"blob is {len(blob)} bytes; expected {AVM_BLOB_LEN}")
    if blob[: len(AVM_MAGIC)] != AVM_MAGIC:
        raise ValueError("blob magic does not identify a SentinelPay authorization")
    return ParsedAuthorization(
        destination=blob[AVM_OFFSET_DESTINATION : AVM_OFFSET_DESTINATION + 32],
        amount=int.from_bytes(blob[AVM_OFFSET_AMOUNT : AVM_OFFSET_AMOUNT + 8], "big"),
        nonce=blob[AVM_OFFSET_NONCE : AVM_OFFSET_NONCE + 32],
        expires_at=int.from_bytes(blob[AVM_OFFSET_EXPIRES_AT : AVM_OFFSET_EXPIRES_AT + 8], "big"),
    )


class SentinelPayContractLogic:
    """
    Python reference model and validation logic for the SentinelPay AVM contract.
    Enforces on-chain invariants matching TEAL / PyTeal execution.
    """

    def __init__(self, state: ContractState):
        self.state = state

    def validate_atomic_group(
        self,
        payment_tx: Dict[str, Any],
        app_call_tx: Dict[str, Any],
        now: Optional[int] = None,
        group_size: int = 2,
    ) -> Tuple[bool, str]:
        """
        Execute the atomic group validation.

        ``app_call_tx["args"]`` is ``[selector, signed_blob, signature]`` — the
        same three arguments the deployed contract takes. Note what is *not*
        here: no separately supplied destination, amount or nonce. Those are
        read from the signed blob, so a caller has nothing to substitute.

        ``payment_tx`` mirrors gtxn[0]: ``receiver`` (raw 32 bytes), ``amount``,
        and optionally ``close_remainder_to`` / ``rekey_to``.
        """
        now = int(time.time()) if now is None else now

        args = app_call_tx.get("args", [])
        if len(args) < 3 or args[0] != SELECTOR_VALIDATE_AND_PAY:
            return False, "Invalid app call selector; expected 'validate_and_pay' with 3 args."

        blob, signature_b64 = args[1], args[2]
        try:
            parsed = parse_avm_blob(blob)
        except ValueError as e:
            return False, f"Malformed authorization blob: {e}"

        # Invariant 1: group shape.
        if group_size < 2:
            return False, f"Group size {group_size} is too small; expected at least 2."
        if payment_tx.get("type", "pay") != "pay":
            return False, "Transaction 0 is not a payment."
        if payment_tx.get("close_remainder_to"):
            return False, "Payment closes out the sender's account; rejected."
        if payment_tx.get("rekey_to"):
            return False, "Payment rekeys the sender's account; rejected."

        # Invariant 2: signature over the whole blob.
        if not AttestationSigner._verify_raw(
            blob, signature_b64, self.state.verifier_public_key_b64
        ):
            return False, "On-chain signature verification failed: invalid verifier signature."

        # Invariant 3: destination binding.
        if payment_tx.get("receiver") != parsed.destination:
            return False, (
                f"Destination mismatch: payment receiver {payment_tx.get('receiver')!r} "
                f"!= attested destination {parsed.destination!r}"
            )

        # Invariant 4: amount binding.
        if payment_tx.get("amount") != parsed.amount:
            return False, (
                f"Amount mismatch: payment amount {payment_tx.get('amount')} "
                f"!= attested amount {parsed.amount}"
            )

        # Invariant 5: expiry.
        if now >= parsed.expires_at:
            return False, f"Authorization expired at {parsed.expires_at} (now {now})."

        # Invariant 6: cumulative spend cap.
        projected = self.state.current_daily_spend + parsed.amount
        if projected > self.state.max_daily_spend:
            return False, f"Spend cap exceeded: {projected} > max limit {self.state.max_daily_spend}"

        # Invariant 7: replay.
        if parsed.nonce in self.state.consumed_nonces:
            return False, f"Replay rejected: nonce {parsed.nonce.hex()} has already been consumed."

        self.state.consumed_nonces.add(parsed.nonce)
        self.state.current_daily_spend = projected
        return True, "Atomic group and authorization validated successfully."

    def admin_reset_spend(self, sender: str) -> Tuple[bool, str]:
        """Reset the cumulative counter. Admin only — see the PyTeal docstring."""
        if sender != self.state.admin_address:
            return False, "Only the admin may reset the spend counter."
        self.state.current_daily_spend = 0
        return True, "Spend counter reset."
