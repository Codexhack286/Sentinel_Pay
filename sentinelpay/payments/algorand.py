"""Construction of the protected Algorand atomic group.

One place builds the `[payment, validate_and_pay, ...budget]` group, so the
live demo, the adversarial verification script and any future facilitator path
all submit exactly the shape the contract expects. When the contract's argument
layout changes, this is the only caller that has to change with it.
"""

import base64
from typing import List, Optional

from algosdk import transaction

from sentinelpay.verifier.attestation import Attestation

SELECTOR_VALIDATE_AND_PAY = b"validate_and_pay"

# ed25519verify_bare costs 1900 opcode units against a default 700-unit budget
# per application call. Budget is pooled across every app call in the group, so
# two extra NoOps against a trivial always-approve app lift the pool to
# 3 x 700 = 2100. They carry no logic and cannot weaken any contract check.
BUDGET_BOOST_CALLS = 2
OPCODE_BUDGET_PER_APP_CALL = 700


class GroupBuildError(ValueError):
    """The requested group cannot be built as specified."""


def build_protected_group(
    *,
    sender: str,
    receiver: str,
    amount: int,
    attestation: Attestation,
    sentinelpay_app_id: int,
    budget_app_id: int,
    suggested_params: transaction.SuggestedParams,
    note: Optional[bytes] = None,
    override_blob: Optional[bytes] = None,
    override_signature: Optional[bytes] = None,
) -> List[transaction.Transaction]:
    """Build the atomic group: [payment, validate_and_pay app call, budget NoOps].

    ``override_blob`` / ``override_signature`` exist so the adversarial script
    can submit deliberately tampered groups and prove the contract rejects them.
    Legitimate callers leave both unset.
    """
    if amount <= 0:
        raise GroupBuildError(f"amount must be positive, got {amount}")
    if not sentinelpay_app_id:
        raise GroupBuildError("sentinelpay_app_id is required")
    if not budget_app_id:
        raise GroupBuildError(
            "budget_app_id is required — deploy it with scripts/deploy_budget_app.py"
        )

    blob = override_blob if override_blob is not None else attestation.avm_signing_bytes()
    if override_signature is not None:
        signature = override_signature
    else:
        if not attestation.avm_signature:
            raise GroupBuildError(
                "Attestation has no AVM signature. Its destination is not a real "
                "Algorand address, so it was never authorized for on-chain settlement."
            )
        signature = base64.b64decode(attestation.avm_signature)

    nonce_key = attestation.nonce_bytes()

    payment = transaction.PaymentTxn(
        sender=sender,
        sp=suggested_params,
        receiver=receiver,
        amt=amount,
        note=note,
    )
    app_call = transaction.ApplicationNoOpTxn(
        sender=sender,
        sp=suggested_params,
        index=sentinelpay_app_id,
        app_args=[SELECTOR_VALIDATE_AND_PAY, blob, signature],
        boxes=[(sentinelpay_app_id, nonce_key)],
    )
    budget_calls = [
        transaction.ApplicationNoOpTxn(
            sender=sender,
            sp=suggested_params,
            index=budget_app_id,
            note=f"sentinelpay-budget-{i}".encode(),
        )
        for i in range(BUDGET_BOOST_CALLS)
    ]

    group = [payment, app_call, *budget_calls]
    group_id = transaction.calculate_group_id(group)
    for txn in group:
        txn.group = group_id
    return group


def pooled_opcode_budget(group: List[transaction.Transaction]) -> int:
    """Opcode units available to the group, for pre-flight sanity checks."""
    app_calls = sum(1 for txn in group if isinstance(txn, transaction.ApplicationCallTxn))
    return app_calls * OPCODE_BUDGET_PER_APP_CALL
