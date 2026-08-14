"""
SentinelPay Algorand Smart Contract — real PyTeal implementation.

This is the deployable counterpart to `contracts/sentinelpay.py` (which is a
pure-Python *reference model* used for fast, chain-free unit testing of the
authorization invariants). This module compiles to actual TEAL bytecode via
PyTeal and is what gets deployed to Algorand TestNet/MainNet with AlgoKit.

Global state:
    admin              (bytes)  - creator address, allowed to update spend cap
    verifier_pk         (bytes)  - Ed25519 public key (32 bytes) of the SentinelPay verifier
    max_daily_spend      (uint64) - hard cap on cumulative spend per rolling window
    spend_today          (uint64) - cumulative spend counter (reset by admin op, see NOTE)

Box storage:
    key = nonce (bytes, from the signed attestation) -> value = b"\\x01"
    Presence of the box == nonce has been consumed. This is the on-chain
    replay-protection mechanism referenced in docs/threat-model.md and
    SentinelPay_Project_Review.docx Section 5 ("Attestation replay").

Required atomic group shape for `validate_and_pay` (GroupSize == 2):
    gtxn[0]  Payment transaction   (the actual settlement leg)
    gtxn[1]  ApplicationCall to this app, method "validate_and_pay", with args:
        args[0] = "validate_and_pay"
        args[1] = signing_bytes   (canonical JSON bytes of the attestation payload)
        args[2] = signature       (64-byte Ed25519 signature over signing_bytes)
        args[3] = destination     (32-byte raw Algorand address, must == gtxn[0].Receiver)
        args[4] = amount          (8-byte big-endian uint64, must == gtxn[0].Amount)
        args[5] = nonce           (bytes; box key, must not already exist)

NOTE: `spend_today` is intentionally a simple monotonic counter for the demo
(matches the reference model in contracts/sentinelpay.py). Production rollover
(daily reset) would use a scheduled admin no-op call keyed to UTC day, tracked
as future work in docs/status.md — not required for TestNet PoC scope.
"""

from pyteal import (
    Approve,
    App,
    Assert,
    Bytes,
    Btoi,
    Cond,
    Expr,
    Global,
    Int,
    Mode,
    OnComplete,
    Reject,
    Seq,
    Txn,
    TxnType,
    Gtxn,
    compileTeal,
    BoxCreate,
    BoxPut,
    Ed25519Verify_Bare,
)

APP_ARG_SELECTOR = 0
APP_ARG_SIGNING_BYTES = 1
APP_ARG_SIGNATURE = 2
APP_ARG_DESTINATION = 3
APP_ARG_AMOUNT = 4
APP_ARG_NONCE = 5

GLOBAL_ADMIN = Bytes("admin")
GLOBAL_VERIFIER_PK = Bytes("verifier_pk")
GLOBAL_MAX_DAILY_SPEND = Bytes("max_daily_spend")
GLOBAL_SPEND_TODAY = Bytes("spend_today")

NONCE_BOX_FLAG = Bytes("base16", "0x01")


def on_create() -> Expr:
    """
    ApplicationCreate: seeds global state.
    Expects creation args: [verifier_pk (32 bytes), max_daily_spend (8-byte uint)]
    """
    return Seq(
        App.globalPut(GLOBAL_ADMIN, Txn.sender()),
        App.globalPut(GLOBAL_VERIFIER_PK, Txn.application_args[0]),
        App.globalPut(GLOBAL_MAX_DAILY_SPEND, Btoi(Txn.application_args[1])),
        App.globalPut(GLOBAL_SPEND_TODAY, Int(0)),
        Approve(),
    )


def validate_and_pay() -> Expr:
    """
    Core authorization invariant, executed as gtxn[1] of a 2-txn atomic group.
    Mirrors SentinelPayContractLogic.validate_atomic_group() 1:1.
    """
    payment_amount = Gtxn[0].amount()
    new_spend_total = App.globalGet(GLOBAL_SPEND_TODAY) + payment_amount

    return Seq(
        # Invariant 1: at least a 2-txn group: [payment, this app call, ...budget txns]
        # Allowing GroupSize >= 2 lets callers append extra NoOp transactions to
        # boost the shared opcode pool (needed for ed25519verify_bare, which costs
        # 1900 units vs the default 700-unit per-txn budget).
        Assert(Global.group_size() >= Int(2)),
        Assert(Gtxn[0].type_enum() == TxnType.Payment),

        # Invariant 2: Ed25519 signature over the attestation's signing_bytes,
        # verified against the verifier's registered public key.
        Assert(
            Ed25519Verify_Bare(
                Txn.application_args[APP_ARG_SIGNING_BYTES],
                Txn.application_args[APP_ARG_SIGNATURE],
                App.globalGet(GLOBAL_VERIFIER_PK),
            )
        ),

        # Invariant 3: attestation destination must equal the actual payment receiver.
        Assert(Gtxn[0].receiver() == Txn.application_args[APP_ARG_DESTINATION]),

        # Invariant 4: attestation amount must equal the actual payment amount.
        Assert(payment_amount == Btoi(Txn.application_args[APP_ARG_AMOUNT])),

        # Invariant 5: spend cap enforcement (cumulative).
        Assert(new_spend_total <= App.globalGet(GLOBAL_MAX_DAILY_SPEND)),

        # Invariant 6: replay protection — nonce box must not already exist.
        # BoxCreate returns 0 (false) if the box already existed, which we
        # treat as a replay and reject.
        Assert(
            BoxCreate(Txn.application_args[APP_ARG_NONCE], Int(1))
        ),
        BoxPut(Txn.application_args[APP_ARG_NONCE], NONCE_BOX_FLAG),

        # Commit updated spend counter.
        App.globalPut(GLOBAL_SPEND_TODAY, new_spend_total),
        Approve(),
    )


def approval_program() -> Expr:
    is_create = Txn.application_id() == Int(0)
    is_validate_and_pay = Txn.application_args[APP_ARG_SELECTOR] == Bytes("validate_and_pay")

    return Cond(
        [is_create, on_create()],
        [
            Txn.on_completion() == OnComplete.NoOp,
            Cond([is_validate_and_pay, validate_and_pay()], [Int(1), Reject()]),
        ],
        [Txn.on_completion() == OnComplete.DeleteApplication, Reject()],
        [Txn.on_completion() == OnComplete.UpdateApplication, Reject()],
        [Txn.on_completion() == OnComplete.OptIn, Reject()],
        [Txn.on_completion() == OnComplete.CloseOut, Reject()],
    )


def clear_state_program() -> Expr:
    return Approve()


def compile_approval(version: int = 8) -> str:
    return compileTeal(approval_program(), mode=Mode.Application, version=version)


def compile_clear(version: int = 8) -> str:
    return compileTeal(clear_state_program(), mode=Mode.Application, version=version)


if __name__ == "__main__":
    print(compile_approval())
