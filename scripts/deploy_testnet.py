"""
Deploy the SentinelPay application to Algorand TestNet.

Prerequisites:
    1. uv run python scripts/gen_verifier_key.py   -> VERIFIER_{PUBLIC,PRIVATE}_KEY in .env
    2. uv run python scripts/fund_testnet.py       -> creator account, funded at the dispenser
    3. uv run python contracts/compile.py          -> contracts/build/*.teal

Usage:
    uv run python scripts/deploy_testnet.py --max-daily-spend 1000000

On success, prints the new SENTINELPAY_APP_ID to add to .env.

The verifier public key is written into the app's global state at creation and
cannot be changed afterwards (the contract rejects UpdateApplication). Rotating
the verifier key therefore means deploying a new app — deliberate, so a
compromised admin key cannot quietly swap in an attacker's signing identity.

CAVEAT: `compile_teal` calls algod's `POST /v2/teal/compile`, which is only
available on nodes with EnableDeveloperAPI set. Public endpoints generally have
it on; if you get a 404/501, switch providers rather than assuming the
bytecode is wrong.
"""

import argparse
import base64
import sys
from pathlib import Path

from algosdk import transaction

from scripts._chain import (
    EXPLORER_APP,
    account_from_mnemonic,
    compile_teal,
    get_algod_client,
    wait_for_confirmation,
)
from sentinelpay.config import settings
from sentinelpay.verifier.attestation import _pad_b64

BUILD_DIR = Path(__file__).parent.parent / "contracts" / "build"


def deploy(admin_mnemonic: str, verifier_public_key_b64: str, max_daily_spend: int) -> int:
    approval_path = BUILD_DIR / "approval.teal"
    clear_path = BUILD_DIR / "clear.teal"
    if not approval_path.exists() or not clear_path.exists():
        print(
            "No compiled TEAL found. Run `uv run python contracts/compile.py` first.",
            file=sys.stderr,
        )
        sys.exit(1)

    client = get_algod_client()
    admin_private_key, admin_address = account_from_mnemonic(admin_mnemonic)

    verifier_pk_bytes = base64.b64decode(_pad_b64(verifier_public_key_b64))
    if len(verifier_pk_bytes) != 32:
        print(
            f"VERIFIER_PUBLIC_KEY decodes to {len(verifier_pk_bytes)} bytes; expected 32. "
            "Regenerate with scripts/gen_verifier_key.py.",
            file=sys.stderr,
        )
        sys.exit(1)

    txn = transaction.ApplicationCreateTxn(
        sender=admin_address,
        sp=client.suggested_params(),
        on_complete=transaction.OnComplete.NoOpOC,
        approval_program=compile_teal(client, approval_path.read_text()),
        clear_program=compile_teal(client, clear_path.read_text()),
        global_schema=transaction.StateSchema(num_uints=2, num_byte_slices=2),
        local_schema=transaction.StateSchema(num_uints=0, num_byte_slices=0),
        app_args=[verifier_pk_bytes, int(max_daily_spend).to_bytes(8, "big")],
    )
    txid = client.send_transaction(txn.sign(admin_private_key))
    print(f"Submitted ApplicationCreate txn: {txid}")

    app_id = wait_for_confirmation(client, txid)["application-index"]

    print(f"\nSentinelPay app deployed. App ID: {app_id}")
    print(f"Add this to .env: SENTINELPAY_APP_ID={app_id}")
    print(f"Explorer: {EXPLORER_APP.format(app_id)}")
    print(
        "\nNext: fund the app account for nonce-box MBR with "
        "`uv run python scripts/fund_app_mbr.py`."
    )
    return app_id


def main() -> None:
    parser = argparse.ArgumentParser(description="Deploy SentinelPay app to Algorand TestNet")
    parser.add_argument(
        "--max-daily-spend",
        type=int,
        default=1_000_000,
        help="Cumulative spend cap in microAlgo enforced on-chain (default 1.0 ALGO)",
    )
    args = parser.parse_args()

    if args.max_daily_spend <= 0:
        parser.error("--max-daily-spend must be positive")

    admin_mnemonic = settings.admin_mnemonic
    if not admin_mnemonic:
        print(
            "Neither CONTRACT_CREATOR_MNEMONIC nor AGENT_MNEMONIC is set in .env. "
            "Run scripts/fund_testnet.py, fund the account at the dispenser, then "
            "add its mnemonic to .env.",
            file=sys.stderr,
        )
        sys.exit(1)
    if not settings.VERIFIER_PUBLIC_KEY:
        print(
            "VERIFIER_PUBLIC_KEY not set in .env — run "
            "`uv run python scripts/gen_verifier_key.py` first.",
            file=sys.stderr,
        )
        sys.exit(1)

    deploy(
        admin_mnemonic=admin_mnemonic,
        verifier_public_key_b64=settings.VERIFIER_PUBLIC_KEY,
        max_daily_spend=args.max_daily_spend,
    )


if __name__ == "__main__":
    main()
