# SentinelPay 🛡️⚡

**Authorization and Policy-Enforcement Layer for Autonomous AI-Agent Payments on Algorand and x402**

*x402 Global Challenge Project*

---

## 1. What is SentinelPay?

**SentinelPay** sits between autonomous AI agent intent and economic payment settlement. 

While modern AI agents (powered by Deep Agents and LangGraph) can plan, research, and execute complex multi-step workflows, **they must not possess unrestricted direct authority to spend funds**. 

SentinelPay transforms proposed agent actions into canonical structured intents, evaluates them against deterministic spend policies and verifiers, issues cryptographic authorization attestations (Ed25519), and enforces this authorization on-chain through an Algorand smart contract in the atomic settlement group.

```text
User Objective & Budget
         │
         ▼
Managed Deep Agent (Deep Agents Harness)
         │
         ▼
SentinelPay Policy Gateway (Normalizer -> Policy Engine -> Intent Verifier)
         │
         ▼
Signed Attestation (Ed25519)
         │
         ▼
Algorand Atomic Transaction Group [Payment Tx + SentinelPay Contract App Call]
         │
         ▼
x402 Paid Resource Server (Serves content upon validated settlement)
```

---

## 2. Why x402 Agents Need SentinelPay

The HTTP 402 (`Payment Required`) standard and x402-avm enable machine-to-machine micropayments for API endpoints. However, autonomous agents consuming x402 resources are vulnerable to:

1. **Prompt Injection Attacks**: Injected text in web search results or tool outputs commanding the agent to drain funds or pay attackers.
2. **Runaway Spend Loops**: Recursive tool-calling spending unbounded micro-transactions.
3. **Destination Spoofing**: Adversarial manipulation redirecting payments to rogue addresses.

SentinelPay solves this by ensuring that **no payment can settle unless bound to an authorized, unexpired, unconsumed attestation** verified by an Algorand smart contract.

---

## 3. Project Status & Roadmap

