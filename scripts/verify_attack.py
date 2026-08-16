"""
Adversarial on-chain verification.

The point of SentinelPay is that an unauthorized payment cannot *settle* — not
that an application-layer message says "blocked". This script proves the strong
claim by constructing groups a compromised client would build and submitting
them to Algorand TestNet, showing that consensus rejects each one.

Every case here assumes the attacker has already fully compromised the agent
process: they hold a genuine, correctly signed attestation and can build any
transaction group they like. What they cannot do is make one settle.

Cases:
    1. bare-payment             - payment with no SentinelPay app call at all
    2. amount-substitution      - real attestation, inflated payment amount
    3. destination-substitution - real attestation, attacker's receiver
    4. blob-tampering           - signed bytes edited to match the attacker's payment
    5. forged-signature         - attacker-signed authorization blob
    6. replay                   - resubmit an authorization already consumed on-chain
    7. admin-impersonation      - non-admin tries to reset the on-chain spend counter

Usage:
    uv run python scripts/verify_attack.py                 # dry run, builds only
    uv run python scripts/verify_attack.py --broadcast     # really submits to TestNet

Dry run needs no funds and no network.

A rejection only counts if it comes from the SentinelPay contract. A group that
bounces on insufficient balance or an expired validity window proves nothing
about authorization, so those are reported as INCONCLUSIVE and the script exits
non-zero rather than letting them read as a defence. That is why the inflated
amount here is modest: it has to be affordable, or the balance check fires
first and the contract never runs.
"""

import argparse
import sys
from dataclasses import dataclass
from typing import Callable, List, Optional

from algosdk import account, transaction
from algosdk.encoding import decode_address, encode_address, is_valid_address
from cryptography.hazmat.primitives.asymmetric import ed25519

from scripts._chain import (
    account_from_mnemonic,
    describe_error,
    get_algod_client,
    require,
    wait_for_confirmation,
)
from sentinelpay.config import settings
from sentinelpay.gateway.middleware import SentinelPayGateway
from sentinelpay.intent.models import PaymentIntent
from sentinelpay.keys import load_signer
from sentinelpay.payments.algorand import build_protected_group
from sentinelpay.policy.models import AgentPolicy
from sentinelpay.verifier.attestation import (
    AVM_OFFSET_AMOUNT,
    AVM_OFFSET_DESTINATION,
    Attestation,
)
from sentinelpay.verifier.verifier import LocalSemanticVerifier

PAYMENT_AMOUNT_UALGO = 100_000
# Only 2x the authorized amount, not some dramatic number. The point is to make
# the *contract* be what rejects the group. An inflated amount the account
# cannot afford gets bounced by the balance check before the app call ever runs,
# which proves nothing about authorization — see `classify_rejection` below.
INFLATED_AMOUNT_UALGO = 200_000
AGENT_ID = "deep-agent-researcher-01"
POLICY_ID = "policy-attack-verification-v1"
USER_OBJECTIVE = "Research renewable energy datasets and retrieve 2026 statistics"

# A well-formed (checksummed) address nobody holds the key for. Using a valid
# address makes the rejection provably about authorization rather than about a
# malformed receiver.
ATTACKER_ADDRESS = encode_address(bytes([0xA7] * 32))


@dataclass
class AttackCase:
    name: str
    description: str
    build: Callable[[], List[transaction.Transaction]]
    expected: str
    # Substring the rejection must contain for this case to count as proven.
    # Without it, a group bounced for an unrelated reason (an underfunded
    # account, an expired validity window) would read as a successful defence.
    proof_marker: str = "assert failed"
    # Group that must settle first for the attack to be meaningful. The replay
    # case needs its nonce genuinely consumed on-chain before the replay runs.
    setup: Optional[Callable[[], List[transaction.Transaction]]] = None
    # Per-transaction private keys, when the attacker is not the agent account.
    # None means "sign everything with the agent key".
    signers: Optional[List[str]] = None


