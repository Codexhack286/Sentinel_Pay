# SentinelPay — command cheat sheet.
# Not a script to execute top-to-bottom; copy the lines you need.

# ── Local / offline: no network, no keys, no funds ────────────────────────────
uv sync
uv run pytest -q
uv run python examples/legitimate_flow.py
uv run python examples/prompt_injection_flow.py
uv run python -m services.api.app          # x402 resource server, :8000
uv run python -m services.verifier.app     # verifier node, :8001 (separate terminal)
uv run python contracts/compile.py         # -> contracts/build/{approval,clear}.teal

# ── TestNet: needs network access and a funded account ───────────────────────
uv run python scripts/gen_verifier_key.py  # -> VERIFIER_{PUBLIC,PRIVATE}_KEY in .env
uv run python scripts/fund_testnet.py      # -> AGENT_MNEMONIC in .env, then fund it
uv run python scripts/check_balance.py     # pre-flight: funded? keys match?
uv run python scripts/deploy_testnet.py --max-daily-spend 1000000
uv run python scripts/deploy_budget_app.py
uv run python scripts/fund_app_mbr.py

# ── Proof runs ────────────────────────────────────────────────────────────────
uv run python scripts/smoke_test_facilitator.py
uv run python scripts/live_broadcast.py                # legitimate settlement
uv run python scripts/live_roundtrip.py                # full 402 -> pay -> 200 loop
uv run python scripts/verify_attack.py                 # dry run, no funds needed
uv run python scripts/verify_attack.py --broadcast     # unauthorized groups rejected on-chain
uv run python scripts/admin_reset_spend.py             # zero spend_today between rehearsals
