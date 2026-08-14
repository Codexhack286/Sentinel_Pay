# SentinelPay Project Status & Roadmap

**Current Version**: `0.3.0-beta`
**Last Updated**: August 14, 2026 — Live TestNet Deployment ✅
**Repository**: [https://github.com/Codexhack286/Sentinel_Pay](https://github.com/Codexhack286/Sentinel_Pay)

---

## 1. Executive Summary

SentinelPay is an authorization and policy-enforcement layer for autonomous AI-agent payments in x402 ecosystems. It prevents prompt-injection hijacking, runaway spending, and unauthorized transfers by ensuring that all agent-initiated payments must pass deterministic policy checks and verifier attestation before being executed in an Algorand smart contract atomic group.

**Current State**: Full local architecture, agent runtime, security engine, reference contract logic, **real deployable PyTeal contract**, attack testing matrix, and demo flows are **100% operational and verified (61/61 tests passing)**. The **SentinelPay smart contract is now live on Algorand TestNet** (App ID: `769239295`) with the verifier public key and admin address baked into on-chain global state. Services confirmed running and responding to live HTTP requests.

**Resolved risk**: the facilitator single-point-of-failure/compatibility question flagged in `SentinelPay_Project_Review.docx` Section 5 — whether GoPlausible's facilitator supports atomic transaction groups beyond the bare payment leg — is **confirmed yes**. GoPlausible's own docs describe `paymentGroup` as explicitly extensible for "integrating with other smart contracts on Algorand," and `verify()` only enforces required fields on the transaction at `paymentIndex`, not on the rest of the group. SentinelPay's `[payment, app-call]` shape fits their model as-is. See `sentinelpay/payments/facilitator.py` docstring for the full citation trail.

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
- [x] **Real PyTeal Contract** (`contracts/pyteal_contract.py`): Deployable AVM v8 program (not just a TEAL string scaffold) — same 6 invariants as the reference model, with **Box storage** for on-chain nonce replay protection. Compiles cleanly via PyTeal 0.27.
- [x] **Compilation Pipeline** (`contracts/compile.py`): `uv run python contracts/compile.py` → writes `contracts/build/approval.teal` and `clear.teal`.
- [x] **Contract Unit Tests**: `contracts/tests/test_sentinelpay.py` (reference-model invariants) + `contracts/tests/test_pyteal_contract.py` (real compilation output).

### Services & API (`services/`)
- [x] **x402 Resource Endpoint** (`services/api/app.py`): FastAPI server returning HTTP 402 challenge and serving protected dataset upon receiving valid SentinelPay settlement proof.
- [x] **Standalone Verifier Node** (`services/verifier/app.py`): REST endpoint for policy evaluation and attestation signing.

### Adversarial & Test Suite (`tests/`, `contracts/tests/`) — 61/61 Tests Passing
- [x] `tests/unit/test_policy.py`: Deterministic cap, allowlist, and expiry checks.
- [x] `tests/unit/test_intent.py`: Intent normalization and deterministic hash reproducibility.
- [x] `tests/unit/test_attestation.py`: Ed25519 signature generation and tamper detection.
- [x] `tests/unit/test_verifier.py` **(new)**: `LocalSemanticVerifier` in isolation — empty-goal, adversarial-indicator, and category-alignment checks; also documents a real substring-matching quirk where a tool named e.g. `paid_research` auto-satisfies the "research" category regardless of the declared goal.
- [x] `tests/unit/test_x402_handler.py` **(new)**: `X402PaymentHandler` — 402 parsing, settlement-proof construction, and every rejection branch of `verify_settlement_proof` (bad scheme, replay, destination/amount/currency mismatch, bad signature, malformed base64).
- [x] `tests/unit/test_gateway.py` **(new)**: `SentinelPayGateway` — policy-denial short-circuit, verifier-denial passthrough, spend tracking only on the authorized path.
- [x] `tests/unit/test_verifier_service.py` **(new)**: standalone verifier REST node (`services/verifier/app.py`) — had zero coverage before.
- [x] `tests/unit/test_facilitator.py`: GoPlausible request/payload shaping against their documented V2 schema (no live network calls).
- [x] `tests/integration/test_payment_flow.py`: Full 402 challenge -> payment intent -> attestation -> settlement -> 200 data delivery.
- [x] `tests/attacks/test_prompt_injection.py` (Attack A): Injected tool command rejected; zero funds moved.
- [x] `tests/attacks/test_verifier_bypass.py` (Attack B): Bare payment attempts rejected by endpoint and contract.
- [x] `tests/attacks/test_replay.py` (Attack C): Reused nonces rejected immediately.
- [x] `tests/attacks/test_spend_cap.py` (Attack D): Rapid payments exceeding daily limits blocked.
- [x] `contracts/tests/test_pyteal_contract.py`: Real PyTeal contract compiles and encodes all 6 invariants (group size, signature check, box-storage replay guard, selector check).

**Still without dedicated tests**: `agent/agent.py` and `agent/tools/` (only exercised indirectly through the attack tests' `simulate_attack` path — no direct unit tests of the DeepAgent harness itself), and `scripts/deploy_testnet.py` / `scripts/fund_testnet.py` (network-dependent scripts, not meaningfully unit-testable without a live or mocked algod).

### Facilitator Integration (`sentinelpay/payments/facilitator.py`)
- [x] **GoPlausible HTTP client**: thin async wrapper around `POST /verify` and `POST /settle` on the public reference facilitator (`https://facilitator.goplausible.xyz`), plus `/health` and `/supported`.
- [x] **Composability risk resolved** (was "Medium" severity, open question in the review doc): confirmed via GoPlausible's protocol docs that atomic groups with an app-call transaction alongside the payment are supported by design — no workaround needed.

### Runnable Demos (`examples/`, `scripts/`)
- [x] `examples/legitimate_flow.py`: Complete console walkthrough of Scenario A.
- [x] `examples/prompt_injection_flow.py`: Complete console walkthrough of Scenario B.
- [x] `scripts/run_demo.py` & `scripts/dev.py`: Interactive runners and development server.

---

## 3. Pending Tasks & Next Steps 📋

```text
Local Architecture (Done) ──► Compiled Contract + Facilitator Client (Done) ──► Live TestNet Run ──► MainNet & Polish
```

### High Priority: Live TestNet Smart Contract Deployment ✅ COMPLETE
- [x] **PyTeal Compilation**: `contracts/pyteal_contract.py` + `contracts/compile.py` — done, compiles locally, tested.
- [x] **Deploy script written**: `scripts/deploy_testnet.py` — reviewed and smoke-tested against live node.
- [x] **TestNet Account Funding**: `scripts/fund_testnet.py` run, account funded via Algorand TestNet dispenser. Mnemonics in `.env`.
- [x] **Contract Deployment**: `scripts/deploy_testnet.py` executed successfully.
  - **App ID: `769239295`** (live on Algorand TestNet)
  - Explorer: https://testnet.explorer.perawallet.app/application/769239295
  - Confirmed global state: `verifier_pk`, `admin`, `max_daily_spend=1,000,000 uALGO`, `spend_today=0`
- [x] **Services confirmed live**: API server (`:8000`) returning HTTP 402 challenges; Verifier node (`:8001`) signing attestations.

### Medium Priority: Live x402 Facilitator Integration
- [x] **GoPlausible client written**: `sentinelpay/payments/facilitator.py` — `verify()`/`settle()` wired to the real documented schema, unit-tested for payload shape.
- [x] **Composability risk resolved**: confirmed the facilitator supports SentinelPay's `[payment, app-call]` group shape (see Section 1 and the module docstring).
- [ ] **Live verify()/settle() smoke test**: run one real call against `https://facilitator.goplausible.xyz/health` and `/supported` to confirm current uptime and Algorand TestNet listing before relying on it for the demo.
- [ ] **Real Atomic Group Broadcast**: Fund agent wallet, send a live `[payment, app-call]` group through the contract (`SENTINELPAY_APP_ID=769239295`) and capture transaction/group IDs.
- [ ] **Box MBR funding**: Fund the app account's minimum balance requirement for nonce Box storage before first `validate_and_pay` call (see `docs/protocol.md`).

### Verification & Demonstration Polish
- [ ] **On-Chain Demo Run**: Execute end-to-end payment flow against live TestNet — capture Pera Explorer tx links showing the atomic `[payment + app-call]` group.
- [ ] **Demo Recording / Walkthrough**: Record terminal/web walkthrough showcasing legitimate payment confirmation vs. prompt-injection block.

### Final Submission / MainNet Promotion (Optional / Challenge Scope)
- [ ] **MainNet Deployment**: Deploy smart contract to Algorand MainNet.
- [ ] **MainNet x402 Proof**: Execute at least one verified micropayment transaction for official hackathon leaderboard qualification.
