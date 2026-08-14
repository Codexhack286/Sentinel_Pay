"""
Deploy the SentinelPay application to Algorand TestNet.

Prerequisites:
    1. `uv run python contracts/compile.py`  (produces contracts/build/*.teal)
    2. `uv run python scripts/fund_testnet.py`  (generate + fund a creator/admin
       account and a verifier account via the TestNet dispenser)
    3. Populate .env with ADMIN_MNEMONIC and VERIFIER_MNEMONIC (or reuse
       AGENT_MNEMONIC / VERIFIER_MNEMONIC — see .env.example)

Usage:
    uv run python scripts/deploy_testnet.py --max-daily-spend 1000000

On success, prints the new SENTINELPAY_APP_ID to add to .env. This is the
last piece of the "High Priority: TestNet Smart Contract Deployment" item in
docs/status.md — everything upstream of this (contract logic, attestation
signing, policy engine) is already implemented and unit-tested locally.

NOTE: This script talks to a live Algorand TestNet node (ALGOD_ADDRESS in
.env / sentinelpay/config.py) and therefore requires outbound network access
that a locked-down sandbox may not have. It has not been exercised against a
live node from this environment — treat it as reviewed-but-unrun and smoke
test it from a machine with TestNet connectivity before demo day.

CAVEAT (found during doc verification, not yet confirmed against a live
node): `compile_program_source()` below calls algod's `POST /v2/teal/compile`
endpoint, which the Algorand REST API docs state is "only enabled when a
node's configuration file sets EnableDeveloperAPI to true." Public endpoints
generally run with this enabled (it's required for most public dapp tooling
to function at all), but it is not guaranteed for every provider. If
`client.compile()` fails with a 404/501 against your configured
ALGOD_ADDRESS, switch to a provider/config known to expose it (e.g. AlgoKit's
bundled LocalNet, or Nodely/AlgoNode's standard testnet endpoint) rather than
assuming the assembled bytecode is wrong.
"""

import argparse
import base64
import sys
from pathlib import Path

from algosdk import account, mnemonic, transaction
from algosdk.v2client import algod

from sentinelpay.config import settings

BUILD_DIR = Path(__file__).parent.parent / "contracts" / "build"


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


def compile_program_source(client: algod.AlgodClient, source: str) -> bytes:
    """Ask algod to assemble TEAL source to bytecode (works for pre-compiled TEAL)."""
    compiled = client.compile(source)
    return base64.b64decode(compiled["result"])


def deploy(admin_mnemonic: str, verifier_public_key_b64: str, max_daily_spend: int) -> int:
    if not (BUILD_DIR / "approval.teal").exists():
        print("No compiled TEAL found. Run `uv run python contracts/compile.py` first.", file=sys.stderr)
        sys.exit(1)

    approval_source = (BUILD_DIR / "approval.teal").read_text()
    clear_source = (BUILD_DIR / "clear.teal").read_text()

    client = get_algod_client()
    admin_private_key = mnemonic.to_private_key(admin_mnemonic)
    admin_address = account.address_from_private_key(admin_private_key)

    approval_bytecode = compile_program_source(client, approval_source)
    clear_bytecode = compile_program_source(client, clear_source)

    # Add missing padding: some .env parsers strip trailing '=' from base64 values.
    padded = verifier_public_key_b64 + "=" * (-len(verifier_public_key_b64) % 4)
    verifier_pk_bytes = base64.b64decode(padded)
    max_daily_spend_bytes = int(max_daily_spend).to_bytes(8, "big")

    global_schema = transaction.StateSchema(num_uints=2, num_byte_slices=2)
    local_schema = transaction.StateSchema(num_uints=0, num_byte_slices=0)

    params = client.suggested_params()
    txn = transaction.ApplicationCreateTxn(
        sender=admin_address,
        sp=params,
        on_complete=transaction.OnComplete.NoOpOC,
        approval_program=approval_bytecode,
        clear_program=clear_bytecode,
        global_schema=global_schema,
        local_schema=local_schema,
        app_args=[verifier_pk_bytes, max_daily_spend_bytes],
    )
    signed_txn = txn.sign(admin_private_key)
    txid = client.send_transaction(signed_txn)
    print(f"Submitted ApplicationCreate txn: {txid}")

    confirmed = wait_for_confirmation(client, txid)
    app_id = confirmed["application-index"]

    print(f"\nSentinelPay app deployed. App ID: {app_id}")
    print(f"Add this to .env: SENTINELPAY_APP_ID={app_id}")
    print(
        "\nNote: agents/verifier submitting `validate_and_pay` calls must fund the "
        "app account for box MBR (nonce boxes) before first use — see docs/protocol.md."
    )
    return app_id


def main() -> None:
    parser = argparse.ArgumentParser(description="Deploy SentinelPay app to Algorand TestNet")
    parser.add_argument("--max-daily-spend", type=int, default=1_000_000, help="Cap in microAlgo (default 1.0 ALGO)")
    args = parser.parse_args()

    if not settings.AGENT_MNEMONIC:
        print(
            "AGENT_MNEMONIC not set in .env — this account is used as the app creator/admin "
            "for this deploy script. Run scripts/fund_testnet.py, then add the mnemonic to .env.",
            file=sys.stderr,
        )
        sys.exit(1)
    if not settings.VERIFIER_PUBLIC_KEY:
        print(
            "VERIFIER_PUBLIC_KEY not set in .env — this is the base64 Ed25519 public key "
            "the deployed contract will use for on-chain attestation checks.",
            file=sys.stderr,
        )
        sys.exit(1)

    deploy(
        admin_mnemonic=settings.AGENT_MNEMONIC,
        verifier_public_key_b64=settings.VERIFIER_PUBLIC_KEY,
        max_daily_spend=args.max_daily_spend,
    )


if __name__ == "__main__":
    main()
