"""
SentinelPay Algorand Smart Contract — real PyTeal implementation.

This is the deployable counterpart to `contracts/sentinelpay.py` (which is a
pure-Python *reference model* used for fast, chain-free unit testing of the
authorization invariants). This module compiles to actual TEAL bytecode via
PyTeal and is what gets deployed to Algorand TestNet/MainNet with AlgoKit.

WHY THE ARGUMENT SHAPE LOOKS LIKE THIS
--------------------------------------
An earlier revision passed destination, amount and nonce as *separate*
application arguments alongside a signed blob, and only checked that the
signature over the blob was valid. Those separate arguments were never bound to
the blob, so any single valid attestation could be resubmitted with an
attacker-chosen destination, an attacker-chosen amount and a fresh nonce — the
signature check passed, and every other assert compared attacker input against
attacker input. One legitimate 0.1 ALGO authorization was effectively a bearer
token for the whole spend cap.

The fix is structural: the contract now reads destination, amount, nonce and
expiry *out of the signed bytes themselves*, at fixed offsets. There is nothing
left for a caller to substitute.

Global state:
    admin            (bytes)  - creator address; may reset the spend counter
    verifier_pk      (bytes)  - Ed25519 public key (32 bytes) of the SentinelPay verifier
    max_daily_spend  (uint64) - hard cap on cumulative spend per window
    spend_today      (uint64) - cumulative spend counter

Box storage:
    key = nonce32 (32 bytes, extracted from the signed blob) -> value = 0x01
    Presence of the box means the authorization was already consumed. This is
    the on-chain replay protection referenced in docs/threat-model.md.

Signed blob layout (must stay in lockstep with
`sentinelpay/verifier/attestation.py::Attestation.avm_signing_bytes`):

    offset  len  field
    0       8    magic "SPAYv1\\x00\\x00"
    8       32   destination   (raw Algorand public key)
    40      8    amount        (big-endian uint64)
    48      32   nonce32       (box key)
    80      8    expires_at    (big-endian uint64, unix seconds)
    88      32   intent_hash32
    ---     ---
    120          total

Required atomic group shape for `validate_and_pay` (GroupSize >= 2):
    gtxn[0]  Payment transaction   (the actual settlement leg)
    gtxn[n]  ApplicationCall to this app, args:
        args[0] = "validate_and_pay"
        args[1] = signed blob   (exactly 120 bytes, layout above)
        args[2] = signature     (64-byte Ed25519 signature over args[1])
    Any further transactions may be appended (e.g. NoOp calls that pool extra
    opcode budget for ed25519verify_bare); they cannot weaken the checks below.

NOTE: `spend_today` is a monotonic counter plus an explicit admin reset rather
than an automatic daily rollover — the AVM has no scheduler, and a rollover
keyed to block timestamps would add state and opcode cost for no security gain
at PoC scope. Without the reset the demo app bricks itself once cumulative
spend reaches the cap, which is why `admin_reset_spend` exists.
"""

from pyteal import (
    App,
    Approve,
    Assert,
    Bytes,
    BoxCreate,
    BoxPut,
    Cond,
    Ed25519Verify_Bare,
    Expr,
    Extract,
    ExtractUint64,
    Global,
    Gtxn,
    Int,
    Len,
    Mode,
    OnComplete,
    Reject,
    ScratchVar,
    Seq,
    TealType,
    Txn,
    TxnType,
    compileTeal,
)

APP_ARG_SELECTOR = 0
APP_ARG_BLOB = 1
APP_ARG_SIGNATURE = 2

GLOBAL_ADMIN = Bytes("admin")
GLOBAL_VERIFIER_PK = Bytes("verifier_pk")
GLOBAL_MAX_DAILY_SPEND = Bytes("max_daily_spend")
GLOBAL_SPEND_TODAY = Bytes("spend_today")

SELECTOR_VALIDATE_AND_PAY = Bytes("validate_and_pay")
SELECTOR_ADMIN_RESET_SPEND = Bytes("admin_reset_spend")

# Imported rather than duplicated: the offsets below and the blob the signer
# produces have to move together or the contract silently reads garbage.
from sentinelpay.verifier.attestation import (  # noqa: E402  (constants only, no cycle)
    AVM_BLOB_LEN as BLOB_LEN,
    AVM_MAGIC,
    AVM_OFFSET_AMOUNT as BLOB_OFFSET_AMOUNT,
    AVM_OFFSET_DESTINATION as BLOB_OFFSET_DESTINATION,
    AVM_OFFSET_EXPIRES_AT as BLOB_OFFSET_EXPIRES_AT,
    AVM_OFFSET_NONCE as BLOB_OFFSET_NONCE,
)

BLOB_MAGIC = Bytes("base16", AVM_MAGIC.hex())
BLOB_OFFSET_MAGIC = 0
BLOB_LEN_MAGIC = len(AVM_MAGIC)
BLOB_LEN_NONCE = 32

NONCE_BOX_FLAG = Bytes("base16", "0x01")
ED25519_SIGNATURE_LEN = 64


def on_create() -> Expr:
    """
    ApplicationCreate: seeds global state.
    Expects creation args: [verifier_pk (32 bytes), max_daily_spend (8-byte uint)]
    """
    return Seq(
        Assert(Len(Txn.application_args[0]) == Int(32)),
        Assert(Len(Txn.application_args[1]) == Int(8)),
        App.globalPut(GLOBAL_ADMIN, Txn.sender()),
        App.globalPut(GLOBAL_VERIFIER_PK, Txn.application_args[0]),
        App.globalPut(GLOBAL_MAX_DAILY_SPEND, ExtractUint64(Txn.application_args[1], Int(0))),
        App.globalPut(GLOBAL_SPEND_TODAY, Int(0)),
        Approve(),
    )


