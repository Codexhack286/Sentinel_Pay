"""Algorand TestNet account utility for SentinelPay."""

import algosdk
from algosdk import account, mnemonic


def generate_testnet_account():
    """Generates a new Algorand TestNet keypair and mnemonic."""
    private_key, address = account.generate_account()
    passphrase = mnemonic.from_private_key(private_key)
    print("=== New Algorand TestNet Account ===")
    print(f"Address:  {address}")
    print(f"Mnemonic: {passphrase}")
    print("\nTo fund this account, visit the Algorand TestNet Dispenser:")
    print("👉 https://bank.testnet.algorand.network/ or https://testnet.algoexplorer.io/dispenser")
    print("Add this address and mnemonic to your .env file.")


if __name__ == "__main__":
    generate_testnet_account()
