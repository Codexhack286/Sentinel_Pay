"""
Check the configured TestNet accounts before spending fees on a deploy.

Reports the agent account balance, the SentinelPay app account's box-MBR
balance, and whether the verifier identity in .env matches the key baked into
the deployed contract. That last check catches the failure mode that otherwise
shows up as an opaque `logic eval error` at broadcast time.

Usage:
    uv run python scripts/check_balance.py
"""

import base64
import sys

from algosdk.logic import get_application_address

from scripts._chain import account_from_mnemonic, get_algod_client
from sentinelpay.config import settings

# First-time setup is the expensive part: two app deployments plus the box-MBR
# transfer, which is locked in the app account permanently.
RECOMMENDED_SETUP_BALANCE_UALGO = 1_000_000

# Once deployed, a full demo cycle (live_roundtrip + verify_attack --broadcast)
# costs only transaction fees — the payments are self-directed and net to zero.
# Roughly 10 transactions at the 0.001 ALGO minimum fee, plus headroom.
RECOMMENDED_RUN_BALANCE_UALGO = 100_000
ALGORAND_MIN_BALANCE_UALGO = 100_000


def algo(micro: int) -> str:
    return f"{micro / 1_000_000:.6f} ALGO"


def main() -> None:
    if not settings.AGENT_MNEMONIC:
        print("AGENT_MNEMONIC not set in .env.", file=sys.stderr)
        sys.exit(1)

    client = get_algod_client()
    _, agent_address = account_from_mnemonic(settings.AGENT_MNEMONIC)

    print(f"Agent address: {agent_address}")
    try:
        balance = client.account_info(agent_address).get("amount", 0)
    except Exception as e:
        print(f"  Could not reach algod at {settings.ALGOD_ADDRESS}: {e}", file=sys.stderr)
        sys.exit(1)

    print(f"  Balance: {algo(balance)}")
    if balance == 0:
        print("  NOT FUNDED. Paste the address above into https://lora.algokit.io/testnet/fund")
        sys.exit(1)

    # Algorand holds back a minimum balance that cannot be spent, so headroom is
    # what is left above it, not the raw balance.
    spendable = balance - ALGORAND_MIN_BALANCE_UALGO
    deployed = bool(settings.SENTINELPAY_APP_ID)
    needed = RECOMMENDED_RUN_BALANCE_UALGO if deployed else RECOMMENDED_SETUP_BALANCE_UALGO
    label = "demo runs" if deployed else "first-time setup (two deploys + box MBR)"

    print(f"  Spendable above the {algo(ALGORAND_MIN_BALANCE_UALGO)} minimum: {algo(spendable)}")
    if spendable < needed:
        print(f"  LOW for {label}: {algo(needed)} recommended.")
        print("  Top up at https://lora.algokit.io/testnet/fund")
    else:
        runs = spendable // 10_000  # ~0.01 ALGO of fees per full demo cycle
        print(f"  OK for {label}" + (f" (~{runs} full demo cycles)" if deployed else ""))

    if not settings.SENTINELPAY_APP_ID:
        print("\nSENTINELPAY_APP_ID not set; nothing deployed yet.")
        return

    app_address = get_application_address(settings.SENTINELPAY_APP_ID)
    print(f"\nSentinelPay app {settings.SENTINELPAY_APP_ID}")
    print(f"  App account: {app_address}")
    try:
        app_balance = client.account_info(app_address).get("amount", 0)
    except Exception:
        app_balance = 0
    print(f"  Box MBR balance: {algo(app_balance)}")
    if app_balance < 200_000:
        print("  Too low for nonce boxes. Run: uv run python scripts/fund_app_mbr.py")

    # Compare the on-chain verifier key against .env. A mismatch means every
    # attestation this machine signs will fail ed25519verify_bare on-chain.
    try:
        state = client.application_info(settings.SENTINELPAY_APP_ID)["params"]["global-state"]
    except Exception as e:
        print(f"  Could not read global state: {e}")
        return

    on_chain_key = next(
        (
            entry["value"]["bytes"]
            for entry in state
            if base64.b64decode(entry["key"]).decode(errors="replace") == "verifier_pk"
        ),
        None,
    )
    if on_chain_key is None:
        print("  verifier_pk not found in global state.")
    elif settings.VERIFIER_PUBLIC_KEY and on_chain_key == settings.VERIFIER_PUBLIC_KEY:
        print("  Verifier key matches .env  OK")
    else:
        print("  VERIFIER KEY MISMATCH — this app was deployed with a different key.")
        print(f"    on-chain: {on_chain_key}")
        print(f"    .env:     {settings.VERIFIER_PUBLIC_KEY}")
        print("    Redeploy with scripts/deploy_testnet.py, or restore the original key.")


if __name__ == "__main__":
    main()
