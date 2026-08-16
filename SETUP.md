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

### 3. Run the test suite (all should pass)

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

### Step 1 — Generate the Ed25519 Verifier Keypair

```bash
uv run python scripts/gen_verifier_key.py
```

Add both printed values to `.env`. **Wrap them in double quotes** to preserve
the `=` padding:
```
VERIFIER_PUBLIC_KEY="<paste here>"
VERIFIER_PRIVATE_KEY="<paste here>"
```

This one key is shared by every process: the verifier service signs with it, the
x402 resource server validates against it, and the deployed contract stores the
public half. If `VERIFIER_PRIVATE_KEY` is unset, each process mints a throwaway
key (with a warning) and nothing validates anything across process boundaries.

The private key is as sensitive as a wallet mnemonic. Use separate keys for
TestNet and MainNet, and never log or commit it.

### Step 2 — Generate & Fund an Algorand TestNet Account

```bash
uv run python scripts/fund_testnet.py
```

This prints an **address** and **25-word mnemonic**. Copy the mnemonic to `.env`:
```
AGENT_MNEMONIC="word1 word2 word3 ... word25"
```

Then fund the address at the Algorand TestNet Dispenser:
- **https://lora.algokit.io/testnet/fund** (the older
  `bank.testnet.algorand.network` URL redirects here)

Wait ~10 seconds for funds to arrive, then verify:
```bash
uv run python scripts/check_balance.py
```

This also reports the app account's box-MBR balance and whether the verifier key
in `.env` matches the one baked into the deployed contract — a mismatch there
otherwise surfaces much later as an opaque `logic eval error`.

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
uv run python scripts/fund_app_mbr.py --amount 300000
# ~0.0157 ALGO of minimum balance is locked per consumed nonce, permanently
```

### Step 7 — Smoke Test the Facilitator

```bash
uv run python scripts/smoke_test_facilitator.py
# Confirms GoPlausible facilitator is reachable and Algorand TestNet is listed
```

---

## Part 3 — Live Settlement

### The full x402 loop (recommended — this is the demo)

```bash
uv run python scripts/live_roundtrip.py
```

Runs the entire protocol against live TestNet in one command:

1. `GET /paid-dataset` with no payment -> **402** plus payment requirements
2. SentinelPay authorizes the exact payment and signs an attestation
3. The same request with that attestation, *before broadcasting* -> **402**
   ("payment not settled"). A valid signature is not a payment.
4. The protected atomic group is broadcast and confirms on-chain
5. The **identical** request -> **200**, resource served
6. A third attempt -> **403**, replay refused

Step 3 next to step 5 is the whole argument: same request, same signature, and
the only thing that changed is that the money actually moved.

### Run just the broadcast

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
MODEL_PROVIDER=local                       # or `ollama` for a real local model
MODEL_NAME=llama3.2:3b

# ── Algorand TestNet nodes (public, no token needed) ──────────────────────────
ALGOD_ADDRESS=https://testnet-api.algonode.cloud
ALGOD_PORT=443
ALGOD_TOKEN=
INDEXER_ADDRESS=https://testnet-idx.algonode.cloud
INDEXER_PORT=443
INDEXER_TOKEN=

# ── Accounts (mnemonics — NEVER commit, always quote in .env) ─────────────────
AGENT_MNEMONIC="word1 word2 ... word25"    # payment sender; funds the group fees
CONTRACT_CREATOR_MNEMONIC=                 # deploy + admin; falls back to AGENT_MNEMONIC
VERIFIER_MNEMONIC=                          # optional second account

# ── The resource being sold ───────────────────────────────────────────────────
RESOURCE_OWNER_ADDRESS=                    # real Algorand address; blank = pay self
RESOURCE_PRICE_UALGO=100000

# ── Contract IDs (set after deployment) ───────────────────────────────────────
SENTINELPAY_APP_ID=769368669               # from deploy_testnet.py output
BUDGET_APP_ID=769368677                    # from deploy_budget_app.py output

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
| `gen_verifier_key.py` | `uv run python scripts/gen_verifier_key.py` | Generate the shared verifier Ed25519 identity |
| `fund_testnet.py` | `uv run python scripts/fund_testnet.py` | Generate Algorand TestNet account + faucet link |
| `check_balance.py` | `uv run python scripts/check_balance.py` | Pre-flight: balances + verifier key match |
| `compile.py` | `uv run python contracts/compile.py` | Compile PyTeal → TEAL bytecode |
| `deploy_testnet.py` | `uv run python scripts/deploy_testnet.py` | Deploy SentinelPay contract to TestNet |
| `deploy_budget_app.py` | `uv run python scripts/deploy_budget_app.py` | Deploy opcode-budget helper app |
| `fund_app_mbr.py` | `uv run python scripts/fund_app_mbr.py` | Fund contract account for Box MBR |
| `smoke_test_facilitator.py` | `uv run python scripts/smoke_test_facilitator.py` | Check GoPlausible facilitator uptime |
| `live_broadcast.py` | `uv run python scripts/live_broadcast.py` | Live atomic group settlement |
| `live_roundtrip.py` | `uv run python scripts/live_roundtrip.py` | Full x402 loop: 402 -> authorize -> settle -> 200 |
| `admin_reset_spend.py` | `uv run python scripts/admin_reset_spend.py` | Zero the on-chain spend counter (admin only) |
| `verify_attack.py` | `uv run python scripts/verify_attack.py --broadcast` | Prove unauthorized groups are rejected on-chain |
| `run_demo.py` | `uv run python scripts/run_demo.py` | Interactive demo menu |

---

## Common Issues

| Error | Cause | Fix |
|-------|-------|-----|
| `Incorrect padding` | `.env` parser strips `=` from base64 values | Wrap values in double quotes in `.env` |
| `overspend` | Deployer/agent account has 0 ALGO | Fund at https://lora.algokit.io/testnet/fund |
| `dynamic cost budget exceeded` | `ed25519verify_bare` needs 1900 opcode units | Ensure `BUDGET_APP_ID` is set; re-run `deploy_budget_app.py` |
| `WrongKeyLengthError` | Placeholder address used as recipient | Set `RESOURCE_OWNER_ADDRESS` to a real address, or leave it blank to pay self |
| `Attestation has no AVM signature` | Destination is not a real Algorand address, so the attestation was never authorized for on-chain use | Set a valid `RESOURCE_OWNER_ADDRESS` |
| `VERIFIER_PRIVATE_KEY is not set` (warning) | No shared verifier identity configured | Run `scripts/gen_verifier_key.py` and fill in `.env` |
| `assert failed` / `logic eval error` on `validate_and_pay` | App deployed from an older contract revision whose argument layout differs | Recompile and redeploy: `contracts/compile.py`, then `scripts/deploy_testnet.py` |
| `/health 404` on verifier | Wrong route — verifier health is at `/` not `/health` | Use `curl.exe http://127.0.0.1:8001/` |
| `HTTP 402` from curl | Expected! 402 is the paywall challenge | Use `curl.exe` (not PowerShell alias) to see response body |

