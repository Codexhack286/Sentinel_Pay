"""
Tests that the deployable PyTeal contract compiles cleanly and still emits the
opcodes each invariant depends on.

These are shape assertions on generated TEAL, not execution tests — running TEAL
needs an AVM, which would mean a LocalNet dependency. Behaviour is covered by
`test_reference_model.py`, which models the same invariants in Python, and by
`scripts/verify_attack.py`, which exercises the real program on TestNet. What
these guard is that a refactor cannot quietly *drop* a check from the compiled
program while the Python model still passes.

TEAL compilation is fully local; no node required.
"""

import pytest

from contracts.pyteal_contract import compile_approval, compile_clear
from sentinelpay.verifier.attestation import (
    AVM_BLOB_LEN,
    AVM_MAGIC,
    AVM_OFFSET_AMOUNT,
    AVM_OFFSET_DESTINATION,
    AVM_OFFSET_EXPIRES_AT,
    AVM_OFFSET_NONCE,
)


@pytest.fixture(scope="module")
def teal() -> str:
    return compile_approval()


def test_approval_program_compiles(teal):
    assert teal.startswith("#pragma version 8")
    assert len(teal.splitlines()) > 20


def test_clear_program_compiles():
    assert "#pragma version 8" in compile_clear()


def test_selectors_are_present(teal):
    assert "validate_and_pay" in teal
    assert "admin_reset_spend" in teal


def test_group_shape_is_checked(teal):
    assert "GroupSize" in teal
    assert "TypeEnum" in teal


def test_signature_is_verified(teal):
    assert "ed25519verify_bare" in teal


def test_box_storage_backs_replay_protection(teal):
    assert "box_create" in teal
    assert "box_put" in teal


def test_close_out_and_rekey_are_rejected(teal):
    """An amount-only check would let a payment drain the rest of the balance."""
    assert "CloseRemainderTo" in teal
    assert "RekeyTo" in teal
    assert "ZeroAddress" in teal


def test_expiry_is_checked_against_block_time(teal):
    assert "LatestTimestamp" in teal


def test_enforced_fields_are_extracted_from_the_signed_blob(teal):
    """The binding that makes the whole scheme sound.

    Destination, amount, nonce and expiry must be read out of the signed bytes
    at these exact offsets. If they ever arrive as separate application
    arguments again, a caller can substitute them freely while keeping a valid
    signature over something else entirely.
    """
    for offset in (
        AVM_OFFSET_DESTINATION,
        AVM_OFFSET_AMOUNT,
        AVM_OFFSET_NONCE,
        AVM_OFFSET_EXPIRES_AT,
    ):
        assert f"extract {offset}" in teal or f"int {offset}" in teal, (
            f"no extraction at blob offset {offset}"
        )

    assert f"int {AVM_BLOB_LEN}" in teal, "blob length is not validated"
    assert AVM_MAGIC.hex() in teal.replace("0x", ""), "blob magic is not validated"


def test_program_only_reads_three_application_arguments(teal):
    """Argument 3 and beyond would be unsigned and therefore attacker-controlled."""
    assert "txna ApplicationArgs 3" not in teal
    assert "txna ApplicationArgs 4" not in teal
    assert "txna ApplicationArgs 5" not in teal


def test_only_noop_and_create_are_dispatched(teal):
    """Everything else — Update, Delete, OptIn, CloseOut — falls through to a reject.

    Rejecting UpdateApplication is what stops a compromised admin key from
    swapping in an attacker's verifier identity, and the default-deny shape
    means a newly added OnCompletion cannot accidentally become reachable.
    """
    dispatch = teal.splitlines()[:12]
    assert "int NoOp" in dispatch, "NoOp branch missing"
    assert not any(
        completion in "\n".join(dispatch)
        for completion in ("UpdateApplication", "DeleteApplication", "OptIn", "CloseOut")
    ), "a non-NoOp completion has its own branch instead of falling through to reject"
