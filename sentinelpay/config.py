"""Configuration management for SentinelPay."""

from typing import Optional
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # App config
    APP_ENV: str = "development"
    DEBUG: bool = True
    
    # Model config (zero-cost baseline)
    MODEL_PROVIDER: str = "local"
    MODEL_NAME: str = "mock-deep-agent"
    
    # Optional LangSmith
    LANGSMITH_API_KEY: Optional[str] = None
    
    # Algorand TestNet Config
    ALGOD_ADDRESS: str = "https://testnet-api.algonode.cloud"
    ALGOD_PORT: int = 443
    ALGOD_TOKEN: str = ""
    INDEXER_ADDRESS: str = "https://testnet-idx.algonode.cloud"
    INDEXER_PORT: int = 443
    INDEXER_TOKEN: str = ""
    
    # Accounts & App ID
    AGENT_MNEMONIC: Optional[str] = None
    VERIFIER_MNEMONIC: Optional[str] = None
    SENTINELPAY_APP_ID: int = 0
    
    # Verifier Signing Key (for local testing/mocking)
    VERIFIER_PUBLIC_KEY: Optional[str] = None
    VERIFIER_PRIVATE_KEY: Optional[str] = None
    
    # API Ports
    API_PORT: int = 8000
    VERIFIER_PORT: int = 8001


settings = Settings()
