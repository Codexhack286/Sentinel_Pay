# SentinelPay Smart Contracts

## Overview

The SentinelPay contract is an Algorand Virtual Machine (AVM) application
deployed to TestNet/MainNet. It is the **hard enforcement boundary** for agent
payments: everything upstream of it — policy engine, verifier, agent harness —
can be wrong, compromised, or bypassed, and an unauthorized payment still fails
to settle.

## What it enforces

Executed as part of an atomic group whose first transaction is the payment:

1. **Blob framing** — the signed authorization is exactly 120 bytes with the
   expected magic prefix, and the signature is 64 bytes.
2. **Group shape** — at least `[payment, this app call]`, `gtxn[0]` is a payment,
   and neither the payment nor the app call carries a `CloseRemainderTo` or a
   `RekeyTo`.
3. **Signature** — `ed25519verify_bare` over the whole blob against the
   `verifier_pk` registered at creation.
4. **Exact field matching** — the destination and amount are read *out of the
   signed blob* and compared to `gtxn[0].Receiver` and `gtxn[0].Amount`.
5. **Expiry** — `Global.LatestTimestamp` is before the signed `expires_at`.
6. **Spend cap** — cumulative `spend_today + amount <= max_daily_spend`.
7. **Replay protection** — the 32-byte nonce from the blob is written to box
   storage; a box that already exists means the authorization was consumed.

Full argument layout and invariant ordering: [`docs/protocol.md`](../docs/protocol.md).

### Why every field comes from the signed blob

An earlier revision took destination, amount and nonce as separate application
arguments and only checked the signature over an unrelated blob. Nothing bound
the two, so one genuine attestation could be replayed with an attacker's
destination, an attacker's amount and a fresh nonce: the signature check passed
and every other assert compared attacker input against attacker input. A single
0.1 ALGO authorization was effectively a bearer token for the whole spend cap.

Reading the enforced fields from the signed bytes at fixed offsets removes the
substitution surface entirely. `contracts/tests/test_reference_model.py` pins
each of those attacks as a test.

## Two implementations, same invariants

- `contracts/reference_model.py` — pure-Python **reference model**
  (`SentinelPayContractLogic`). Runs in milliseconds with no node, and is
  readable without knowing TEAL. Named `reference_model` rather than
  `sentinelpay` because the latter shadowed the top-level `sentinelpay` package
  whenever `contracts/` landed on `sys.path`.
- `contracts/pyteal_contract.py` — the **real, deployable** AVM v8 program.

Both import their offsets from `sentinelpay/verifier/attestation.py`, so the
signer and both validators cannot drift apart silently.

## Opcode budget

`ed25519verify_bare` costs 1900 units against a 700-unit default per app call.
Budget is pooled across every application call in a group, so the client appends
two NoOp calls to a trivial always-approve helper app (deployed by
`scripts/deploy_budget_app.py`), lifting the pool to 2100. The helper holds no
state and approves unconditionally, so it cannot weaken any check above.

## Box storage costs

Each consumed nonce is a 32-byte key with a 1-byte value: 0.0157 ALGO of minimum
balance, permanently, since the current contract never deletes boxes. Fund the
app account with `scripts/fund_app_mbr.py` before the first `validate_and_pay`.

## Testing & deployment

```bash
uv run pytest contracts/tests            # reference model + TEAL compilation
uv run python contracts/compile.py       # -> contracts/build/{approval,clear}.teal
uv run python scripts/gen_verifier_key.py
uv run python scripts/fund_testnet.py
uv run python scripts/deploy_testnet.py --max-daily-spend 1000000
uv run python scripts/deploy_budget_app.py
uv run python scripts/fund_app_mbr.py
uv run python scripts/live_broadcast.py  # legitimate settlement
uv run python scripts/verify_attack.py --broadcast   # proves attacks do not settle
```
