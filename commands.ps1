cd Sentinel_Pay-main
uv sync                                    # or: pip install -e ".[dev]"

# Run everything local/offline:
uv run pytest -v                           # 61/61 tests
uv run python examples/legitimate_flow.py
uv run python examples/prompt_injection_flow.py
uv run python -m services.api.app          # x402 resource server, :8000
uv run python -m services.verifier.app     # standalone verifier node, :8001 (run separately)

# Contract compile (fully local, no network):
uv run python contracts/compile.py         # → contracts/build/{approval,clear}.teal

# TestNet deploy (needs real network access — not run from this sandbox):
uv run python scripts/fund_testnet.py      # generate + get dispenser link
# → add mnemonic + VERIFIER_PUBLIC_KEY to .env
uv run python scripts/deploy_testnet.py --max-daily-spend 1000000