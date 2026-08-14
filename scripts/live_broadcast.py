"""
Step 3 — Live Atomic Group Broadcast.

Constructs and submits a real [payment + SentinelPay app-call] atomic group
to Algorand TestNet, proving end-to-end on-chain settlement.

Flow:
    1. Build a PaymentIntent for the demo paid-dataset resource.
    2. Run it through the SentinelPay gateway (policy + verifier → attestation).
    3. Construct the Algorand atomic group:
         gtxn[0]  Payment:      agent → RESOURCE_OWNER, 100,000 uALGO
         gtxn[1]  App call:     → SENTINELPAY_APP_ID, validate_and_pay, attestation args
    4. Assign group ID, sign both transactions.
    5. Broadcast via algosdk (direct algod, not facilitator — simpler for PoC).
    6. Print Pera Explorer links for both the tx and the app.

Prerequisites:
    - AGENT_MNEMONIC funded (>= 0.1 ALGO for fee + payment amount)
    - SENTINELPAY_APP_ID set in .env
    - VERIFIER_PRIVATE_KEY set in .env (for signing attestations)
    - App account funded for Box MBR (run scripts/fund_app_mbr.py first)

Usage:
    uv run python scripts/live_broadcast.py
"""

import base64
import json
import sys

from algosdk import account, mnemonic, transaction
from algosdk.v2client import algod
from cryptography.hazmat.primitives.asymmetric import ed25519

from sentinelpay.config import settings
from sentinelpay.gateway.middleware import SentinelPayGateway
from sentinelpay.intent.models import PaymentIntent
from sentinelpay.policy.models import AgentPolicy
from sentinelpay.verifier.attestation import AttestationSigner
from sentinelpay.verifier.verifier import LocalSemanticVerifier

# ── Demo parameters ────────────────────────────────────────────────────────────
# Set RESOURCE_OWNER_ADDRESS in .env to a real funded TestNet address you own.
# For a self-contained demo, if not set, we pay back to the agent's own address
# (proves the full atomic group + contract validation works without needing a
# second funded wallet).
PAYMENT_AMOUNT_UALGO = 100_000   # 0.1 ALGO
RESOURCE_ID = "energy-dataset-2026"
AGENT_ID = "deep-agent-researcher-01"
POLICY_ID = "policy-testnet-demo-v1"


def get_algod_client() -> algod.AlgodClient:
    return algod.AlgodClient(settings.ALGOD_TOKEN, settings.ALGOD_ADDRESS, headers={})


def wait_for_confirmation(client: algod.AlgodClient, txid: str) -> dict:
    last_round = client.status().get("last-round")
    while True:
        pending = client.pending_transaction_info(txid)
        if pending.get("confirmed-round", 0) > 0:
            return pending
        last_round += 1
        client.status_after_block(last_round)


def load_verifier_signer() -> AttestationSigner:
    """Load verifier signing key from .env VERIFIER_PRIVATE_KEY."""
    if not settings.VERIFIER_PRIVATE_KEY:
        print("VERIFIER_PRIVATE_KEY not set in .env.", file=sys.stderr)
        sys.exit(1)
    # Restore padding stripped by some .env parsers
    raw_b64 = settings.VERIFIER_PRIVATE_KEY + "=" * (-len(settings.VERIFIER_PRIVATE_KEY) % 4)
    raw_bytes = base64.b64decode(raw_b64)
    private_key = ed25519.Ed25519PrivateKey.from_private_bytes(raw_bytes)
    return AttestationSigner(private_key=private_key)


