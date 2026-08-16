"""
Tests for the protected atomic group builder (sentinelpay/payments/algorand.py).

These run entirely offline — building and grouping transactions needs no node.
They pin the group shape the deployed contract expects, so a change to one has
to be a deliberate change to both.
"""

import base64
import time

import pytest
from algosdk import transaction
from algosdk.encoding import encode_address

from sentinelpay.payments.algorand import (
    OPCODE_BUDGET_PER_APP_CALL,
    GroupBuildError,
    build_protected_group,
    pooled_opcode_budget,
)
from sentinelpay.verifier.attestation import Attestation, AttestationSigner

SENDER = encode_address(bytes([0x01] * 32))
RECEIVER = encode_address(bytes([0x11] * 32))
SENTINELPAY_APP_ID = 769239295
BUDGET_APP_ID = 769239296

# ed25519verify_bare costs 1900 units; the group must pool more than that.
ED25519_VERIFY_BARE_COST = 1900


@pytest.fixture
def params():
    return transaction.SuggestedParams(
        fee=1000, first=1, last=1001, gh=base64.b64encode(b"h" * 32).decode(), flat_fee=True
    )


@pytest.fixture
def attestation():
    return AttestationSigner().sign(
        Attestation(
            intent_hash="b" * 64,
            agent_id="agent-1",
            policy_id="policy-1",
            tool_name="paid_research",
            destination=RECEIVER,
            amount=100_000,
            currency="uALGO",
            expires_at=int(time.time()) + 300,
        )
    )


def build(attestation, params, **overrides):
    kwargs = dict(
        sender=SENDER,
        receiver=RECEIVER,
        amount=100_000,
        attestation=attestation,
        sentinelpay_app_id=SENTINELPAY_APP_ID,
        budget_app_id=BUDGET_APP_ID,
        suggested_params=params,
    )
    kwargs.update(overrides)
    return build_protected_group(**kwargs)


def test_group_shape_matches_the_contract(attestation, params):
    group = build(attestation, params)

    assert isinstance(group[0], transaction.PaymentTxn)
    assert group[0].receiver == RECEIVER
    assert group[0].amt == 100_000

    app_call = group[1]
    assert app_call.index == SENTINELPAY_APP_ID
    assert app_call.app_args[0] == b"validate_and_pay"
    assert app_call.app_args[1] == attestation.avm_signing_bytes()
    assert app_call.app_args[2] == base64.b64decode(attestation.avm_signature)
    assert len(app_call.app_args) == 3, "extra unsigned args would be attacker-controllable"


def test_nonce_box_is_referenced_so_the_contract_can_write_it(attestation, params):
    app_call = build(attestation, params)[1]

    assert len(app_call.boxes) == 1
    box = app_call.boxes[0]
    assert box.name == attestation.nonce_bytes()
    # algosdk encodes "a box of the app being called" as foreign-app index 0.
    assert box.app_index == 0


def test_every_transaction_shares_one_group_id(attestation, params):
    group = build(attestation, params)
    group_ids = {txn.group for txn in group}

    assert len(group_ids) == 1
    assert group_ids.pop() is not None


def test_pooled_budget_covers_the_signature_check(attestation, params):
    group = build(attestation, params)
    assert pooled_opcode_budget(group) > ED25519_VERIFY_BARE_COST
    assert pooled_opcode_budget(group) == 3 * OPCODE_BUDGET_PER_APP_CALL


def test_attestation_without_an_avm_signature_cannot_be_settled(params):
    """A placeholder-destination attestation has no on-chain representation."""
    offline = AttestationSigner().sign(
        Attestation(
            intent_hash="hash",
            agent_id="agent-1",
            policy_id="policy-1",
            tool_name="paid_research",
            destination="RESOURCE_OWNER_PLACEHOLDER",
            amount=100_000,
            currency="uALGO",
        )
    )
    with pytest.raises(ValueError):
        build(offline, params)


def test_missing_budget_app_is_refused(attestation, params):
    with pytest.raises(GroupBuildError, match="budget_app_id"):
        build(attestation, params, budget_app_id=0)


def test_non_positive_amount_is_refused(attestation, params):
    with pytest.raises(GroupBuildError, match="positive"):
        build(attestation, params, amount=0)
