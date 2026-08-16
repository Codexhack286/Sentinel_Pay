"""
Deploy the trivial opcode-budget helper app to Algorand TestNet.

Its approval program is a bare `Approve()`. NoOp calls to it in a transaction
group contribute their 700-unit opcode budget to the group's shared pool, which
is how `validate_and_pay` affords `ed25519verify_bare` (1900 units). The helper
holds no state and makes no decisions, so it cannot weaken any SentinelPay
check — see sentinelpay/payments/algorand.py.

Usage:
    uv run python scripts/deploy_budget_app.py
    # Prints BUDGET_APP_ID — add it to .env
"""

import sys

from algosdk import transaction

from scripts._chain import (
    EXPLORER_APP,
    account_from_mnemonic,
    compile_teal,
    get_algod_client,
    wait_for_confirmation,
)
from sentinelpay.config import settings

ALWAYS_APPROVE_TEAL = "#pragma version 8\nint 1\nreturn\n"


def main() -> None:
    admin_mnemonic = settings.admin_mnemonic
    if not admin_mnemonic:
        print(
            "Neither CONTRACT_CREATOR_MNEMONIC nor AGENT_MNEMONIC is set in .env.",
            file=sys.stderr,
        )
        sys.exit(1)

    client = get_algod_client()
    private_key, sender = account_from_mnemonic(admin_mnemonic)
    bytecode = compile_teal(client, ALWAYS_APPROVE_TEAL)

    txn = transaction.ApplicationCreateTxn(
        sender=sender,
        sp=client.suggested_params(),
        on_complete=transaction.OnComplete.NoOpOC,
        approval_program=bytecode,
        clear_program=bytecode,
        global_schema=transaction.StateSchema(num_uints=0, num_byte_slices=0),
        local_schema=transaction.StateSchema(num_uints=0, num_byte_slices=0),
        note=b"SentinelPay opcode budget helper app",
    )
    txid = client.send_transaction(txn.sign(private_key))
    print(f"Submitted budget app create txn: {txid}")

    app_id = wait_for_confirmation(client, txid)["application-index"]
    print(f"\nBudget app deployed. App ID: {app_id}")
    print(f"Add this to .env:  BUDGET_APP_ID={app_id}")
    print(f"Explorer: {EXPLORER_APP.format(app_id)}")


if __name__ == "__main__":
    main()
