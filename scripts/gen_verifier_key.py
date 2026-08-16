"""
Generate the SentinelPay verifier Ed25519 identity.

Every process that issues or checks attestations must share one key: the
verifier service signs with it, the x402 resource server checks against it, and
the deployed Algorand contract stores the public half in global state. Without
a configured key each process mints its own and nothing validates anything.

Usage:
    uv run python scripts/gen_verifier_key.py

Copy both printed values into .env. The private key is a 32-byte Ed25519 seed;
it is a secret on the same level as a wallet mnemonic. Do not commit it, do not
paste it into an issue, and use different keys for TestNet and MainNet.
"""

from sentinelpay.verifier.attestation import AttestationSigner


def main() -> None:
    signer = AttestationSigner()
    print("Add these two lines to .env (they are NOT stored anywhere by this script):\n")
    print(f"VERIFIER_PUBLIC_KEY={signer.public_key_b64}")
    print(f"VERIFIER_PRIVATE_KEY={signer.private_key_b64}")
    print(
        "\nThe public key is baked into the contract by scripts/deploy_testnet.py, "
        "so redeploy the app if you ever rotate this key."
    )


if __name__ == "__main__":
    main()
