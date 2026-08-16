"""
Generate an Algorand TestNet account for SentinelPay.

Usage:
    uv run python scripts/fund_testnet.py

Prints a fresh address and mnemonic, then tells you where to fund it. The
mnemonic is printed once and stored nowhere — put it straight into .env, which
is gitignored.
"""

from algosdk import account, mnemonic

# The older bank.testnet.algorand.network dispenser now 301s here.
DISPENSER_URL = "https://lora.algokit.io/testnet/fund"


def generate_testnet_account() -> None:
    private_key, address = account.generate_account()
    passphrase = mnemonic.from_private_key(private_key)

    print("=== New Algorand TestNet Account ===")
    print(f"Address:  {address}")
    print(f"Mnemonic: {passphrase}")
    print(f"\nFund it at the TestNet dispenser: {DISPENSER_URL}")
    print(
        "\nThen add to .env:\n"
        f"  AGENT_MNEMONIC={passphrase}\n"
        f"  RESOURCE_OWNER_ADDRESS={address}   # or a second account you control\n"
        "\nThis mnemonic controls real TestNet funds. Never commit it."
    )


if __name__ == "__main__":
    generate_testnet_account()
