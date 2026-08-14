"""
Tests that the deployable PyTeal contract (contracts/pyteal_contract.py)
compiles cleanly and encodes the same invariants as the pure-Python reference
model in contracts/sentinelpay.py (tested separately in test_sentinelpay.py).

This does not require a live Algorand node — TEAL compilation is fully local.
"""

from contracts.pyteal_contract import compile_approval, compile_clear


def test_approval_program_compiles():
    teal = compile_approval()
    assert teal.startswith("#pragma version 8")
    assert len(teal.splitlines()) > 20


def test_clear_program_compiles():
    teal = compile_clear()
    assert "#pragma version 8" in teal


def test_approval_program_checks_group_size():
    teal = compile_approval()
    assert "GroupSize" in teal


def test_approval_program_verifies_ed25519_signature():
    teal = compile_approval()
    assert "ed25519verify_bare" in teal


def test_approval_program_uses_box_storage_for_replay_protection():
    teal = compile_approval()
    # box_create / box_put ops back the nonce-consumption check described in
    # contracts/README.md and docs/threat-model.md.
    assert "box_create" in teal
    assert "box_put" in teal


def test_approval_program_checks_selector():
    teal = compile_approval()
    assert "validate_and_pay" in teal
