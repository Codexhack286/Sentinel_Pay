"""
The complete x402 loop against live Algorand TestNet.

    GET /paid-dataset          -> 402 with payment requirements
    SentinelPay gateway        -> policy + verifier -> signed attestation
    atomic group broadcast     -> payment + validate_and_pay settle together
    GET /paid-dataset + proof  -> 200, resource served

The last step is the one worth watching. The server does not take the signature
as proof of payment: it looks up the contract's nonce box on TestNet, and only
serves once the chain confirms the authorization was consumed. Between the
broadcast and confirmation, the very same request returns 402.

The resource server runs in-process here (via FastAPI's TestClient) so the whole
thing is one command; it talks to the real network throughout.

Prerequisites: the same as scripts/live_broadcast.py, plus RESOURCE_OWNER_ADDRESS
and RESOURCE_PRICE_UALGO matching what the agent will actually pay.

Usage:
    uv run python scripts/live_roundtrip.py
"""

import sys
import warnings

from algosdk.encoding import is_valid_address

# Starlette's TestClient warns about its httpx dependency. Irrelevant here and
# it clutters a demo people watch, so silence just that one.
warnings.filterwarnings("ignore", message=".*httpx.*", module="fastapi.testclient")

from fastapi.testclient import TestClient  # noqa: E402