def main() -> None:
    # ── Pre-flight checks ──────────────────────────────────────────────────────
    for var, val in [
        ("AGENT_MNEMONIC", settings.AGENT_MNEMONIC),
        ("SENTINELPAY_APP_ID", settings.SENTINELPAY_APP_ID),
        ("VERIFIER_PRIVATE_KEY", settings.VERIFIER_PRIVATE_KEY),
    ]:
        if not val:
            print(f"{var} not set in .env.", file=sys.stderr)
            sys.exit(1)

    # Derive sender + use as self-payment recipient for demo
    # (Replace RESOURCE_OWNER_ADDRESS with a real second address for production)
    _priv = mnemonic.to_private_key(settings.AGENT_MNEMONIC)
    RESOURCE_OWNER_ADDRESS = account.address_from_private_key(_priv)

    print("=== SentinelPay Live Atomic Group Broadcast ===\n")

    # ── Step 1: Build policy + intent ─────────────────────────────────────────
    policy = AgentPolicy(
        policy_id=POLICY_ID,
        agent_id=AGENT_ID,
        max_per_transaction=200_000,
        daily_spend_limit=1_000_000,
        allowed_tools=["paid_research"],
        allowed_destinations=[RESOURCE_OWNER_ADDRESS],
        allowed_categories=["research", "energy", "dataset"],
    )

    intent = PaymentIntent(
        policy_id=POLICY_ID,
        agent_id=AGENT_ID,
        declared_goal="Research renewable energy datasets and retrieve 2026 statistics",
        tool_name="paid_research",
        resource=RESOURCE_ID,
        destination=RESOURCE_OWNER_ADDRESS,
        amount=PAYMENT_AMOUNT_UALGO,
        currency="uALGO",
    )

    print(f"[INTENT] {intent.declared_goal}")
    print(f"         Destination: {RESOURCE_OWNER_ADDRESS}")
    print(f"         Amount:      {PAYMENT_AMOUNT_UALGO} uALGO")

    # ── Step 2: Run through SentinelPay gateway ────────────────────────────────
    signer = load_verifier_signer()
    gateway = SentinelPayGateway(verifier=LocalSemanticVerifier(signer=signer))
    response = gateway.process_payment_request(intent, policy)

    if response.status != "authorized":
        print(f"\n[DENIED] {response.reason}", file=sys.stderr)
        sys.exit(1)

    attestation = response.attestation
    print(f"\n[ATTESTATION] ID:    {attestation.attestation_id}")
    print(f"              Nonce: {attestation.nonce}")
    print(f"              Sig:   {attestation.signature[:32]}...")

    # -- Step 3: Build atomic transaction group --------------------------------
    # Group shape: [payment, app-call, budget1, budget2]
    #
    # ed25519verify_bare costs 1900 opcode units. Each ApplicationCall txn in
    # the group contributes 700 units to a SHARED pool (AVM pooled-budget model).
    # We have 3 app-calls: app_txn + 2 budget NoOps => 3 * 700 = 2100 budget.
    # The budget NoOps call BUDGET_APP_ID (an always-approve trivial contract)
    # so they succeed without any logic of their own.
    # The main SentinelPay contract asserts GroupSize >= 2, so the 4-txn group
    # is accepted.
    if not settings.BUDGET_APP_ID:
        print("BUDGET_APP_ID not set in .env. Run: uv run python scripts/deploy_budget_app.py", file=sys.stderr)
        sys.exit(1)

    client = get_algod_client()
    private_key = mnemonic.to_private_key(settings.AGENT_MNEMONIC)
    sender_addr = account.address_from_private_key(private_key)
    params = client.suggested_params()

    print(f"\n[SENDER] {sender_addr}")

    # gtxn[0]: Payment
    pay_txn = transaction.PaymentTxn(
        sender=sender_addr,
        sp=params,
        receiver=RESOURCE_OWNER_ADDRESS,
        amt=PAYMENT_AMOUNT_UALGO,
        note=f"SentinelPay x402 payment: {RESOURCE_ID}".encode(),
    )

    # gtxn[1]: SentinelPay app call -- validate_and_pay
    signing_bytes = attestation.signing_bytes()
    sig_bytes = base64.b64decode(attestation.signature)
    destination_bytes = transaction.encoding.decode_address(RESOURCE_OWNER_ADDRESS)
    amount_bytes = PAYMENT_AMOUNT_UALGO.to_bytes(8, "big")
    nonce_bytes = attestation.nonce.encode("utf-8")

    app_txn = transaction.ApplicationNoOpTxn(
        sender=sender_addr,
        sp=params,
        index=settings.SENTINELPAY_APP_ID,
        app_args=[
            b"validate_and_pay",   # args[0] selector
            signing_bytes,         # args[1] attestation payload bytes
            sig_bytes,             # args[2] Ed25519 signature
            destination_bytes,     # args[3] destination (raw 32 bytes)
            amount_bytes,          # args[4] amount (8-byte big-endian)
            nonce_bytes,           # args[5] nonce (box key)
        ],
        boxes=[(settings.SENTINELPAY_APP_ID, nonce_bytes)],
    )

    # gtxn[2] & gtxn[3]: Budget-boost NoOps -- call trivial always-approve app.
    # Each adds 700 opcode units to the shared pool. Total: 3 * 700 = 2100,
    # which exceeds ed25519verify_bare's 1900-unit cost.
    budget1 = transaction.ApplicationNoOpTxn(
        sender=sender_addr,
        sp=params,
        index=settings.BUDGET_APP_ID,
        note=b"budget-boost-1",
    )
    budget2 = transaction.ApplicationNoOpTxn(
        sender=sender_addr,
        sp=params,
        index=settings.BUDGET_APP_ID,
        note=b"budget-boost-2",
    )

    # Assign group ID to all 4 txns
    group_txns = [pay_txn, app_txn, budget1, budget2]
    gid = transaction.calculate_group_id(group_txns)
    for t in group_txns:
        t.group = gid

    signed_txns = [t.sign(private_key) for t in group_txns]

    print(f"\n[GROUP]  Group ID: {base64.b64encode(gid).decode()}")
    print(f"         gtxn[0]  Payment {PAYMENT_AMOUNT_UALGO} uALGO -> {RESOURCE_OWNER_ADDRESS[:20]}...")
    print(f"         gtxn[1]  App call -> SentinelPay App ID {settings.SENTINELPAY_APP_ID}")
    print(f"         gtxn[2]  Budget NoOp -> App ID {settings.BUDGET_APP_ID}")
    print(f"         gtxn[3]  Budget NoOp -> App ID {settings.BUDGET_APP_ID}")
    print(f"         Pooled opcode budget: 3 app-calls x 700 = 2100 units")

    # -- Step 4: Broadcast -----------------------------------------------------
    print("\n[BROADCAST] Submitting atomic group to Algorand TestNet...")
    txid = client.send_transactions(signed_txns)
    print(f"            Submitted! Payment tx ID: {txid}")

    confirmed = wait_for_confirmation(client, txid)
    confirmed_round = confirmed["confirmed-round"]
    print(f"            Confirmed in round: {confirmed_round} OK")

    # -- Step 5: Print explorer links ------------------------------------------
    print(f"\n{'='*60}")
    print(f"  SentinelPay Live Settlement Complete!")
    print(f"{'='*60}")
    print(f"\n  Payment Tx:   https://testnet.explorer.perawallet.app/tx/{txid}")
    print(f"  Application:  https://testnet.explorer.perawallet.app/application/{settings.SENTINELPAY_APP_ID}")
    print(f"\n  Attestation:  {attestation.attestation_id}")
    print(f"  Round:        {confirmed_round}")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    main()

