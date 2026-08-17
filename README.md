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
| **Adversarial Settlement Proof** | ✅ **Verified on TestNet** | 6 attack classes submitted to Algorand; every one rejected by the contract itself, at a named opcode |
| **On-chain Settlement Binding** | ✅ **Verified on TestNet** | The resource server serves only once the contract's nonce box confirms the payment settled; unreachable chain fails closed |
| **Full x402 Roundtrip** | ✅ **Verified on TestNet** | `scripts/live_roundtrip.py` — the identical request returns 402 before the broadcast and 200 after |
| **TestNet Deploy Script** | ✅ **Implemented** | `scripts/deploy_testnet.py` |
| **Live TestNet Contract** | ✅ **Live** | App [`769368669`](https://testnet.explorer.perawallet.app/application/769368669) — verifier key and spend cap in on-chain global state |
| **Live Atomic Group Broadcast** | ✅ **Settled** | [`7KRNWCNN...`](https://testnet.explorer.perawallet.app/tx/7KRNWCNNGUOZKEPOVZD3H4GYQWBOF6WGSN45XUZESB74OOKFDJRA) — round 66376855 |
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
│   ├── planner.py                     # Rule-based + optional local-LLM planning
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
│   ├── payments/                      # x402 parsing, group builder, settlement, facilitator
│   ├── gateway/                       # Core SentinelPay middleware gateway
│   ├── keys.py                        # Shared verifier signing identity
│   └── config.py                      # Settings management
│
├── contracts/
│   ├── pyteal_contract.py             # Deployable AVM v8 program
│   ├── reference_model.py             # Pure-Python model of the same invariants
│   ├── compile.py                     # PyTeal -> contracts/build/*.teal
│   ├── README.md                      # Contract deployment notes
│   └── tests/                         # Reference-model + compiled-TEAL tests
│
├── services/
│   ├── api/app.py                     # x402 paid resource endpoint (FastAPI)
│   └── verifier/app.py                # Standalone verifier service (FastAPI)
│
├── tests/
│   ├── unit/                          # Policy, intent, attestation, agent, settlement
│   ├── integration/                   # End-to-end x402 payment flow
│   └── attacks/                       # Prompt injection, bypass, replay, spend cap
│
├── scripts/
│   ├── _chain.py                      # Shared algod client & confirmation helpers
│   ├── gen_verifier_key.py            # Generate the shared verifier identity
│   ├── fund_testnet.py                # Algorand TestNet account generator
│   ├── deploy_testnet.py              # Deploy the SentinelPay app
│   ├── deploy_budget_app.py           # Deploy the opcode-budget helper app
│   ├── fund_app_mbr.py                # Fund the app account for nonce boxes
│   ├── check_balance.py               # Pre-flight: balances + verifier key match
│   ├── live_broadcast.py              # Legitimate on-chain settlement
│   ├── live_roundtrip.py              # Full 402 -> authorize -> settle -> 200 loop
│   ├── verify_attack.py               # Proves unauthorized groups do not settle
│   ├── admin_reset_spend.py           # Zero the on-chain spend counter (admin only)
│   ├── dev.py                         # Development server runner
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

### LangSmith Tracing (optional)

Core payment and agent paths are decorated with LangSmith `@traceable`, so every
run (agent planning, tool calls, gateway checks, policy evaluation, verification,
x402 endpoints) shows up as a trace tree.

```bash
# Enable: set a key (and optionally a project). Copy from .env.example:
LANGSMITH_API_KEY=lsv2_pt_...      # enables tracing
LANGSMITH_PROJECT=sentinelpay      # default project when unset
LANGSMITH_TRACING=false            # force off for a single run, key or not
```

With `LANGSMITH_API_KEY` set, tracing turns on automatically; the decorators are
transparent no-ops when no key is present. Each run of a decorated function
appears as a nested trace in your project at https://smith.langchain.com — open a
trace to see the full `deep_agent_run → plan_task → free_research_tool_execute →
propose_payment → sentinelpay_gateway_process_payment_request → policy/verifier`
pipeline, its inputs/outputs, and per-step timing.

### Deploy the Agent as a LangGraph (optional)

`DeepAgent` is wrapped as a single-node compiled LangGraph at `agent/graph.py`,
so the exact same harness (planning, tools, SentinelPay gateway, policy and
verifier) can run inside LangSmith Deployments without rewriting any internals.
The graph input is `{"user_objective": "...", "simulate_attack": false}` and the
output is an `AgentExecutionLog`.

```bash
# Local dev server (no deploy needed)
uv run --with langgraph-cli[inmem] langgraph dev

# Deploy to LangSmith (builds from langgraph.json, uploads, creates a deployment)
uv tool install langgraph-cli
langgraph deploy --name sentinelpay-agent
```

The deployment is reachable over HTTP at `/invoke` (POST) with the graph state
above. Once deployed, traces appear automatically in the deployment's LangSmith
project.

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

# 3. Generate the shared Ed25519 verifier identity and add both values to .env
uv run python scripts/gen_verifier_key.py
# Wrap the values in double quotes in .env to preserve base64 padding (=)

# 4. Add AGENT_MNEMONIC and quoted VERIFIER_PUBLIC_KEY/VERIFIER_PRIVATE_KEY to .env

# 5. Deploy the SentinelPay app and the opcode-budget helper
uv run python scripts/deploy_testnet.py --max-daily-spend 1000000
uv run python scripts/deploy_budget_app.py
# Add the printed SENTINELPAY_APP_ID and BUDGET_APP_ID to .env

# 6. Fund the app account for nonce-box storage, then settle and attack it
uv run python scripts/fund_app_mbr.py
uv run python scripts/live_roundtrip.py     # the full 402 -> pay -> 200 loop
uv run python scripts/verify_attack.py --broadcast   # attacks rejected on-chain
```

**Live TestNet deployment**: SentinelPay app
[`769368669`](https://testnet.explorer.perawallet.app/application/769368669),
budget helper [`769368677`](https://testnet.explorer.perawallet.app/application/769368677).
Full transaction list and the per-opcode adversarial results are in
[SETUP.md](SETUP.md#testnet-contract-info-live).

> The earlier apps (`769239295` / `769240052`) came from a contract revision that
> did not bind destination, amount and nonce to the signed attestation — a single
> valid authorization could settle any amount to any address. They are superseded
> and must not be reused. See [docs/status.md](docs/status.md) §2.

---

## 7. Zero-Paid-Service Baseline

SentinelPay is architected to be completely functional locally without requiring paid API subscriptions:
- **Zero Paid LLM APIs**: Uses deterministic rules and local verifiers by default.
- **Zero Paid RPCs**: Uses public Algorand TestNet nodes (`algonode.cloud`).
- **Open Standards**: Fully compatible with x402 and Deep Agents.
