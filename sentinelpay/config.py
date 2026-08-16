"""Configuration management for SentinelPay."""

from typing import Optional

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Stand-in used when no real payee is configured. Not a valid Algorand address,
# on purpose: offline demos work, on-chain flows fail loudly instead of
# broadcasting a payment to a nonsense destination.
PLACEHOLDER_RESOURCE_OWNER = "RESOURCE_OWNER_ALGORAND_ADDRESS_AAAAAAAAAAAAAAAAAAAAAAAAAAAA"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    # App config
    APP_ENV: str = "development"
    DEBUG: bool = True

    # Agent planner. "local" = deterministic rules (default, reproducible);
    # "ollama" = a free local model, falling back to rules if unreachable.
    MODEL_PROVIDER: str = "local"
    MODEL_NAME: str = "llama3.2:3b"

    # Optional LangSmith
    LANGSMITH_API_KEY: Optional[str] = None

    # Algorand TestNet Config
    ALGOD_ADDRESS: str = "https://testnet-api.algonode.cloud"
    ALGOD_PORT: int = 443
    ALGOD_TOKEN: str = ""
    INDEXER_ADDRESS: str = "https://testnet-idx.algonode.cloud"
    INDEXER_PORT: int = 443
    INDEXER_TOKEN: str = ""

    # Accounts & App IDs
    AGENT_MNEMONIC: Optional[str] = None
    VERIFIER_MNEMONIC: Optional[str] = None
    # Deploys and admin-resets the contract. Falls back to AGENT_MNEMONIC when
    # unset so a single-wallet TestNet setup still works, but keep them separate
    # for anything beyond a local demo: the agent account is the one exposed to
    # a potentially compromised agent.
    CONTRACT_CREATOR_MNEMONIC: Optional[str] = None
    SENTINELPAY_APP_ID: int = 0
    BUDGET_APP_ID: int = 0  # Trivial always-approve app for opcode budget pooling

    # Verifier Ed25519 signing identity. Generate with scripts/gen_verifier_key.py.
    # The private key is a base64 32-byte seed and must never be committed.
    VERIFIER_PUBLIC_KEY: Optional[str] = None
    VERIFIER_PRIVATE_KEY: Optional[str] = None

    # Address the demo x402 resource is paid to. Must be a real Algorand address
    # for any on-chain flow; the placeholder default only supports offline demos.
    RESOURCE_OWNER_ADDRESS: str = PLACEHOLDER_RESOURCE_OWNER
    RESOURCE_PRICE_UALGO: int = 100_000

    # API Ports
    API_PORT: int = 8000
    VERIFIER_PORT: int = 8001

    # GoPlausible x402-avm Facilitator
    FACILITATOR_URL: str = "https://facilitator.goplausible.xyz"
    X402_NETWORK: str = "algorand:SGO1GKSzyE7IEPItTxCByw9x8FmnrCDexi9/cOUJOiI="

    @model_validator(mode="after")
    def _blank_optional_strings_fall_back_to_defaults(self) -> "Settings":
        # A key present but empty in .env (`RESOURCE_OWNER_ADDRESS=`) otherwise
        # overrides the default with "", which is worse than not setting it.
        if not self.RESOURCE_OWNER_ADDRESS.strip():
            self.RESOURCE_OWNER_ADDRESS = PLACEHOLDER_RESOURCE_OWNER
        for key in ("AGENT_MNEMONIC", "VERIFIER_MNEMONIC", "CONTRACT_CREATOR_MNEMONIC",
                    "VERIFIER_PUBLIC_KEY", "VERIFIER_PRIVATE_KEY", "LANGSMITH_API_KEY"):
            if not (getattr(self, key) or "").strip():
                setattr(self, key, None)
        return self

    @property
    def admin_mnemonic(self) -> Optional[str]:
        """Mnemonic used for deploy and admin calls."""
        return self.CONTRACT_CREATOR_MNEMONIC or self.AGENT_MNEMONIC


settings = Settings()
