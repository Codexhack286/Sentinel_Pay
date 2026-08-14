# SentinelPay Architecture

## 1. Overview
SentinelPay is an **authorization and policy-enforcement layer for autonomous AI-agent payments** in x402-enabled ecosystems.

The central thesis:
> AI agents should be able to reason, plan, and act autonomously, but they must **never** have unrestricted direct authority to spend money. SentinelPay sits between agent intent and economic settlement, binding structured, independently verified intent to the exact payment and enforcing authorization through an Algorand smart contract in the atomic settlement group.

```text
User Objective & Budget
         │
         ▼
Managed Deep Agent (Deep Agents Harness)
  ├── Task Planning
  ├── Subagent Delegation (e.g., Researcher)
  └── Proposed Economic Action
         │
         ▼
SentinelPay Payment Gateway / Middleware
         │
         ├── 1. Intent Normalizer (strip untrusted context -> canonical fields)
         ├── 2. Deterministic Policy Engine (caps, allowlists, currency)
         └── 3. Semantic Intent Verifier (task-scope alignment)
         │
         ▼
Cryptographically Signed Attestation (Ed25519)
         │
         ▼
Algorand Atomic Transaction Group
  ├── Tx 0: Payment Transaction (Asset transfer / micro-ALGO)
  ├── Tx 1: SentinelPay Contract App Call (Validates Attestation, Nonce, Spend Caps)
  └── Tx 2: x402 Resource / Settlement Proof
         │
         ▼
x402 Paid Endpoint (Serves resource upon on-chain verification)
```

## 2. Security Boundaries & Trust Levels

| Component | Responsibility | Trust Level | Notes |
|---|---|---|---|
| **Deep Agent** | Reasoning, tool execution, delegation | **Untrusted** | May be manipulated via prompt injection or rogue plans |
| **Intent Normalizer** | Extracts canonical fields for authorization | **Untrusted Processor** | Ignores untrusted long-form tool/web page outputs |
| **Policy Engine** | Hard limits, daily spend caps, allowlists | **Trusted** | Deterministic check; cannot be overridden by LLM |
| **Intent Verifier** | Validates task-goal alignment | **Trusted (Fallible)** | Structured input only; fails closed |
| **Attestation Signer** | Signs canonical authorization object | **Highly Trusted** | Private key isolated from agent runtime |
| **SentinelPay Contract** | On-chain settlement & group validation | **Enforcement Boundary** | Guarantees atomic group validity before funds move |
| **x402 Facilitator** | Facilitates settlement & proofs | **External Infrastructure**| Does not act as policy authority |

## 3. Transaction Flow Lifecycle

1. **Challenge Discovery (HTTP 402)**: The Deep Agent requests a paid resource (e.g. `GET /paid-tool`). The server responds with `HTTP 402 Payment Required` detailing recipient, amount, asset, and network requirements.
2. **Intent Construction**: The agent generates a structured payment proposal without having raw wallet keys.
3. **Canonical Normalization**: SentinelPay normalizes the intent to isolate critical fields (`agent_id`, `tool`, `resource`, `amount`, `destination`, `expiry`).
4. **Policy & Verification Gate**:
   - Deterministic checks verify limits (per-transaction, daily, tool allowlist, destination allowlist).
   - Verifier checks task alignment.
   - If approved, an Ed25519 signed `Attestation` is produced.
5. **Atomic Transaction Grouping**: An Algorand atomic transaction group is formed combining the payment transaction with the SentinelPay verification app call.
6. **Smart Contract Verification**: The Algorand contract inspects the group:
   - Verifies verifier signature against configured public key.
   - Validates that payment parameters match the attested intent.
   - Enforces spend caps and marks the unique nonce/lease as consumed.
7. **Settlement & Fulfillment**: If the atomic group confirms, the resource server verifies the group execution and returns `HTTP 200 OK` with the paid resource payload.
