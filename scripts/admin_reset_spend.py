"""
Reset the contract's cumulative spend counter. Admin only.

The AVM cannot schedule a daily rollover, so `spend_today` climbs until an admin
zeroes it. Once it reaches `max_daily_spend` every further `validate_and_pay`
fails the cap check and the app is effectively bricked — which is exactly the
kind of thing that surfaces mid-demo. Run this between demo rehearsals.

The call can only zero the counter. It cannot raise the cap, retire a consumed
nonce, or change the verifier key, so holding this key does not let anyone forge
an authorization.

Usage:
    uv run python scripts/admin_reset_spend.py
"""

import base64
import sys

from algosdk import transaction

from scripts._chain import (
    EXPLORER_TX,
    account_from_mnemonic,
    describe_error,
    get_algod_client,
    require,
    wait_for_confirmation,
)
from sentinelpay.config import settings

SELECTOR = b"admin_reset_spend"


def read_spend_today(client, app_id: int) -> int:
    state = client.application_info(app_id)["params"]["global-state"]
    for entry in state:
        if base64.b64decode(entry["key"]) == b"spend_today":
            return entry["value"]["uint"]
    return 0


def main() -> None:
    require("SENTINELPAY_APP_ID")
    admin_mnemonic = settings.admin_mnemonic
    if not admin_mnemonic:
        print("Neither CONTRACT_CREATOR_MNEMONIC nor AGENT_MNEMONIC is set.", file=sys.stderr)
        sys.exit(1)

    client = get_algod_client()
    private_key, sender = account_from_mnemonic(admin_mnemonic)
    app_id = settings.SENTINELPAY_APP_ID

    before = read_spend_today(client, app_id)
    print(f"App {app_id}  spend_today before: {before} uALGO")
    if before == 0:
        print("Already zero; nothing to do.")
        return

    txn = transaction.ApplicationNoOpTxn(
        sender=sender,
        sp=client.suggested_params(),
        index=app_id,
        app_args=[SELECTOR],
    )
    try:
        txid = client.send_transaction(txn.sign(private_key))
    except Exception as e:
        print(f"Rejected: {describe_error(e)}", file=sys.stderr)
        print(
            "If this says 'assert failed', the sending account is not the app's "
            "admin. The admin is fixed at deploy time and cannot be changed.",
            file=sys.stderr,
        )
        sys.exit(1)

    wait_for_confirmation(client, txid)
    print(f"spend_today after:  {read_spend_today(client, app_id)} uALGO")
    print(f"Explorer: {EXPLORER_TX.format(txid)}")


if __name__ == "__main__":
    main()
