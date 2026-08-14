# SentinelPay Project Status, Pending Tasks & Refinement Roadmap

**Current Version**: `0.3.0-beta`  
**Last Updated**: August 14, 2026 — Live TestNet Deployment ✅  
**Repository**: [https://github.com/Codexhack286/Sentinel_Pay](https://github.com/Codexhack286/Sentinel_Pay)

---

## 1. Executive Summary

SentinelPay is an authorization and policy-enforcement layer for autonomous AI-agent payments in x402 ecosystems. It prevents prompt-injection hijacking, runaway spending, and unauthorized transfers by ensuring that all agent-initiated payments must pass deterministic policy checks and verifier attestation before being executed in an Algorand smart contract atomic group.

**Current State**: Full local architecture, agent runtime, security engine, reference contract logic, **real deployable PyTeal contract**, attack testing matrix, and demo flows are **100% operational and verified (61/61 tests passing)**. The **SentinelPay smart contract is live on Algorand TestNet** (App ID: `769239295`) with the verifier public key and admin address baked into on-chain global state.

---

## 2. Completed Milestones ✅

### Phase 0: Repository Scaffolding & Tooling
- [x] Initialized uv-managed Python environment (`pyproject.toml`, `uv.lock`).
- [x] Configured zero-paid dependency baseline (`pydantic`, `fastapi`, `cryptography`, `py-algorand-sdk`, `pytest`).
- [x] Implemented environment security isolation (`.gitignore`, `.env.example`).
- [x] Set up Git version control and established remote repository on GitHub.

### Core SentinelPay Engine (`sentinelpay/`)
- [x] **Intent Normalization & Hashing** (`sentinelpay/intent/`): Normalizes raw agent proposals into canonical form, discards unverified payloads, and generates deterministic SHA-256 intent hashes.
- [x] **Deterministic Policy Engine** (`sentinelpay/policy/`): Enforces hard per-transaction caps, daily cumulative spend limits, tool allowlists, destination allowlists, currency checks, and expiration windows.
- [x] **Attestation & Cryptographic Signer** (`sentinelpay/verifier/`): Implemented Ed25519 digital signature signing and verification for authorization objects.
- [x] **Local Verifier** (`sentinelpay/verifier/verifier.py`): Zero-cost local task alignment and prompt-injection keyword filtering.
- [x] **Gateway Middleware** (`sentinelpay/gateway/middleware.py`): Orchestrates normalization, policy checks, verification, and attestation issuance.
- [x] **x402 Protocol Handler** (`sentinelpay/payments/x402.py`): Parses HTTP 402 challenges and constructs/verifies `SentinelPay-AVM` payment proofs.

### Agent Subsystem (`agent/`)
- [x] **DeepAgent Harness** (`agent/agent.py`): Autonomous task planning, tool delegation, and safe execution boundaries without direct wallet-signing privileges.
- [x] **Tool Boundaries** (`agent/tools/`): Separated unpriced discovery tools (`free_research`) from SentinelPay-gated tools (`paid_research`).
- [x] **Skills & Subagent Specs** (`agent/skills/`, `agent/subagents/`): Guidelines preventing obedience to text-based overrides and defining researcher delegation.

### Smart Contracts & Deployment (`contracts/`, `scripts/`)
- [x] **AVM Validation Logic** (`contracts/sentinelpay.py`): Reference logic for atomic group validation, signature checks, nonce consumption, and spend caps.
- [x] **Real PyTeal Contract** (`contracts/pyteal_contract.py`): Deployable AVM v8 program with **Box storage** for on-chain nonce replay protection.
- [x] **Compilation Pipeline** (`contracts/compile.py`): Generates `contracts/build/approval.teal` and `clear.teal`.
- [x] **TestNet Contract Deployed**: Deployed to Algorand TestNet at **App ID: `769239295`**.
- [x] **Budget Helper Deployed**: Deployed helper app for opcode pooling to satisfy `ed25519verify_bare` requirements.

### Services & API (`services/`)
- [x] **x402 Resource Endpoint** (`services/api/app.py`): FastAPI server returning HTTP 402 challenge and serving protected dataset upon receiving valid SentinelPay settlement proof.
- [x] **Standalone Verifier Node** (`services/verifier/app.py`): REST endpoint for policy evaluation and attestation signing.

### Facilitator Client (`sentinelpay/payments/facilitator.py`)
- [x] **GoPlausible Client**: Implemented client for `/verify`, `/settle`, `/health`, and `/supported`.
- [x] **Smoke Test Passed**: Verified live connection to GoPlausible facilitator and confirmed Algorand TestNet support.

### Adversarial & Test Suite — 61/61 Tests Passing
- [x] Unit tests for policy, intent, attestation, verifier, x402 handler, gateway, verifier REST service, and facilitator payload shaping.
- [x] Integration tests for the complete x402 payment flow.
- [x] 4 Adversarial attack tests: Prompt injection (Attack A), Verifier bypass (Attack B), Nonce replay (Attack C), Spend cap overrun (Attack D).
- [x] Contract compilation and invariant tests.

---

## 3. Pending Implementation & Execution Tasks 📋

```text
Local Architecture (Done) ──► TestNet Contract Deployed (Done) ──► Live Broadcast ──► Facilitator Roundtrip ──► MainNet & Pitch
```

### Task 1: Live On-Chain Broadcast Execution
- [ ] **Box MBR Funding**: Execute `scripts/fund_app_mbr.py` to deposit 0.5 ALGO MBR into the SentinelPay contract account (`SENTINELPAY_APP_ID=769239295`) for Box storage allocation.
- [ ] **Live Atomic Broadcast**: Run `scripts/live_broadcast.py` to broadcast a real `[Payment + SentinelPay validate_and_pay App Call]` atomic group to Algorand TestNet.
- [ ] **Capture On-Chain Tx Proofs**: Record confirmed transaction IDs and Pera Explorer links.

### Task 2: Live x402 Facilitator Roundtrip
- [ ] **Full Loop Settlement**: Connect `services/api/app.py` with `sentinelpay/payments/facilitator.py` so the resource server validates payment proofs directly via the GoPlausible facilitator on TestNet.
- [ ] **Facilitator Fallback Handling**: Implement seamless fallback to direct algod verification if the external facilitator experiences transient downtime.

---

## 4. Architectural & Component Refinements 🔧

### Refinement Track A — Deep Agent Runtime (Dynamic LLM & Prompt Injection)
* **Goal**: Transition from deterministic agent simulation to dynamic LLM tool calling while maintaining zero paid API dependency.
* **Tasks**:
  1. **Local LLM Integration**: Add optional integration with a free local model provider (e.g. **Ollama** running `llama3.2:1b`/`3b` or `mistral`, or LangChain/LangGraph local bindings).
  2. **Dynamic Tool Calling**: Let the LLM dynamically parse the user objective, decompose tasks, select tools, and format payment parameters.
  3. **Live Injection Resistance Test**: Feed live prompt-injected web snippets into the LLM context to showcase the LLM being deceived, but the payment being **firmly blocked by SentinelPay policy and verifier**.
  4. **Dedicated Agent Unit Tests**: Write direct unit tests for `agent/agent.py` and `agent/tools/` mocking dynamic LLM outputs.

### Refinement Track B — Semantic Verifier Hardening (Defense-in-Depth)
* **Goal**: Enhance task-goal alignment checks and eliminate keyword heuristics.
* **Tasks**:
  1. **Fix Category Substring False-Positive**: Refine category matching in `sentinelpay/verifier/verifier.py` so that tool names containing category tokens (e.g. `paid_research`) do not auto-pass unrelated declared goals.
  2. **Zero-Shot Semantic Cosine Similarity**: Integrate a small local embeddings model (e.g. `sentence-transformers/all-MiniLM-L6-v2`) to compute semantic cosine similarity between the declared `user_objective` and the proposed `payment_intent.declared_goal`.
  3. **Threshold Configuration**: Support configurable `verifier_threshold` (e.g., minimum cosine similarity of 0.75) in `AgentPolicy`.

### Refinement Track C — Smart Contract & Storage Economics (AVM Polish)
* **Goal**: Optimize contract storage costs and support multi-asset payments.
* **Tasks**:
  1. **ASA / USDC Payment Support**: Extend contract validation in `contracts/pyteal_contract.py` to inspect Asset Transfer transactions (`axfer`) in addition to native micro-ALGO payments (`pay`), supporting TestNet USDC.
  2. **Box Storage Cleanup / Nonce Pruning**: Add a contract method to prune expired nonce boxes after their timestamp window has passed, allowing reclaim of Minimum Balance Requirements (MBR).

### Refinement Track D — Visual Demo & Presentation Layer
* **Goal**: Provide engaging visual demonstrations for hackathon judges.
* **Tasks**:
  1. **Interactive Web Dashboard / Rich Terminal UI**: Build a visual dashboard (or Rich console visualizer) displaying:
     - Live Prompt → Agent Reasoning → SentinelPay Firewall Decision → On-Chain Atomic Group → Pera Explorer Link.
     - Side-by-side comparison: **Scene A (Legitimate Approved)** vs **Scene B (Prompt Injection Blocked)**.
  2. **2–3 Minute Demo Video**: Record the end-to-end demo highlighting the core pitch: *"Deterministic economic enforcement for probabilistic AI agents."*
  3. **Slide Deck & Architecture Visuals**: Prepare final hackathon presentation slides and exported flowcharts.

### Refinement Track E — MainNet Promotion (Competition Leaderboard)
* **Goal**: Satisfy official x402 Global Challenge competition requirements.
* **Tasks**:
  1. **MainNet Contract Deployment**: Compile and deploy the SentinelPay contract to Algorand MainNet.
  2. **Live MainNet Micropayment**: Execute a live micro-payment transaction via the GoPlausible facilitator to log an official entry on the challenge leaderboard.

---

## 5. Priority Matrix & Action Plan

| Area | Item | Priority | Complexity | Status |
|---|---|---|---|---|
| **Execution** | Fund App MBR & Broadcast Live TestNet Group | 🔴 High (P0) | Low | Ready to Run |
| **Execution** | Live Facilitator Roundtrip Verification | 🔴 High (P0) | Medium | In Progress |
| **Security** | Semantic Verifier Substring Fix & Cosine Similarity | 🟡 Medium (P1) | Low | Planned |
| **AI Agent** | Local LLM (Ollama / LangChain) Dynamic Tool Calling | 🟡 Medium (P1) | Medium | Planned |
| **Contract** | ASA / USDC Support & Nonce Pruning | 🟡 Medium (P1) | Medium | Planned |
| **Presentation**| Rich Terminal / Web UI Demo Visualizer | 🟢 Polish (P2) | Medium | Planned |
| **Submission** | 2-3 Min Pitch Video & Slides | 🟢 Polish (P2) | Low | Planned |
| **Competition** | Algorand MainNet Deployment & Challenge Entry | 🟢 Final (P3) | Low | Pending TestNet Sign-off |