# Rejections that say nothing about authorization. Treating one of these as a
# pass is how a security test quietly stops testing anything.
INCONCLUSIVE_MARKERS = (
    "overspend",
    "underflow",
    "below min",
    "txn dead",
    "round",
    "fee too small",
)


def classify_rejection(reason: str, case: AttackCase) -> str:
    """Return 'proven', 'inconclusive', or 'unexpected' for a rejection reason."""
    lowered = reason.lower()
    if any(marker in lowered for marker in INCONCLUSIVE_MARKERS):
        return "inconclusive"
    if case.proof_marker.lower() in lowered:
        return "proven"
    return "unexpected"


def _splice(blob: bytes, offset: int, replacement: bytes) -> bytes:
    """Overwrite part of a signed blob, as an attacker with the bytes would."""
    return blob[:offset] + replacement + blob[offset + len(replacement) :]


def _flat_fee(params: transaction.SuggestedParams, fee: int) -> transaction.SuggestedParams:
    """Copy of `params` with an exact fee, for pooled-fee groups."""
    return transaction.SuggestedParams(
        fee=fee,
        first=params.first,
        last=params.last,
        gh=params.gh,
        gen=params.gen,
        flat_fee=True,
        min_fee=params.min_fee,
    )


def build_cases(
    *,
    sender: str,
    sender_key: str,
    receiver: str,
    attestation: Attestation,
    params: transaction.SuggestedParams,
) -> List[AttackCase]:
    app_id = settings.SENTINELPAY_APP_ID
    budget_id = settings.BUDGET_APP_ID
    genuine_blob = attestation.avm_signing_bytes()

    def protected(**overrides) -> List[transaction.Transaction]:
        kwargs = dict(
            sender=sender,
            receiver=receiver,
            amount=PAYMENT_AMOUNT_UALGO,
            attestation=attestation,
            sentinelpay_app_id=app_id,
            budget_app_id=budget_id,
            suggested_params=params,
        )
        kwargs.update(overrides)
        return build_protected_group(**kwargs)

    def bare_payment() -> List[transaction.Transaction]:
        return [
            transaction.PaymentTxn(
                sender=sender,
                sp=params,
                receiver=receiver,
                amt=PAYMENT_AMOUNT_UALGO,
                note=b"bare x402 payment, no SentinelPay authorization",
            )
        ]

    def amount_substitution() -> List[transaction.Transaction]:
        # The attestation authorizes 100_000; the attacker pays themselves
        # 900_000 while presenting the genuine signed authorization.
        return protected(amount=INFLATED_AMOUNT_UALGO)

    def destination_substitution() -> List[transaction.Transaction]:
        return protected(receiver=ATTACKER_ADDRESS)

    def blob_tampering() -> List[transaction.Transaction]:
        # Rewrite the signed bytes so they *claim* the attacker's numbers. The
        # signature no longer covers them, which is exactly the check that the
        # earlier unbound-argument design was missing.
        tampered = _splice(
            _splice(genuine_blob, AVM_OFFSET_DESTINATION, decode_address(ATTACKER_ADDRESS)),
            AVM_OFFSET_AMOUNT,
            INFLATED_AMOUNT_UALGO.to_bytes(8, "big"),
        )
        return protected(
            receiver=ATTACKER_ADDRESS,
            amount=INFLATED_AMOUNT_UALGO,
            override_blob=tampered,
        )

    def forged_signature() -> List[transaction.Transaction]:
        rogue = ed25519.Ed25519PrivateKey.generate()
        return protected(override_signature=rogue.sign(genuine_blob))

    def legitimate() -> List[transaction.Transaction]:
        return protected(note=b"sentinelpay-replay-setup")

    def replay() -> List[transaction.Transaction]:
        # Same attestation, hence the same nonce and the same box key. A
        # different note changes the transaction ID, so this is a genuinely new
        # submission rather than a duplicate the pool would drop on its own —
        # the rejection has to come from box_create finding the nonce present.
        return protected(note=b"sentinelpay-replay-attempt")

    # Held across build/sign so the same rogue identity signs its own call.
    rogue_key, rogue_address = account.generate_account()

    def admin_impersonation() -> List[transaction.Transaction]:
        """Someone other than the creator tries to zero the spend counter.

        The rogue account is never funded. Algorand's pooled fees let the agent
        pay for the rogue's zero-fee application call, so the group reaches the
        contract and the admin assert — rather than dying on the rogue's empty
        balance, which would prove nothing.
        """
        fee_params = _flat_fee(params, 2_000)
        free_params = _flat_fee(params, 0)

        fee_payer = transaction.PaymentTxn(
            sender=sender,
            sp=fee_params,
            receiver=sender,
            amt=0,
            note=b"sentinelpay-fee-pool-for-rogue-admin-call",
        )
        rogue_call = transaction.ApplicationNoOpTxn(
            sender=rogue_address,
            sp=free_params,
            index=app_id,
            app_args=[b"admin_reset_spend"],
        )
        group = [fee_payer, rogue_call]
        group_id = transaction.calculate_group_id(group)
        for txn in group:
            txn.group = group_id
        return group

    return [
        AttackCase(
            "bare-payment",
            "Compromised client pays the resource directly, skipping SentinelPay entirely.",
            bare_payment,
            "settles as a plain payment but carries no authorization; the resource "
            "server refuses it because no SentinelPay app call ever consumed a nonce",
        ),
        AttackCase(
            "amount-substitution",
            f"Genuine attestation for {PAYMENT_AMOUNT_UALGO}, payment inflated to {INFLATED_AMOUNT_UALGO}.",
            amount_substitution,
            "contract rejects: signed amount != gtxn[0].amount",
        ),
        AttackCase(
            "destination-substitution",
            "Genuine attestation, funds redirected to the attacker.",
            destination_substitution,
            "contract rejects: signed destination != gtxn[0].receiver",
        ),
        AttackCase(
            "blob-tampering",
            "Attacker edits the signed authorization to match their own payment.",
            blob_tampering,
            "contract rejects: Ed25519 signature no longer verifies",
        ),
        AttackCase(
            "forged-signature",
            "Attacker signs a valid-looking authorization with their own key.",
            forged_signature,
            "contract rejects: signature is not from the registered verifier key",
        ),
        AttackCase(
            "replay",
            "Authorization is settled once legitimately, then submitted a second time.",
            replay,
            "contract rejects: nonce box already exists",
            setup=legitimate,
        ),
        AttackCase(
            "admin-impersonation",
            "A non-admin account tries to reset the on-chain spend counter.",
            admin_impersonation,
            "contract rejects: sender is not the registered admin",
            signers=[sender_key, rogue_key],
        ),
    ]


