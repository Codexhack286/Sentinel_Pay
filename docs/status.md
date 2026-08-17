# SentinelPay — Status, Pending Tasks & Roadmap

**Current Version**: `0.4.0`
**Last Updated**: August 17, 2026 — audit fixes (concurrency, tracing wiring, planner validation, contract lockstep)
**Repository**: [https://github.com/Codexhack286/Sentinel_Pay](https://github.com/Codexhack286/Sentinel_Pay)

---

## 1. Executive Summary

SentinelPay is an authorization and policy-enforcement layer for autonomous
AI-agent payments in x402 ecosystems. Every agent-initiated payment must pass
deterministic policy checks and verifier attestation, and the resulting signed
authorization must be accepted by an Algorand contract in the same atomic group
as the payment.

**Current state**: engine, agent runtime, contract (both the deployable PyTeal
program and the reference model), services, adversarial test matrix and demo
flows are implemented and green — **172/172 tests passing**, all offline.

A security review found the previously deployed contract did not bind the
enforced fields to the signed attestation. **Fixed, redeployed, and verified
live** — app `769368669`. Every attack class is now rejected by the contract
itself, at a named opcode. See section 2.

---

## 2. Security Fix — Authorization Binding (resolved and verified on-chain)

### What was wrong

`validate_and_pay` took six application arguments:

```
args[0] selector   args[1] signed blob   args[2] signature
args[3] destination   args[4] amount   args[5] nonce
```

It verified the Ed25519 signature over `args[1]`, then compared `args[3]` and
`args[4]` against `gtxn[0]`. Nothing tied `args[3..5]` to `args[1]`. An attacker
holding any single genuine attestation could therefore submit:

- `args[1..2]` — the real, correctly signed authorization (signature passes)
- `args[3]` — their own address
- `args[4]` — any amount up to the spend cap
- `args[5]` — a fresh nonce, so the replay check passes too

and every remaining assert compared attacker input against attacker input. One
0.1 ALGO authorization was effectively a bearer token for the entire spend cap.
The contract also never checked expiry, `CloseRemainderTo` or `RekeyTo`.

### The fix

The contract now takes **three** arguments and reads destination, amount, nonce
and expiry out of the signed bytes themselves, at fixed offsets in a 120-byte
blob (`Attestation.avm_signing_bytes()`, layout in `docs/protocol.md` §3.2).
There is no unsigned field left to substitute. Added alongside it: blob length
and magic checks, signature length check, expiry check against
`Global.LatestTimestamp`, and rejection of `CloseRemainderTo` / `RekeyTo` on both
the payment and the app call.

`contracts/tests/test_reference_model.py` pins every one of those attacks, and
`scripts/verify_attack.py --broadcast` demonstrates the same rejections against
live TestNet.

### Verified on TestNet

- [x] Recompiled and redeployed — app **`769368669`**, budget helper **`769368677`**
- [x] App account funded for nonce-box MBR (0.3 ALGO)
- [x] Legitimate settlement confirmed — [`7KRNWCNN...`](https://testnet.explorer.perawallet.app/tx/7KRNWCNNGUOZKEPOVZD3H4GYQWBOF6WGSN45XUZESB74OOKFDJRA), round 66376855
- [x] `verify_attack.py --broadcast` — all 5 attack classes rejected **by the
      contract**, each at a named opcode:

  | Attack | Rejection |
  |---|---|
  | Amount substitution | `pc=263  load 0; ==; assert` |
  | Destination substitution | `pc=256  extract 8 32; ==; assert` |
  | Blob tampering | `pc=229  ed25519verify_bare; assert` |
  | Forged signature | `pc=229  ed25519verify_bare; assert` |
  | Replay after settlement | `pc=287  box_create; assert` |

- [x] On-chain state confirmed: `spend_today` tracked correctly across two
      settlements, two consumed nonce boxes present, `verifier_pk` matching `.env`
- [x] `admin_reset_spend` exercised on-chain (200000 → 0)
- [x] Admin **rejection** proven on-chain too: a non-admin call fails at
      `pc=142  app_global_get; ==; assert`. The rogue account needs no funding —
      Algorand's pooled fees let the agent pay for its zero-fee call, so the
      group reaches the contract instead of dying on an empty balance
- [x] Full x402 loop verified by `scripts/live_roundtrip.py`: the identical
      request returns 402 before the broadcast and 200 after it

The verification script now distinguishes a contract rejection from an unrelated
one. An early run "passed" only because the inflated amount exceeded the account
balance, so two groups never reached the contract at all — those are now reported
as INCONCLUSIVE with a non-zero exit rather than counted as a defence.

Apps `769239295` / `769240052` are the vulnerable revision and must not be reused.

---

## 3. Other fixes in this pass

| Area | Problem | Fix |
|---|---|---|
| Verifier identity | Every process minted its own ephemeral Ed25519 key; the resource server could never validate an attestation the verifier service signed, and restarts invalidated outstanding attestations. `VERIFIER_PRIVATE_KEY` was read by exactly one script. | `sentinelpay/keys.py` loads one configured identity everywhere; `scripts/gen_verifier_key.py` generates it; on-chain paths fail closed without it. |
| x402 proof check | `verify_settlement_proof` never checked `expires_at` or `decision`, so an expired or explicitly denied attestation was accepted forever. A rejected proof also consumed the nonce, locking out the valid retry. | Expiry, decision and clock-skew checks added; the nonce is consumed only after every check passes. |
| Semantic verifier | Category matching read `tool_name` and `resource_id` as well as the goal, so a tool named `paid_research` satisfied the `research` category regardless of what was being bought — the check was vacuous. | Categories match the declared goal only. Added task-scope alignment: the goal must overlap the user's original objective, which is passed through the harness rather than restated by the agent. |
| Spend tracking | `daily_spend_limit` was enforced against a counter that never decayed, so it was a lifetime limit. | Timestamped rolling window, configurable via `spend_window_seconds`. |
| Intent validation | Amount had no lower bound; a negative amount passed the cap check and *reduced* recorded spend. Expiry was derived from a second `time.time()` call, so the lifetime check was flaky across a second boundary. | `amount > 0` enforced on both models; expiry derived from `timestamp`; intent lifetime capped by policy. |
| 402 parsing | `parse_402_response` read `WWW-Authenticate` and then discarded it, so a header-only server looked like a server with no requirements. | Header is parsed. |
| Module shadowing | `contracts/sentinelpay.py` shadowed the `sentinelpay` package whenever `contracts/` was on `sys.path`, breaking `python contracts/compile.py`. | Renamed to `contracts/reference_model.py`. |
| Scripts | Four copies of `get_algod_client` and an unbounded confirmation loop that spun forever if a transaction never landed. | Shared `scripts/_chain.py` with a bounded wait; group construction centralized in `sentinelpay/payments/algorand.py`. |
| Contract lifecycle | The spend counter had no reset, so the app bricked itself once cumulative spend reached the cap. | `admin_reset_spend`, creator-only. Cannot raise the cap, retire a nonce, or change the verifier key. |
| Packaging | `pyproject.toml` declared dev dependencies twice with different pins; uv and pip resolved different ones. | Single `[dependency-groups] dev`. |
| Resource server | Served the dataset on a valid signature alone. A signature proves an authorization was *issued*, not that money moved, so a replayed attestation unlocked the resource without any broadcast. | Acceptance now requires the contract's nonce box to exist on-chain; an unreachable chain fails closed. `sentinelpay/payments/settlement.py`. |
| Off-task purchases | The task-alignment threshold required a single shared word, so "premium energy trading subscription" counted as aligned with an energy research task on the word "energy". | Threshold raised with a two-term floor, plus a deterministic `blocked_actions` denylist (specification section 7) that was never implemented. |
| Staged attack | `simulate_attack=True` selected a hardcoded attacker address and amount from an if/else, so the injection demo proved nothing about the agent. | `agent/planner.py` parses the payment out of the malicious tool output; the attacker's numbers now come from the text. |
| Test isolation | Tests hardcoded the placeholder payee, so they passed only on machines with no `.env`. | Tests read the payee and price off the server's own 402 challenge. |

---

## 4. Completed

### Core engine (`sentinelpay/`)
- [x] Intent normalization, bounded fields, deterministic SHA-256 intent hashing
- [x] Deterministic policy engine: per-transaction cap, rolling cumulative cap,
      tool/destination/currency allowlists, expiry and lifetime bounds
- [x] Ed25519 attestation signing over two encodings — canonical JSON for the
      HTTP verifier, fixed-layout binary for the contract
- [x] Local semantic verifier: injection indicators, category alignment,
      task-scope alignment
- [x] Gateway middleware orchestrating the full decision
- [x] x402 challenge parsing and settlement-proof verification
- [x] Protected atomic group construction (`payments/algorand.py`)

### Agent (`agent/`)
- [x] Deterministic Deep Agent harness with no wallet-signing privileges
- [x] Free vs SentinelPay-gated tool boundary
- [x] Skills and subagent specs
- [x] Single-node LangGraph wrap (`agent/graph.py` + `langgraph.json`) exposing
      `DeepAgent` to LangSmith Deployments without rewriting the harness

### Contracts & scripts
- [x] Deployable AVM v8 PyTeal program with box-backed replay protection
- [x] Pure-Python reference model kept in lockstep via shared offset constants
- [x] Compilation pipeline; deploy, funding, broadcast and adversarial scripts

### Services
- [x] x402 resource endpoint (402 challenge → proof validation → data)
- [x] Standalone verifier node

### Tests — 172 passing
- [x] Unit: policy, intent, attestation (JSON + AVM), verifier, keys, x402
      handler, gateway, verifier service, facilitator payloads, group builder
- [x] Integration: full x402 payment flow
- [x] Adversarial: prompt injection, verifier bypass, replay, spend cap
- [x] Contract: amount/destination substitution, blob tampering, forged
      signature, expiry, cap, close-out, rekey, replay, admin authorization

---

## 5. Pending

### P0 — Execution
- [x] Redeploy the fixed contract to TestNet (section 2)
- [x] Live atomic broadcast; confirmed transaction IDs captured
- [x] `verify_attack.py --broadcast`; per-opcode rejection evidence captured
- [x] Bind the resource server's acceptance to on-chain settlement. The server
      now requires the contract's nonce box to exist before serving; that box is
      written only by a successful `validate_and_pay`, so it transitively proves
      a matching payment settled. Verified live by `scripts/live_roundtrip.py`.
- [ ] Optional: route settlement through the GoPlausible facilitator's
      `/verify` + `/settle` instead of direct algod broadcast. The client exists
      and is smoke-tested; the box check above already makes acceptance
      chain-derived, so this is now a compatibility nicety rather than a
      security gap.

### P1 — Hardening
- [x] Optional local LLM planning (Ollama) so the agent's decisions can be
      genuinely probabilistic, falling back to rules when unavailable
- [x] Injection scenario is data-driven: the agent parses the attacker's amount
      and address out of the tool output instead of reading them from a branch
- [x] `blocked_actions` denylist from specification section 7
- [ ] Replace keyword-based injection detection with a local embeddings model
      (`all-MiniLM-L6-v2`) for cosine similarity between objective and goal
- [ ] ASA / TestNet USDC support (`axfer` in addition to `pay`)
- [ ] Nonce box pruning to reclaim MBR after expiry

### P2 — Presentation
- [x] Terminal or web visualizer: prompt → reasoning → firewall decision →
      atomic group → explorer link, Scene A beside Scene B
- [ ] 2–3 minute demo video and slides

### P3 — Competition
- [ ] MainNet deployment with a segregated key set
- [ ] One real MainNet micropayment through the GoPlausible facilitator

---

## 6. Priority matrix

| Area | Item | Priority | Complexity | Status |
|---|---|---|---|---|
| Security | Authorization binding in the contract | 🔴 P0 | High | ✅ Fixed and verified on TestNet |
| Execution | Redeploy + live broadcast + attack proof | 🔴 P0 | Low | ✅ Done |
| Execution | On-chain acceptance at the resource server | 🔴 P0 | Medium | ✅ Done, verified live |
| Execution | Facilitator `/verify` + `/settle` path | 🟡 P1 | Medium | Optional; box check already binds acceptance |
| Security | Embeddings-based verifier | 🟡 P1 | Low | Not started |
| AI Agent | Local LLM dynamic tool calling | 🟡 P1 | Medium | ✅ Optional Ollama planner |
| Deployment | LangGraph wrap for LangSmith | 🟡 P1 | Low | ✅ Done |
| Contract | ASA/USDC support, nonce pruning | 🟡 P1 | Medium | Not started |
| Presentation | Demo visualizer, video, slides | 🟢 P2 | Medium | ✅ Done |
| Competition | MainNet deployment and entry | 🟢 P3 | Low | Pending TestNet sign-off |