---

## TestNet Contract Info (live)

Deployed from the fixed contract and verified end to end on Algorand TestNet.

| Item | Value |
|------|-------|
| SentinelPay App ID | [`769368669`](https://testnet.explorer.perawallet.app/application/769368669) |
| Budget helper App ID | [`769368677`](https://testnet.explorer.perawallet.app/application/769368677) |
| Legitimate settlement | [`7KRNWCNN...`](https://testnet.explorer.perawallet.app/tx/7KRNWCNNGUOZKEPOVZD3H4GYQWBOF6WGSN45XUZESB74OOKFDJRA) — round 66376855 |
| Admin spend reset | [`ZPBCAD72...`](https://testnet.explorer.perawallet.app/tx/ZPBCAD72E3OQM3XO3H26O4XKRPP53NG3R7DUJI3FNUIJCK75KJBQ) |

### Adversarial results — every rejection came from the contract

`uv run python scripts/verify_attack.py --broadcast`

| Attack | Contract rejection |
|---|---|
| Amount substitution (100k authorized, 200k paid) | `pc=263  load 0; ==; assert` |
| Destination substitution | `pc=256  extract 8 32; ==; assert` |
| Blob tampering (signed bytes edited to match the attack) | `pc=229  ed25519verify_bare; assert` |
| Forged signature (attacker's own key) | `pc=229  ed25519verify_bare; assert` |
| Replay (authorization settled, then resubmitted) | `pc=287  box_create; assert` |

The bare payment settles as an ordinary transfer, as it must — it is just an
Algorand payment. It carries no authorization, consumes no nonce, and the
resource server refuses to serve against it.

> **Superseded.** Apps `769239295` / `769240052` came from the earlier contract
> revision, whose `validate_and_pay` took destination, amount and nonce as
> *unsigned* arguments with nothing binding them to the signed attestation. A
> single genuine authorization could settle any amount to any address there. Do
> not reuse them.