def run(broadcast: bool) -> int:
    require("SENTINELPAY_APP_ID", "BUDGET_APP_ID", "VERIFIER_PRIVATE_KEY", "AGENT_MNEMONIC")

    agent_private_key, agent_address = account_from_mnemonic(settings.AGENT_MNEMONIC)
    receiver = (
        settings.RESOURCE_OWNER_ADDRESS
        if is_valid_address(settings.RESOURCE_OWNER_ADDRESS)
        else agent_address
    )

    policy = AgentPolicy(
        policy_id=POLICY_ID,
        agent_id=AGENT_ID,
        max_per_transaction=200_000,
        daily_spend_limit=1_000_000,
        allowed_tools=["paid_research"],
        allowed_destinations=[receiver],
        allowed_categories=["research", "energy", "dataset"],
    )
    intent = PaymentIntent(
        policy_id=POLICY_ID,
        agent_id=AGENT_ID,
        declared_goal=USER_OBJECTIVE,
        task_scope=USER_OBJECTIVE,
        tool_name="paid_research",
        resource="energy-dataset-2026",
        destination=receiver,
        amount=PAYMENT_AMOUNT_UALGO,
        currency="uALGO",
    )

    gateway = SentinelPayGateway(verifier=LocalSemanticVerifier(signer=load_signer(required=True)))
    response = gateway.process_payment_request(intent, policy)
    if response.status != "authorized":
        print(f"Baseline authorization unexpectedly denied: {response.reason}", file=sys.stderr)
        return 1

    client = get_algod_client()
    params = client.suggested_params()

    # Pre-flight. If the account cannot afford the largest attempted payment,
    # the chain bounces those groups on balance before the contract ever runs,
    # and the whole exercise proves nothing.
    balance = client.account_info(agent_address).get("amount", 0)
    needed = INFLATED_AMOUNT_UALGO + 200_000  # payment + min balance + fees
    if broadcast and balance < needed:
        print(
            f"Agent balance {balance} uALGO is below the {needed} uALGO needed to make\n"
            f"the substitution cases fail *at the contract* rather than on balance.\n"
            "Top up at https://lora.algokit.io/testnet/fund and re-run.",
            file=sys.stderr,
        )
        return 1

    cases = build_cases(
        sender=agent_address,
        sender_key=agent_private_key,
        receiver=receiver,
        attestation=response.attestation,
        params=params,
    )

    def sign(group, case: AttackCase):
        keys = case.signers or [agent_private_key] * len(group)
        if len(keys) != len(group):
            raise ValueError(f"{case.name}: {len(keys)} signers for {len(group)} transactions")
        return [txn.sign(key) for txn, key in zip(group, keys)]

    print("=== SentinelPay Adversarial Settlement Verification ===")
    print(f"Mode: {'BROADCAST to TestNet' if broadcast else 'dry run (build only)'}")
    print(f"Agent balance: {balance} uALGO\n")

    regressions, inconclusive = 0, 0
    for case in cases:
        print(f"[{case.name}] {case.description}")
        try:
            group = case.build()
        except Exception as e:
            print(f"    BUILD REFUSED: {describe_error(e)}\n")
            continue

        print(f"    group size: {len(group)}   expected: {case.expected}")
        if not broadcast:
            print()
            continue

        if case.setup is not None:
            try:
                setup_txid = client.send_transactions(
                    [txn.sign(agent_private_key) for txn in case.setup()]
                )
                wait_for_confirmation(client, setup_txid)
                print(f"    setup settled legitimately (txid {setup_txid})")
            except Exception as e:
                inconclusive += 1
                print(f"    INCONCLUSIVE - setup group failed: {describe_error(e)}\n")
                continue

        try:
            txid = client.send_transactions(sign(group, case))
        except Exception as e:
            reason = describe_error(e)
            if case.name == "bare-payment":
                print(f"    REJECTED: {reason}\n")
                continue
            verdict = classify_rejection(reason, case)
            if verdict == "proven":
                print(f"    PROVEN - contract rejected it: {reason}\n")
            elif verdict == "inconclusive":
                inconclusive += 1
                print(f"    INCONCLUSIVE - bounced before the contract ran: {reason}")
                print("      This says nothing about authorization. Fix the cause and re-run.\n")
            else:
                inconclusive += 1
                print(f"    UNEXPECTED rejection reason: {reason}\n")
            continue

        # Only the bare payment is expected to make it on-chain; every other
        # case reaching this point means an authorization check did not hold.
        if case.name == "bare-payment":
            print(f"    settled as a plain payment (txid {txid}); carries no authorization\n")
        else:
            regressions += 1
            print(f"    !! ACCEPTED ON CHAIN (txid {txid}) - THIS IS A SECURITY REGRESSION\n")

    if regressions:
        print(f"{regressions} attack case(s) settled. The authorization boundary is broken.")
        return 1
    if inconclusive:
        print(
            f"{inconclusive} case(s) were rejected for reasons unrelated to authorization.\n"
            "The boundary is NOT demonstrated. Do not present this run as proof."
        )
        return 1
    print("All authorization-bypass attempts were rejected by the contract itself.")
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--broadcast",
        action="store_true",
        help="Actually submit each group to TestNet (spends fees; all but case 1 are rejected)",
    )
    sys.exit(run(parser.parse_args().broadcast))


if __name__ == "__main__":
    main()
