"""
Step 1 — Fund the SentinelPay app account for box MBR.

The contract records consumed nonces in box storage (replay protection). Before
the first `validate_and_pay` call the app account must hold enough ALGO to back
those boxes:
    - App base MBR:  0.1 ALGO
    - Per-box MBR:   0.0025 + 0.0004/byte; a 32-byte key with a 1-byte value is
                     0.0157 ALGO per consumed nonce
    - Default below funds the base plus roughly 25 nonces.

Boxes are never deleted by the current contract, so this balance is consumed
permanently as the demo runs. Top it up with `--amount` if a long demo session
exhausts it.

Usage:
    uv run python scripts/fund_app_mbr.py [--amount 500000]
"""

import argparse

from algosdk import transaction
from algosdk.logic import get_application_address

from scripts._chain import (
    EXPLORER_TX,
    account_from_mnemonic,
    get_algod_client,
    require,
    wait_for_confirmation,
)
from sentinelpay.config import settings

DEFAULT_FUND_AMOUNT_UALGO = 500_000


def main() -> None:
    parser = argparse.ArgumentParser(description="Fund the SentinelPay app account for box MBR")
    parser.add_argument(
        "--amount",
        type=int,
        default=DEFAULT_FUND_AMOUNT_UALGO,
        help=f"Target app-account balance in microAlgo (default {DEFAULT_FUND_AMOUNT_UALGO})",
    )
    args = parser.parse_args()

    require("AGENT_MNEMONIC", "SENTINELPAY_APP_ID")

    client = get_algod_client()
    private_key, sender = account_from_mnemonic(settings.AGENT_MNEMONIC)
    app_address = get_application_address(settings.SENTINELPAY_APP_ID)

    print(f"Sender (agent):   {sender}")
    print(f"App account:      {app_address}")
    print(f"App ID:           {settings.SENTINELPAY_APP_ID}")

    try:
        current = client.account_info(app_address).get("amount", 0)
    except Exception:
        # A never-funded app account does not exist yet, which algod reports as
        # an error rather than a zero balance.
        current = 0
    print(f"Current balance:  {current} uALGO")

    if current >= args.amount:
        print("App account already funded sufficiently. No action needed.")
        return

    top_up = args.amount - current
    print(f"Funding:          {top_up} uALGO ({top_up / 1_000_000:.3f} ALGO)")

    txn = transaction.PaymentTxn(
        sender=sender,
        sp=client.suggested_params(),
        receiver=app_address,
        amt=top_up,
        note=b"SentinelPay Box MBR funding",
    )
    txid = client.send_transaction(txn.sign(private_key))
    print(f"\nSubmitted funding txn: {txid}")

    confirmed = wait_for_confirmation(client, txid)
    print(f"Confirmed in round: {confirmed['confirmed-round']}")
    print("\nApp account funded. Ready for the first validate_and_pay call.")
    print(f"Explorer: {EXPLORER_TX.format(txid)}")


if __name__ == "__main__":
    main()
