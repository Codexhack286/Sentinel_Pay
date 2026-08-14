"""
Step 2 — Facilitator smoke test.

Checks that the GoPlausible x402-avm facilitator is reachable and that it
lists Algorand TestNet as a supported network before we attempt a live
atomic group broadcast.

Usage:
    uv run python scripts/smoke_test_facilitator.py
"""

import asyncio
import sys

from sentinelpay.payments.facilitator import (
    GoPlausibleFacilitatorClient,
    ALGORAND_TESTNET_CAIP2,
)


async def main() -> None:
    print("=== GoPlausible Facilitator Smoke Test ===\n")
    async with GoPlausibleFacilitatorClient() as client:
        # 1. Health check
        print("1. GET /health ...")
        try:
            health = await client.health()
            print(f"   OK  Status: {health}")
        except Exception as e:
            print(f"   FAIL /health failed: {e}", file=sys.stderr)
            sys.exit(1)

        # 2. Supported networks
        print("\n2. GET /supported ...")
        try:
            supported = await client.supported()
            print(f"   Raw response: {supported}")

            # Facilitator returns {'kinds': [...], ...} — check the kinds list
            kinds = supported.get("kinds", [])
            networks = [k.get("network", "") for k in kinds] if isinstance(kinds, list) else []

            if any(ALGORAND_TESTNET_CAIP2 in n for n in networks):
                print(f"   OK  Algorand TestNet is supported.")
            else:
                print(f"   WARN  Algorand TestNet not found in supported list.")
                print(f"         Networks found: {networks}")
        except Exception as e:
            print(f"   FAIL /supported failed: {e}", file=sys.stderr)
            sys.exit(1)

    print("\nOK  Facilitator is live and reachable. Proceed to live broadcast.")


if __name__ == "__main__":
    asyncio.run(main())