| Component | Status | Description |
|---|---|---|
| **Intent Normalization & Hashing** | ✅ **Implemented** | Canonical extraction, string sanitization, and SHA-256 intent hashing |
| **Deterministic Policy Engine** | ✅ **Implemented** | Hard limits, daily spend cap tracking, tool & destination allowlists |
| **Attestation Signer & Verifier** | ✅ **Implemented** | Ed25519 cryptographic signing & tamper-detection |
| **Deep Agent Harness** | ✅ **Implemented** | Autonomous planning, tool boundaries, prompt injection resilience |
| **x402 FastAPI Server & Middleware** | ✅ **Implemented** | 402 challenge issuance and SentinelPay-AVM settlement verification |
| **Algorand Smart Contract Logic** | ✅ **Implemented** | Reference AVM logic for atomic group validation, replay defense, and cap tracking |
| **PyTeal Contract (deployable)** | ✅ **Implemented** | Real compiling AVM v8 program with Box-storage replay protection (`contracts/pyteal_contract.py`) |
| **GoPlausible Facilitator Client** | ✅ **Implemented** | `verify()`/`settle()` HTTP client against the public reference facilitator (`sentinelpay/payments/facilitator.py`) |
| **TestNet Deploy Script** | ✅ **Deployed Live** | `scripts/deploy_testnet.py` — executed against live Algorand TestNet |
| **Live TestNet Contract** | ✅ **Live** | App ID [`769239295`](https://testnet.explorer.perawallet.app/application/769239295) — verifier key & spend cap baked into on-chain global state |
| **Live Atomic Group Broadcast** | 🔵 **Next** | Real `[payment + app-call]` settlement via GoPlausible on Algorand TestNet |
| **Algorand MainNet Promotion** | 🔵 **Planned** | MainNet deployment for x402 Global Challenge submission |

---

## 4. Repository Structure

```text
sentinelpay/
├── README.md                          # Project documentation and guide
├── LICENSE                            # MIT License
├── pyproject.toml                     # Python dependencies & build config
├── .env.example                       # Environment variables template
├── .gitignore                         # Secret and cache protection
│
├── docs/
│   ├── architecture.md                # System architecture & transaction lifecycle
│   ├── threat-model.md                # 7 Security invariants & threat matrix
│   ├── protocol.md                    # Data structures & atomic group spec
│   └── demo-scenarios.md              # Scenario A (Legitimate) & Scenario B (Attack)
│
├── agent/
│   ├── agent.py                       # DeepAgent harness & execution logic
│   ├── AGENTS.md                      # Agent roles & boundaries
│   ├── tools/                         # Free & protected paid tool abstractions
│   ├── skills/                        # Agent skill definitions
│   └── subagents/                     # Specialized researcher delegation
│
├── sentinelpay/
│   ├── policy/                        # Deterministic rules, limits & evaluator
│   ├── intent/                        # Normalizer, models & SHA-256 hasher
│   ├── verifier/                      # Ed25519 signer & semantic verifier
│   ├── payments/                      # x402 challenge parser & settlement proofs
│   ├── gateway/                       # Core SentinelPay middleware gateway
│   └── config.py                      # Settings management
│
├── contracts/
│   ├── sentinelpay.py                 # AVM smart contract & reference validator
│   ├── README.md                      # Contract deployment notes
│   └── tests/test_sentinelpay.py      # On-chain rule unit tests
│
├── services/
│   ├── api/app.py                     # x402 paid resource endpoint (FastAPI)
│   └── verifier/app.py                # Standalone verifier service (FastAPI)
│
├── tests/
│   ├── unit/                          # Policy, intent, and attestation tests
│   ├── integration/                   # End-to-end x402 payment flow
│   └── attacks/                       # Prompt injection, bypass, replay, spend cap
│
├── scripts/
│   ├── dev.py                         # Development server runner
│   ├── fund_testnet.py                # Algorand TestNet account generator
│   └── run_demo.py                    # Interactive demo selector
│
└── examples/
    ├── legitimate_flow.py             # Scenario A: Legitimate payment run
    └── prompt_injection_flow.py       # Scenario B: Prompt injection defense run
```

---

## 5. Security Invariants

1. **Invariant 1 — No Direct Wallet Authority**: Agents never hold unrestricted signing keys.
2. **Invariant 2 — Exact-Action Authorization Binding**: Attestations cryptographically bind amount, recipient, agent, and goal.
3. **Invariant 3 — On-Chain Enforcement**: A bare payment without SentinelPay app call fails settlement.
4. **Invariant 4 — Replay Resistance**: Nonce consumption prevents authorization reuse.
5. **Invariant 5 — Hard Spend Caps**: Contract-level cumulative spend limits cannot be exceeded.
6. **Invariant 6 — Verifier Isolation**: Verifier never ingests arbitrary raw tool output.
7. **Invariant 7 — Destination Allowlisting**: Payments restricted to authorized recipients.

---

## 6. Quickstart & Local Setup

### Prerequisites
- Python 3.11+
- `uv` package manager

### Installation

```bash
# Clone the repository
cd sentinelpay

# Install dependencies with uv
uv sync
```

### Running Tests

```bash
# Run unit, integration, contract, and adversarial attack tests
uv run pytest -v
```

### Running the Demos

```bash
# Run Legitimate Flow (Scenario A)
uv run python examples/legitimate_flow.py

# Run Prompt Injection Defense (Scenario B)
uv run python examples/prompt_injection_flow.py

# Or launch the interactive CLI runner
uv run python scripts/run_demo.py
```

### Starting the x402 Resource API

```bash
uv run python -m services.api.app
```

### Compiling & Deploying the Smart Contract (requires TestNet network access)

```bash
# 1. Compile PyTeal → TEAL artifacts (fully local, no network needed)
uv run python contracts/compile.py

# 2. Generate a TestNet account, then fund it via the dispenser link it prints
uv run python scripts/fund_testnet.py

# 3. Generate your Ed25519 verifier keypair and add both to .env
uv run python -c "
import base64
from cryptography.hazmat.primitives.asymmetric import ed25519
priv = ed25519.Ed25519PrivateKey.generate()
pub  = priv.public_key()
print('VERIFIER_PUBLIC_KEY=' + base64.b64encode(pub.public_bytes_raw()).decode())
print('VERIFIER_PRIVATE_KEY=' + base64.b64encode(priv.private_bytes_raw()).decode())
"
# Wrap the values in double quotes in .env to preserve base64 padding (=)

# 4. Add AGENT_MNEMONIC and quoted VERIFIER_PUBLIC_KEY/VERIFIER_PRIVATE_KEY to .env

# 5. Deploy
uv run python scripts/deploy_testnet.py --max-daily-spend 1000000
# Prints SENTINELPAY_APP_ID — add it to .env
```

**Live TestNet contract**: App ID [`769239295`](https://testnet.explorer.perawallet.app/application/769239295)

---

## 7. Zero-Paid-Service Baseline

SentinelPay is architected to be completely functional locally without requiring paid API subscriptions:
- **Zero Paid LLM APIs**: Uses deterministic rules and local verifiers by default.
- **Zero Paid RPCs**: Uses public Algorand TestNet nodes (`algonode.cloud`).
- **Open Standards**: Fully compatible with x402 and Deep Agents.
