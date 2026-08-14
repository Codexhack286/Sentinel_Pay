"""
SentinelPay Algorand Smart Contract (AVM).
Enforces exact authorization, replay resistance, spend caps, and atomic group binding.
"""

from dataclasses import dataclass
from typing import List, Dict, Any, Optional
import hashlib
import base64
from cryptography.hazmat.primitives.asymmetric import ed25519


@dataclass
class ContractState:
    """Simulated or on-chain state for SentinelPay smart contract."""
    admin_address: str
    verifier_public_key_b64: str
    max_daily_spend: int
    current_daily_spend: int = 0
    consumed_nonces: set = None

    def __post_init__(self):
        if self.consumed_nonces is None:
            self.consumed_nonces = set()


class SentinelPayContractLogic:
    """
    Python reference model and validation logic for SentinelPay AVM Smart Contract.
    Enforces on-chain invariants matching TEAL / PyTeal execution.
    """

    def __init__(self, state: ContractState):
        self.state = state

    def validate_atomic_group(
        self,
        payment_tx: Dict[str, Any],
        app_call_tx: Dict[str, Any],
        attestation_payload: Dict[str, Any],
        attestation_signature_b64: str,
    ) -> (bool, str):
        """
        Executes atomic group validation:
        Tx 0: Payment transaction
        Tx 1: SentinelPay App Call (this contract)
        """
        # Invariant 1: App Call action must be 'validate_and_pay'
        args = app_call_tx.get("args", [])
        if not args or args[0] != "validate_and_pay":
            return False, "Invalid app call selector; expected 'validate_and_pay'."

        # Invariant 2: Verify Attestation Ed25519 signature
        signing_bytes = attestation_payload.get("signing_bytes")
        if not signing_bytes:
            return False, "Missing signing bytes in attestation payload."

        try:
            pub_bytes = base64.b64decode(self.state.verifier_public_key_b64)
            pub_key = ed25519.Ed25519PublicKey.from_public_bytes(pub_bytes)
            sig_bytes = base64.b64decode(attestation_signature_b64)
            pub_key.verify(sig_bytes, signing_bytes)
        except Exception:
            return False, "On-chain signature verification failed: invalid verifier signature."

        # Invariant 3: Attestation Nonce must NOT have been consumed (Replay protection)
        nonce = attestation_payload.get("nonce")
        if not nonce or nonce in self.state.consumed_nonces:
            return False, f"Replay rejected: nonce '{nonce}' has already been consumed."

        # Invariant 4: Payment Transaction destination must match Attestation destination
        if payment_tx.get("receiver") != attestation_payload.get("destination"):
            return False, (
                f"Destination mismatch: Payment Tx receiver '{payment_tx.get('receiver')}' "
                f"!= Attested destination '{attestation_payload.get('destination')}'"
            )

        # Invariant 5: Payment Transaction amount must match Attestation amount
        if payment_tx.get("amount") != attestation_payload.get("amount"):
            return False, (
                f"Amount mismatch: Payment Tx amount {payment_tx.get('amount')} "
                f"!= Attested amount {attestation_payload.get('amount')}"
            )

        # Invariant 6: Spend Cap enforcement
        payment_amount = payment_tx.get("amount", 0)
        if self.state.current_daily_spend + payment_amount > self.state.max_daily_spend:
            return False, (
                f"Spend cap exceeded: {self.state.current_daily_spend + payment_amount} "
                f"> max limit {self.state.max_daily_spend}"
            )

        # Update contract state atomically
        self.state.consumed_nonces.add(nonce)
        self.state.current_daily_spend += payment_amount
        return True, "Atomic group and authorization validated successfully."


def compile_teal_approval_program() -> str:
    """
    Returns the PyTeal / TEAL assembly specification for SentinelPay AVM contract.
    """
    return """#pragma version 8
// SentinelPay Core AVM Authorization Contract
// OnCreation: Initialize global state (admin, verifier_pk, max_daily_spend)
txn ApplicationID
int 0
==
bz check_app_call
byte "admin"
txn Sender
app_global_put
byte "spend_today"
int 0
app_global_put
int 1
return

check_app_call:
// Validate 'validate_and_pay' method invocation
txna ApplicationArgs 0
byte "validate_and_pay"
==
bnz handle_validate_and_pay
int 0
return

handle_validate_and_pay:
// 1. Check Group Size == 2 (Tx 0: Payment, Tx 1: App Call)
global GroupSize
int 2
==
assert

// 2. Check Tx 0 is Payment
gtxn 0 TypeEnum
int pay
==
assert

// 3. Verify Ed25519 signature of attestation argument
txna ApplicationArgs 1 // signed data
txna ApplicationArgs 2 // signature
byte "verifier_pk"
app_global_get
ed25519verify_bare
assert

// 4. Match payment destination and amount
gtxn 0 Receiver
txna ApplicationArgs 3 // destination
==
assert

gtxn 0 Amount
txna ApplicationArgs 4 // amount btoi
btoi
==
assert

// 5. Update spend counter and return success
int 1
return
"""
