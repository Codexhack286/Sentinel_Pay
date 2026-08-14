# SentinelPay — Setup & Usage Guide

Complete walkthrough: local development → TestNet deployment → live settlement.

---

## Prerequisites

| Tool | Version | Install |
|------|---------|---------|
| Python | 3.11+ | [python.org](https://python.org) |
| `uv` | latest | `pip install uv` |
| Git | any | [git-scm.com](https://git-scm.com) |

---

## Part 1 — Local Setup (No Network Required)

### 1. Clone & Install

```bash
git clone https://github.com/Codexhack286/Sentinel_Pay.git
cd Sentinel_Pay-main
uv sync
```

### 2. Copy the environment template

```bash
cp .env.example .env
```

Leave everything blank for now — local demos and tests work without any keys.

### 3. Run the test suite (61/61 should pass)

```bash
uv run pytest -v
```

### 4. Run the demo scenarios

```bash
# Scenario A: Legitimate payment flow — policy approves, attestation issued
uv run python examples/legitimate_flow.py

# Scenario B: Prompt injection attack — policy blocks, no funds moved
uv run python examples/prompt_injection_flow.py

# Interactive menu
uv run python scripts/run_demo.py
```

### 5. Start the services locally

Open two terminals:

**Terminal 1 — x402 Resource Server (paywall):**
```bash
uv run python -m services.api.app
# Running on http://127.0.0.1:8000
```

**Terminal 2 — Verifier Node (attestation signer):**
```bash
uv run python -m services.verifier.app
# Running on http://127.0.0.1:8001
```

**Test them:**
```bash
curl.exe http://127.0.0.1:8000/          # API health + verifier public key
curl.exe http://127.0.0.1:8000/paid-dataset  # Returns HTTP 402 challenge (expected)
curl.exe http://127.0.0.1:8001/          # Verifier health + public key
```

Swagger UI (browser):
- `http://127.0.0.1:8000/docs`
- `http://127.0.0.1:8001/docs`

---

## Part 2 — TestNet Deployment

### Step 1 — Generate Ed25519 Verifier Keypair

```bash
uv run python -c "
import base64
from cryptography.hazmat.primitives.asymmetric import ed25519
priv = ed25519.Ed25519PrivateKey.generate()
pub  = priv.public_key()
print('VERIFIER_PUBLIC_KEY=' + base64.b64encode(pub.public_bytes_raw()).decode())
print('VERIFIER_PRIVATE_KEY=' + base64.b64encode(priv.private_bytes_raw()).decode())
"
```

Add both values to `.env`. **Wrap them in double quotes** to preserve the `=` padding:
```
VERIFIER_PUBLIC_KEY="<paste here>"
VERIFIER_PRIVATE_KEY="<paste here>"
```

### Step 2 — Generate & Fund an Algorand TestNet Account

```bash
uv run python scripts/fund_testnet.py
```

This prints an **address** and **25-word mnemonic**. Copy the mnemonic to `.env`:
```
AGENT_MNEMONIC="word1 word2 word3 ... word25"
```

Then fund the address at the Algorand TestNet Dispenser:
- **https://bank.testnet.algorand.network/**

Wait ~30 seconds for funds to arrive. Verify:
```bash
uv run python -c "
from algosdk.v2client import algod
from algosdk import account, mnemonic
from sentinelpay.config import settings
client = algod.AlgodClient(settings.ALGOD_TOKEN, settings.ALGOD_ADDRESS, headers={})
pk = mnemonic.to_private_key(settings.AGENT_MNEMONIC)
addr = account.address_from_private_key(pk)
info = client.account_info(addr)
print('Balance:', info['amount'] / 1_000_000, 'ALGO')
"
```

### Step 3 — Compile the Smart Contract

```bash
uv run python contracts/compile.py
# Writes contracts/build/approval.teal and clear.teal
```

### Step 4 — Deploy the SentinelPay Contract

```bash
uv run python scripts/deploy_testnet.py --max-daily-spend 1000000
```

On success, prints:
```
SentinelPay app deployed. App ID: <YOUR_APP_ID>
Add this to .env: SENTINELPAY_APP_ID=<YOUR_APP_ID>
```

Add `SENTINELPAY_APP_ID=<YOUR_APP_ID>` to `.env`.

View on explorer:
```
https://testnet.explorer.perawallet.app/application/<YOUR_APP_ID>
```

### Step 5 — Deploy the Budget Helper App

The SentinelPay contract uses `ed25519verify_bare` (1900 opcode units). The AVM
pools 700 units per app-call transaction — we need 2 extra always-approve calls
to reach 2100 units. This helper app provides them.

```bash
uv run python scripts/deploy_budget_app.py
# Prints: BUDGET_APP_ID=<id>
```

Add `BUDGET_APP_ID=<id>` to `.env`.

### Step 6 — Fund the Contract Account for Box Storage

The contract stores nonces in Algorand Box storage (replay protection). The app
account needs a minimum balance before the first payment:

```bash
uv run python scripts/fund_app_mbr.py
# Sends 0.5 ALGO to the contract account
```

### Step 7 — Smoke Test the Facilitator

```bash
uv run python scripts/smoke_test_facilitator.py
# Confirms GoPlausible facilitator is reachable and Algorand TestNet is listed
```

---

## Part 3 — Live Atomic Group Settlement

### Run the live broadcast

```bash
uv run python scripts/live_broadcast.py
```

**What this does:**
1. Builds a `PaymentIntent` for the demo dataset resource
2. Runs it through the SentinelPay gateway (policy check → verifier → Ed25519 attestation)
3. Constructs a 4-transaction atomic group:
   - `gtxn[0]` Payment 100,000 uALGO → resource owner
   - `gtxn[1]` SentinelPay `validate_and_pay` app call (verifies sig, nonce, amount, destination, spend cap)
   - `gtxn[2,3]` Budget NoOp calls to pool opcode budget
4. Submits to Algorand TestNet and waits for confirmation
5. Prints Pera Explorer links

**Expected output:**
```
SentinelPay Live Settlement Complete!
============================================================
  Payment Tx:   https://testnet.explorer.perawallet.app/tx/<TX_ID>
  Application:  https://testnet.explorer.perawallet.app/application/<APP_ID>
  Attestation:  attest_xxxxxxxxxxxx
  Round:        <ROUND>
```

---

## Quick Reference — All .env Variables

```ini
# ── Model (local dev — no changes needed) ─────────────────────────────────────
MODEL_PROVIDER=local
MODEL_NAME=mock-deep-agent

# ── Algorand TestNet nodes (public, no token needed) ──────────────────────────
ALGOD_ADDRESS=https://testnet-api.algonode.cloud
ALGOD_PORT=443
ALGOD_TOKEN=
INDEXER_ADDRESS=https://testnet-idx.algonode.cloud
INDEXER_PORT=443
INDEXER_TOKEN=

# ── Accounts (mnemonics — NEVER commit, always quote in .env) ─────────────────
AGENT_MNEMONIC="word1 word2 ... word25"    # creator + payment sender
VERIFIER_MNEMONIC=                          # optional second account

# ── Contract IDs (set after deployment) ───────────────────────────────────────
SENTINELPAY_APP_ID=769240052               # from deploy_testnet.py output
BUDGET_APP_ID=769240123                    # from deploy_budget_app.py output

# ── Verifier Ed25519 Keys (quote to preserve = padding) ───────────────────────
VERIFIER_PUBLIC_KEY="<base64>"             # baked into the contract on deploy
VERIFIER_PRIVATE_KEY="<base64>"            # used by verifier service to sign

# ── Service ports ──────────────────────────────────────────────────────────────
API_PORT=8000
VERIFIER_PORT=8001

# ── GoPlausible Facilitator ────────────────────────────────────────────────────
FACILITATOR_URL=https://facilitator.goplausible.xyz
X402_NETWORK=algorand:SGO1GKSzyE7IEPItTxCByw9x8FmnrCDexi9/cOUJOiI=
```

---

## Script Reference

| Script | Command | Purpose |
|--------|---------|---------|
| `fund_testnet.py` | `uv run python scripts/fund_testnet.py` | Generate Algorand TestNet account + faucet link |
| `compile.py` | `uv run python contracts/compile.py` | Compile PyTeal → TEAL bytecode |
| `deploy_testnet.py` | `uv run python scripts/deploy_testnet.py` | Deploy SentinelPay contract to TestNet |
| `deploy_budget_app.py` | `uv run python scripts/deploy_budget_app.py` | Deploy opcode-budget helper app |
| `fund_app_mbr.py` | `uv run python scripts/fund_app_mbr.py` | Fund contract account for Box MBR |
| `smoke_test_facilitator.py` | `uv run python scripts/smoke_test_facilitator.py` | Check GoPlausible facilitator uptime |
| `live_broadcast.py` | `uv run python scripts/live_broadcast.py` | End-to-end live atomic group settlement |
| `run_demo.py` | `uv run python scripts/run_demo.py` | Interactive demo menu |

---

## Common Issues

| Error | Cause | Fix |
|-------|-------|-----|
| `Incorrect padding` | `.env` parser strips `=` from base64 values | Wrap values in double quotes in `.env` |
| `overspend` | Deployer/agent account has 0 ALGO | Fund at https://bank.testnet.algorand.network/ |
| `dynamic cost budget exceeded` | `ed25519verify_bare` needs 1900 opcode units | Ensure `BUDGET_APP_ID` is set; re-run `deploy_budget_app.py` |
| `WrongKeyLengthError` | Placeholder address used as recipient | Check `RESOURCE_OWNER_ADDRESS` in `live_broadcast.py` |
| `/health 404` on verifier | Wrong route — verifier health is at `/` not `/health` | Use `curl.exe http://127.0.0.1:8001/` |
| `HTTP 402` from curl | Expected! 402 is the paywall challenge | Use `curl.exe` (not PowerShell alias) to see response body |

---

## TestNet Contract Info (Live)

| Item | Value |
|------|-------|
| SentinelPay App ID | `769240052` |
| Budget App ID | `769240123` |
| Live Settlement Tx | [`3CNWBV2L...`](https://testnet.explorer.perawallet.app/tx/3CNWBV2LSTEBDQV5MPQFLKCU6BLK4XO2VDOFQ3NPDRBGTJAGIL3A) |
| Confirmed Round | `66296621` |
| Explorer | [Pera TestNet](https://testnet.explorer.perawallet.app/application/769240052) · [Lora](https://lora.algokit.io/testnet/application/769240052) |
