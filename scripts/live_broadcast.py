"""
Step 3 — Live Atomic Group Broadcast.

Constructs and submits a real [payment + SentinelPay app-call] atomic group to
Algorand TestNet, proving end-to-end on-chain settlement.

Flow:
    1. Build a PaymentIntent for the demo paid-dataset resource.
    2. Run it through the SentinelPay gateway (policy + verifier -> attestation).
    3. Construct the protected atomic group.
    4. Sign and broadcast via algod.
    5. Print Pera Explorer links.

Prerequisites:
    - VERIFIER_PRIVATE_KEY set (scripts/gen_verifier_key.py) and matching the
      key baked into the deployed app
    - AGENT_MNEMONIC funded (payment amount + ~0.004 ALGO of group fees)
    - SENTINELPAY_APP_ID and BUDGET_APP_ID set
    - App account funded for box MBR (scripts/fund_app_mbr.py)

Usage:
    uv run python scripts/live_broadcast.py
"""

import base64
import sys

from algosdk.encoding import is_valid_address

from scripts._chain import (
    EXPLORER_APP,
    EXPLORER_TX,
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
from sentinelpay.payments.algorand import build_protected_group, pooled_opcode_budget
from sentinelpay.policy.models import AgentPolicy
from sentinelpay.verifier.verifier import LocalSemanticVerifier

PAYMENT_AMOUNT_UALGO = 100_000  # 0.1 ALGO
RESOURCE_ID = "energy-dataset-2026"
AGENT_ID = "deep-agent-researcher-01"
POLICY_ID = "policy-testnet-demo-v1"
USER_OBJECTIVE = "Research renewable energy datasets and retrieve 2026 statistics"


def main() -> None:
    require("AGENT_MNEMONIC", "SENTINELPAY_APP_ID", "BUDGET_APP_ID", "VERIFIER_PRIVATE_KEY")

    agent_private_key, agent_address = account_from_mnemonic(settings.AGENT_MNEMONIC)
    # Falls back to paying the agent's own address so the demo needs only one
    # funded TestNet wallet; the contract checks are identical either way.
    resource_owner = (
        settings.RESOURCE_OWNER_ADDRESS
        if is_valid_address(settings.RESOURCE_OWNER_ADDRESS)
        else agent_address
    )

    print("=== SentinelPay Live Atomic Group Broadcast ===\n")

    policy = AgentPolicy(
        policy_id=POLICY_ID,
        agent_id=AGENT_ID,
        max_per_transaction=200_000,
        daily_spend_limit=1_000_000,
        allowed_tools=["paid_research"],
        allowed_destinations=[resource_owner],
        allowed_categories=["research", "energy", "dataset"],
    )
    intent = PaymentIntent(
        policy_id=POLICY_ID,
        agent_id=AGENT_ID,
        declared_goal=USER_OBJECTIVE,
        task_scope=USER_OBJECTIVE,
        tool_name="paid_research",
        resource=RESOURCE_ID,
        destination=resource_owner,
        amount=PAYMENT_AMOUNT_UALGO,
        currency="uALGO",
    )

    print(f"[INTENT] {intent.declared_goal}")
    print(f"         Destination: {resource_owner}")
    print(f"         Amount:      {PAYMENT_AMOUNT_UALGO} uALGO")

    gateway = SentinelPayGateway(verifier=LocalSemanticVerifier(signer=load_signer(required=True)))
    response = gateway.process_payment_request(intent, policy)
    if response.status != "authorized":
        print(f"\n[DENIED] {response.reason}", file=sys.stderr)
        sys.exit(1)

    attestation = response.attestation
    print(f"\n[ATTESTATION] ID:    {attestation.attestation_id}")
    print(f"              Nonce: {attestation.nonce_bytes().hex()}")
    print(f"              Expires at: {attestation.expires_at}")

    client = get_algod_client()
    group = build_protected_group(
        sender=agent_address,
        receiver=resource_owner,
        amount=PAYMENT_AMOUNT_UALGO,
        attestation=attestation,
        sentinelpay_app_id=settings.SENTINELPAY_APP_ID,
        budget_app_id=settings.BUDGET_APP_ID,
        suggested_params=client.suggested_params(),
        note=f"SentinelPay x402 payment: {RESOURCE_ID}".encode(),
    )

    print(f"\n[SENDER] {agent_address}")
    print(f"[GROUP]  Group ID: {base64.b64encode(group[0].group).decode()}")
    print(f"         gtxn[0]  Payment {PAYMENT_AMOUNT_UALGO} uALGO -> {resource_owner[:20]}...")
    print(f"         gtxn[1]  validate_and_pay -> App {settings.SENTINELPAY_APP_ID}")
    print(f"         gtxn[2..] Budget NoOps  -> App {settings.BUDGET_APP_ID}")
    print(f"         Pooled opcode budget: {pooled_opcode_budget(group)} units")

    print("\n[BROADCAST] Submitting atomic group to Algorand TestNet...")
    try:
        txid = client.send_transactions([txn.sign(agent_private_key) for txn in group])
    except Exception as e:
        print(f"[REJECTED] {describe_error(e)}", file=sys.stderr)
        sys.exit(1)

    confirmed_round = wait_for_confirmation(client, txid)["confirmed-round"]

    print(f"\n{'=' * 60}")
    print("  SentinelPay Live Settlement Complete")
    print(f"{'=' * 60}")
    print(f"\n  Payment Tx:   {EXPLORER_TX.format(txid)}")
    print(f"  Application:  {EXPLORER_APP.format(settings.SENTINELPAY_APP_ID)}")
    print(f"\n  Attestation:  {attestation.attestation_id}")
    print(f"  Round:        {confirmed_round}")
    print(f"{'=' * 60}\n")


if __name__ == "__main__":
    main()
