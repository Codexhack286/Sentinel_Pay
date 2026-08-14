"""
Deploy a trivial budget-only app to Algorand TestNet.

This app's approval program is just `Approve()` — it always succeeds.
Adding NoOp calls to it in a transaction group pools their 700-unit opcode
budgets without any risk of rejection.

Usage:
    uv run python scripts/deploy_budget_app.py
    # Prints BUDGET_APP_ID — add it to .env as BUDGET_APP_ID=<id>
"""

import sys
from algosdk import account, mnemonic, transaction
from algosdk.v2client import algod
from sentinelpay.config import settings

# Minimal TEAL that always approves (1 line — no logic)
BUDGET_APPROVAL_TEAL = "#pragma version 8\nint 1\nreturn\n"
BUDGET_CLEAR_TEAL = "#pragma version 8\nint 1\nreturn\n"


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


def main() -> None:
    if not settings.AGENT_MNEMONIC:
        print("AGENT_MNEMONIC not set in .env.", file=sys.stderr)
        sys.exit(1)

    client = get_algod_client()
    private_key = mnemonic.to_private_key(settings.AGENT_MNEMONIC)
    sender = account.address_from_private_key(private_key)

    # Compile TEAL via algod
    approval_bytes = client.compile(BUDGET_APPROVAL_TEAL)["result"]
    clear_bytes = client.compile(BUDGET_CLEAR_TEAL)["result"]

    import base64
    approval_bytecode = base64.b64decode(approval_bytes)
    clear_bytecode = base64.b64decode(clear_bytes)

    params = client.suggested_params()
    txn = transaction.ApplicationCreateTxn(
        sender=sender,
        sp=params,
        on_complete=transaction.OnComplete.NoOpOC,
        approval_program=approval_bytecode,
        clear_program=clear_bytecode,
        global_schema=transaction.StateSchema(num_uints=0, num_byte_slices=0),
        local_schema=transaction.StateSchema(num_uints=0, num_byte_slices=0),
        note=b"SentinelPay opcode budget helper app",
    )
    signed = txn.sign(private_key)
    txid = client.send_transaction(signed)
    print(f"Submitted budget app create txn: {txid}")

    confirmed = wait_for_confirmation(client, txid)
    app_id = confirmed["application-index"]
    print(f"\nBudget app deployed. App ID: {app_id}")
    print(f"Add this to .env:  BUDGET_APP_ID={app_id}")
    print(f"Explorer: https://testnet.explorer.perawallet.app/application/{app_id}")


if __name__ == "__main__":
    main()