from scripts._chain import (
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
from sentinelpay.payments.algorand import build_protected_group
from sentinelpay.payments.x402 import X402PaymentHandler
from sentinelpay.policy.models import AgentPolicy
from sentinelpay.verifier.verifier import LocalSemanticVerifier

AGENT_ID = "deep-agent-researcher-01"
POLICY_ID = "policy-live-roundtrip-v1"
USER_OBJECTIVE = "Research renewable energy datasets and retrieve 2026 statistics"


def step(number: int, title: str) -> None:
    print(f"\n{'-' * 62}\n  STEP {number}: {title}\n{'-' * 62}")


def main() -> int:
    require("AGENT_MNEMONIC", "SENTINELPAY_APP_ID", "BUDGET_APP_ID", "VERIFIER_PRIVATE_KEY")

    if not settings.VERIFIER_PUBLIC_KEY:
        print(
            "VERIFIER_PUBLIC_KEY is not set. The resource server would validate "
            "against a different key than the gateway signs with.",
            file=sys.stderr,
        )
        return 1

    # Imported here so the module picks up the configured settings above.
    from services.api.app import app

    client = TestClient(app)
    algod_client = get_algod_client()
    agent_key, agent_address = account_from_mnemonic(settings.AGENT_MNEMONIC)
    payee = (
        settings.RESOURCE_OWNER_ADDRESS
        if is_valid_address(settings.RESOURCE_OWNER_ADDRESS)
        else agent_address
    )

    print("=== SentinelPay live x402 roundtrip (Algorand TestNet) ===")
    print(f"Agent:  {agent_address}")
    print(f"Payee:  {payee}")
    print(f"App:    {settings.SENTINELPAY_APP_ID}")

    # ── 1. The paywall ────────────────────────────────────────────────────────
    step(1, "GET /paid-dataset with no payment")
    challenge = client.get("/paid-dataset")
    print(f"HTTP {challenge.status_code}")
    print(f"WWW-Authenticate: {challenge.headers.get('WWW-Authenticate', '')[:96]}...")
    if challenge.status_code != 402:
        print("Expected a 402 challenge.", file=sys.stderr)
        return 1
    requirement = challenge.json()

    if not is_valid_address(requirement["pay_to"]):
        print(
            f"\nRESOURCE_OWNER_ADDRESS ({requirement['pay_to']}) is not a real Algorand "
            "address, so this payment could never settle. Set it in .env.",
            file=sys.stderr,
        )
        return 1

    # ── 2. Authorization ──────────────────────────────────────────────────────
    step(2, "SentinelPay authorizes the exact payment")
    policy = AgentPolicy(
        policy_id=POLICY_ID,
        agent_id=AGENT_ID,
        max_per_transaction=requirement["amount"] * 2,
        daily_spend_limit=requirement["amount"] * 10,
        allowed_tools=["paid_research"],
        allowed_destinations=[requirement["pay_to"]],
        allowed_categories=["research", "energy", "dataset"],
    )
    intent = PaymentIntent(
        policy_id=POLICY_ID,
        agent_id=AGENT_ID,
        declared_goal=USER_OBJECTIVE,
        task_scope=USER_OBJECTIVE,
        tool_name="paid_research",
        resource=requirement["resource_id"],
        destination=requirement["pay_to"],
        amount=requirement["amount"],
        currency=requirement["asset"],
    )
    gateway = SentinelPayGateway(verifier=LocalSemanticVerifier(signer=load_signer(required=True)))
    response = gateway.process_payment_request(intent, policy)
    if response.status != "authorized":
        print(f"Denied: {response.reason}", file=sys.stderr)
        return 1

    attestation = response.attestation
    proof = X402PaymentHandler.construct_settlement_proof(attestation, tx_id="", group_id="")
    # Both forms, labelled. The string is what the attestation carries and what
    # HTTP-layer messages quote; its SHA-256 is the contract's box key. Printing
    # one as "nonce" and letting the other appear later reads like a mismatch.
    print(f"Attestation:  {attestation.attestation_id}")
    print(f"Nonce:        {attestation.nonce}")
    print(f"Box key:      {attestation.nonce_bytes().hex()}  (SHA-256 of the nonce)")

    # ── 3. Authorized but not yet paid ────────────────────────────────────────
    step(3, "Present the authorization BEFORE broadcasting")
    early = client.get("/paid-dataset", headers={"Authorization": proof})
    print(f"HTTP {early.status_code}")
    print(f"  {early.json().get('detail', '')}")
    if early.status_code == 200:
        print(
            "\nThe server served the resource without a settled payment. "
            "On-chain settlement verification is not being enforced.",
            file=sys.stderr,
        )
        return 1
    print("\n  A valid signature is not a payment. This is the check that makes it a paywall.")

    # ── 4. Settle ─────────────────────────────────────────────────────────────
    step(4, "Broadcast the protected atomic group")
    group = build_protected_group(
        sender=agent_address,
        receiver=requirement["pay_to"],
        amount=requirement["amount"],
        attestation=attestation,
        sentinelpay_app_id=settings.SENTINELPAY_APP_ID,
        budget_app_id=settings.BUDGET_APP_ID,
        suggested_params=algod_client.suggested_params(),
        note=f"SentinelPay x402: {requirement['resource_id']}".encode(),
    )
    try:
        txid = algod_client.send_transactions([txn.sign(agent_key) for txn in group])
    except Exception as e:
        print(f"Rejected: {describe_error(e)}", file=sys.stderr)
        return 1
    confirmed_round = wait_for_confirmation(algod_client, txid)["confirmed-round"]
    print(f"Settled in round {confirmed_round}")
    print(f"{EXPLORER_TX.format(txid)}")

    # ── 5. Redeem ─────────────────────────────────────────────────────────────
    step(5, "Present the same authorization again, now that it settled")
    served = client.get("/paid-dataset", headers={"Authorization": proof})
    print(f"HTTP {served.status_code}")
    if served.status_code != 200:
        print(f"  {served.json().get('detail', '')}", file=sys.stderr)
        return 1
    body = served.json()
    print(f"  settlement_verified: {body['settlement_verified']}")
    print(f"  {body['settlement_detail']}")
    print(f"  resource: {body['data']['title']}")

    # ── 6. Replay ─────────────────────────────────────────────────────────────
    step(6, "Present it a third time (replay)")
    replay = client.get("/paid-dataset", headers={"Authorization": proof})
    print(f"HTTP {replay.status_code}")
    print(f"  {replay.json().get('detail', '')}")

    print(f"\n{'=' * 62}")
    print("  Full x402 loop complete: 402 -> authorize -> settle -> 200 -> replay refused")
    print(f"{'=' * 62}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
