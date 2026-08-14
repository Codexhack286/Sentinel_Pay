"""
Step 1 — Fund SentinelPay App Account for Box MBR.

The SentinelPay contract uses Algorand Box storage to record consumed nonces
(replay protection). Before the first `validate_and_pay` call, the app account
needs a minimum balance to cover the Box MBR:
    - App base MBR:  0.1 ALGO
    - Per-Box MBR:   0.0025 ALGO + 0.0004 ALGO/byte  (box key = nonce ~40 bytes)
                     ≈ 0.019 ALGO per nonce box
    - Safety buffer: fund 0.5 ALGO total to cover ~20 nonce boxes comfortably.

The sender is the AGENT_MNEMONIC account (same one used to deploy).

Usage:
    uv run python scripts/fund_app_mbr.py
"""

import sys

from algosdk import account, mnemonic, transaction
from algosdk.v2client import algod

from sentinelpay.config import settings

# Amount to send to the app account (in microAlgo). 0.5 ALGO covers ~20 nonce boxes.
FUND_AMOUNT_UALGO = 500_000


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
    if not settings.SENTINELPAY_APP_ID:
        print("SENTINELPAY_APP_ID not set in .env.", file=sys.stderr)
        sys.exit(1)

    client = get_algod_client()

    # Derive sender address from mnemonic
    private_key = mnemonic.to_private_key(settings.AGENT_MNEMONIC)
    sender = account.address_from_private_key(private_key)

    # App account address is deterministic: sha512/256("appID" || app_id_bytes)
    app_address = transaction.logic.get_application_address(settings.SENTINELPAY_APP_ID)

    print(f"Sender (agent):   {sender}")
    print(f"App account:      {app_address}")
    print(f"App ID:           {settings.SENTINELPAY_APP_ID}")
    print(f"Funding amount:   {FUND_AMOUNT_UALGO} uALGO ({FUND_AMOUNT_UALGO / 1_000_000:.3f} ALGO)")

    # Check current app account balance
    try:
        info = client.account_info(app_address)
        current = info.get("amount", 0)
        print(f"App account current balance: {current} uALGO")
        if current >= FUND_AMOUNT_UALGO:
            print("App account already funded sufficiently. No action needed.")
            return
    except Exception:
        print("App account not yet funded (expected for new apps).")

    params = client.suggested_params()
    txn = transaction.PaymentTxn(
        sender=sender,
        sp=params,
        receiver=app_address,
        amt=FUND_AMOUNT_UALGO,
        note=b"SentinelPay Box MBR funding",
    )
    signed = txn.sign(private_key)
    txid = client.send_transaction(signed)
    print(f"\nSubmitted funding txn: {txid}")

    confirmed = wait_for_confirmation(client, txid)
    print(f"Confirmed in round: {confirmed['confirmed-round']}")
    print(f"\nApp account funded. Ready for first validate_and_pay call.")
    print(f"Explorer: https://testnet.explorer.perawallet.app/tx/{txid}")


if __name__ == "__main__":
    main()
