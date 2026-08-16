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
  ├── Tx 0: Payment Transaction (micro-ALGO)
  ├── Tx 1: SentinelPay validate_and_pay App Call
  │         (signature, destination, amount, expiry, spend cap, nonce box)
  └── Tx 2+: Opcode-budget NoOps (no logic; they only pool AVM budget)
         │
         ▼
x402 Paid Endpoint
  └── Serves the resource only after confirming on-chain that the
      contract consumed this authorization's nonce
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
   - Verifies the verifier signature over the fixed-layout authorization blob.
   - Reads destination, amount, nonce and expiry *out of those signed bytes* and
     compares them to the actual payment — nothing arrives as an unsigned
     argument that a caller could substitute.
   - Rejects `CloseRemainderTo` and `RekeyTo` on both transactions.
   - Enforces the cumulative spend cap and writes the nonce to box storage.
7. **Settlement & Fulfillment**: The resource server looks up the nonce box on
   chain. Because that box is written only by a successful `validate_and_pay`,
   its presence transitively proves a matching payment settled — so the server
   returns `HTTP 200 OK` with the payload. A missing box, or an unreachable
   node, returns `402`: unproven means unpaid.
