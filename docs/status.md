# SentinelPay Project Status & Roadmap

**Current Version**: `0.1.0-alpha`  
**Last Updated**: August 14, 2026  
**Repository**: [https://github.com/Codexhack286/Sentinel_Pay](https://github.com/Codexhack286/Sentinel_Pay)

---

## 1. Executive Summary

SentinelPay is an authorization and policy-enforcement layer for autonomous AI-agent payments in x402 ecosystems. It prevents prompt-injection hijacking, runaway spending, and unauthorized transfers by ensuring that all agent-initiated payments must pass deterministic policy checks and verifier attestation before being executed in an Algorand smart contract atomic group.

**Current State**: Full local architecture, agent runtime, security engine, reference contract, attack testing matrix, and demo flows are **100% operational and verified (17/17 tests passing)**.

---

## 2. Completed Milestones ✅

### Phase 0: Repository Scaffolding & Tooling
- [x] Initialized uv-managed Python environment (`pyproject.toml`, `uv.lock`).
- [x] Configured zero-paid dependency baseline (`pydantic`, `fastapi`, `cryptography`, `py-algorand-sdk`, `pytest`).
- [x] Implemented environment security isolation (`.gitignore`, `.env.example`).
- [x] Set up Git version control and pushed initial baseline to GitHub.

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

### Reference Smart Contract & Logic (`contracts/`)
- [x] **AVM Validation Logic** (`contracts/sentinelpay.py`): Implemented reference logic for atomic group validation, Ed25519 signature checks, nonce consumption (replay defense), and spend cap tracking.
- [x] **PyTeal / TEAL Assembly Scaffold**: Contract approval program specification.
- [x] **Contract Unit Tests** (`contracts/tests/test_sentinelpay.py`): Validated atomic group invariants, replay prevention, and destination tampering detection.

### Services & API (`services/`)
- [x] **x402 Resource Endpoint** (`services/api/app.py`): FastAPI server returning HTTP 402 challenge and serving protected dataset upon receiving valid SentinelPay settlement proof.
- [x] **Standalone Verifier Node** (`services/verifier/app.py`): REST endpoint for policy evaluation and attestation signing.

### Adversarial & Test Suite (`tests/`) — 17/17 Tests Passing
- [x] `tests/unit/test_policy.py`: Deterministic cap, allowlist, and expiry checks.
- [x] `tests/unit/test_intent.py`: Intent normalization and deterministic hash reproducibility.
- [x] `tests/unit/test_attestation.py`: Ed25519 signature generation and tamper detection.
- [x] `tests/integration/test_payment_flow.py`: Full 402 challenge -> payment intent -> attestation -> settlement -> 200 data delivery.
- [x] `tests/attacks/test_prompt_injection.py` (Attack A): Injected tool command rejected; zero funds moved.
- [x] `tests/attacks/test_verifier_bypass.py` (Attack B): Bare payment attempts rejected by endpoint and contract.
- [x] `tests/attacks/test_replay.py` (Attack C): Reused nonces rejected immediately.
- [x] `tests/attacks/test_spend_cap.py` (Attack D): Rapid payments exceeding daily limits blocked.

### Runnable Demos (`examples/`, `scripts/`)
- [x] `examples/legitimate_flow.py`: Complete console walkthrough of Scenario A.
- [x] `examples/prompt_injection_flow.py`: Complete console walkthrough of Scenario B.
- [x] `scripts/run_demo.py` & `scripts/dev.py`: Interactive runners and development server.

---

## 3. Pending Tasks & Next Steps 📋

```text
Local Architecture (Done) ──► TestNet Deployment ──► x402 Facilitator ──► MainNet & Polish
```

### High Priority: TestNet Smart Contract Deployment
- [ ] **PyTeal / Beaker Compilation**: Finalize compilation pipeline to generate bytecode/artifacts using AlgoKit.
- [ ] **TestNet Account Funding**: Generate and fund Agent and Verifier TestNet accounts via dispenser (`scripts/fund_testnet.py`).
- [ ] **Contract Deployment**: Deploy the SentinelPay application to Algorand TestNet and populate `SENTINELPAY_APP_ID` in `.env`.

### Medium Priority: Live x402 Facilitator Integration
- [ ] **GoPlausible Integration**: Connect payment submission with the public GoPlausible x402 TestNet facilitator.
- [ ] **Real Atomic Group Broadcast**: Send live transactions to Algorand TestNet and capture transaction IDs and group IDs.

### Verification & Demonstration Polish
- [ ] **On-Chain Demo Run**: Execute the legitimate and prompt-injection demo scripts against live Algorand TestNet nodes and capture block explorer links (Pera Explorer / AlgoExplorer).
- [ ] **Demo Recording / Walkthrough**: Record terminal/web walkthrough showcasing the difference between on-chain confirmation and injection block.

### Final Submission / MainNet Promotion (Optional / Challenge Scope)
- [ ] **MainNet Deployment**: Deploy smart contract to Algorand MainNet.
- [ ] **MainNet x402 Proof**: Execute at least one verified micropayment transaction for official hackathon leaderboard qualification.