def validate_and_pay() -> Expr:
    """
    Core authorization invariant, executed alongside the payment leg at gtxn[0].
    Mirrors SentinelPayContractLogic.validate_atomic_group() 1:1.
    """
    blob = Txn.application_args[APP_ARG_BLOB]
    amount = ScratchVar(TealType.uint64)
    nonce = ScratchVar(TealType.bytes)

    return Seq(
        # Invariant 0: the signed blob is exactly the shape this contract parses.
        # Without the length and magic checks, `Extract` at a fixed offset could
        # read whatever a shorter or differently-framed message happened to
        # place there.
        Assert(Len(blob) == Int(BLOB_LEN)),
        Assert(Extract(blob, Int(BLOB_OFFSET_MAGIC), Int(BLOB_LEN_MAGIC)) == BLOB_MAGIC),
        Assert(Len(Txn.application_args[APP_ARG_SIGNATURE]) == Int(ED25519_SIGNATURE_LEN)),

        # Invariant 1: at least [payment, this app call]. Extra transactions may
        # follow (they pool opcode budget for the signature check below) and
        # cannot relax anything, since every check reads gtxn[0] or the blob.
        Assert(Global.group_size() >= Int(2)),
        Assert(Gtxn[0].type_enum() == TxnType.Payment),

        # Invariant 2: the payment must not smuggle out the rest of the sender's
        # balance or hand over the account. An amount-only check would happily
        # approve a 0.1 ALGO payment that also closes the account to the
        # attacker.
        Assert(Gtxn[0].close_remainder_to() == Global.zero_address()),
        Assert(Gtxn[0].rekey_to() == Global.zero_address()),
        Assert(Txn.rekey_to() == Global.zero_address()),

        # Invariant 3: Ed25519 signature over the whole blob, against the
        # verifier public key registered at creation. Everything read below
        # comes from these now-authenticated bytes.
        Assert(
            Ed25519Verify_Bare(
                blob,
                Txn.application_args[APP_ARG_SIGNATURE],
                App.globalGet(GLOBAL_VERIFIER_PK),
            )
        ),

        amount.store(ExtractUint64(blob, Int(BLOB_OFFSET_AMOUNT))),
        nonce.store(Extract(blob, Int(BLOB_OFFSET_NONCE), Int(BLOB_LEN_NONCE))),

        # Invariant 4: the authorized destination is the actual payment receiver.
        Assert(Gtxn[0].receiver() == Extract(blob, Int(BLOB_OFFSET_DESTINATION), Int(32))),

        # Invariant 5: the authorized amount is the actual payment amount.
        Assert(Gtxn[0].amount() == amount.load()),

        # Invariant 6: the authorization has not expired. Block timestamps are
        # coarse but monotonic, which is all an expiry window needs.
        Assert(Global.latest_timestamp() < ExtractUint64(blob, Int(BLOB_OFFSET_EXPIRES_AT))),

        # Invariant 7: cumulative spend cap.
        Assert(
            App.globalGet(GLOBAL_SPEND_TODAY) + amount.load()
            <= App.globalGet(GLOBAL_MAX_DAILY_SPEND)
        ),

        # Invariant 8: replay protection. BoxCreate returns 0 when the box
        # already exists, which means this nonce was already consumed.
        Assert(BoxCreate(nonce.load(), Int(1))),
        BoxPut(nonce.load(), NONCE_BOX_FLAG),

        App.globalPut(GLOBAL_SPEND_TODAY, App.globalGet(GLOBAL_SPEND_TODAY) + amount.load()),
        Approve(),
    )


def admin_reset_spend() -> Expr:
    """Reset the cumulative spend counter. Admin only.

    Stands in for the daily rollover the AVM cannot schedule itself. It can only
    ever reset the counter — it cannot raise the cap, retire a consumed nonce,
    or change the verifier key, so a compromised admin key cannot forge an
    authorization, only widen how much already-authorized spending fits.
    """
    return Seq(
        Assert(Txn.sender() == App.globalGet(GLOBAL_ADMIN)),
        Assert(Txn.rekey_to() == Global.zero_address()),
        App.globalPut(GLOBAL_SPEND_TODAY, Int(0)),
        Approve(),
    )


def approval_program() -> Expr:
    return Cond(
        [Txn.application_id() == Int(0), on_create()],
        [
            Txn.on_completion() == OnComplete.NoOp,
            Seq(
                # A NoOp with no arguments would otherwise panic on the selector
                # read; fail closed with an explicit reject instead.
                Assert(Txn.application_args.length() > Int(0)),
                Cond(
                    [Txn.application_args[APP_ARG_SELECTOR] == SELECTOR_VALIDATE_AND_PAY, validate_and_pay()],
                    [Txn.application_args[APP_ARG_SELECTOR] == SELECTOR_ADMIN_RESET_SPEND, admin_reset_spend()],
                    [Int(1), Reject()],
                ),
            ),
        ],
        [Int(1), Reject()],
    )


def clear_state_program() -> Expr:
    return Approve()


def compile_approval(version: int = 8) -> str:
    return compileTeal(approval_program(), mode=Mode.Application, version=version)


def compile_clear(version: int = 8) -> str:
    return compileTeal(clear_state_program(), mode=Mode.Application, version=version)


if __name__ == "__main__":
    print(compile_approval())
