# SentinelPay Protocol Specification

## 1. Intent Model & Normalization

When an agent requests a payment to access a resource, the raw request is normalized into a `CanonicalIntent`:

```json
{
  "version": "1.0",
  "policy_id": "policy-research-v1",
  "agent_id": "deep-agent-researcher-01",
  "declared_goal": "Retrieve market statistics for solar energy",
  "tool_name": "paid_market_research",
  "resource_id": "market-stat-api.testnet",
  "destination": "ALGORAND_RECEIVER_ADDRESS",
  "amount": 100000,
  "currency": "uALGO",
  "timestamp": 1773489000,
  "expiry": 1773489300
}
```

The SHA-256 hash of the canonical JSON representation produces the `intent_hash`:
$$\text{intent\_hash} = \text{SHA-256}(\text{CanonicalIntent})$$

## 2. Attestation Object

Upon successful policy evaluation and verifier review, SentinelPay generates an `Attestation`:

```json
{
  "attestation_id": "attest-8f14b2d3...",
  "intent_hash": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
  "task_scope_hash": "9f2c...",
  "agent_id": "deep-agent-researcher-01",
  "policy_id": "policy-research-v1",
  "tool_name": "paid_market_research",
  "destination": "ALGORAND_RECEIVER_ADDRESS",
  "amount": 100000,
  "currency": "uALGO",
  "nonce": "nonce-4a92...",
  "issued_at": 1773489000,
  "expires_at": 1773489300,
  "decision": "ALLOW",
  "verifier_id": "sentinelpay-verifier-node-1",
  "signature": "base64_ed25519_signature_over_canonical_json",
  "avm_signature": "base64_ed25519_signature_over_the_120_byte_blob"
}
```

There are two signatures because there are two verifiers with different parsing
abilities, not because one is a fallback for the other:

- `signature` covers the canonical JSON above and is what the x402 resource
  server checks.
- `avm_signature` covers the fixed-layout binary blob in section 3.2 and is what
  the Algorand contract checks. TEAL cannot parse JSON, and a JSON encoding has
  no fixed offsets to `extract` from.

An attestation whose destination is not a real Algorand address gets no
`avm_signature` at all — offline demo attestations are structurally unable to
settle, which is the correct default.

`task_scope_hash` binds the authorization to the user-authorized task, so an
attestation issued for one task cannot be reused to justify another.

## 3. Algorand Atomic Group Structure

The atomic group submitted to Algorand contains:

1. **Transaction 0 (Payment)**:
   - Type: `pay` (or `axfer` for ASA/USDC)
   - Sender: Agent Wallet / Escrow
   - Receiver: Resource Owner Address
   - Amount: `amount` matching Attestation

2. **Transaction 1 (SentinelPay Application Call)**:
   - Type: `appl`
   - Application ID: `SENTINELPAY_APP_ID`
   - OnComplete: `NoOp`
   - App Args — exactly three (matches `contracts/pyteal_contract.py`):
     - `args[0]`: `validate_and_pay`
     - `args[1]`: the signed authorization blob (exactly 120 bytes, layout below)
     - `args[2]`: 64-byte Ed25519 signature over `args[1]`
   - Box reference: the 32-byte nonce extracted from `args[1]`.

3. **Transactions 2..n (optional)**: NoOp calls to the budget helper app. Each
   contributes 700 opcode units to the group's shared pool, which is how the
   1900-unit `ed25519verify_bare` fits. They carry no logic.

### 3.1 Why only three arguments

Destination, amount and nonce are **not** separate arguments. An earlier
revision passed them alongside the signed blob without binding them to it, so a
single genuine attestation could be resubmitted with an attacker's destination,
an attacker's amount and a fresh nonce — the signature check still passed, and
every other assert compared attacker input against attacker input.

The contract now reads every enforced field out of the signed bytes at fixed
offsets. There is nothing left for a caller to substitute.

### 3.2 Signed blob layout

Produced by `Attestation.avm_signing_bytes()`; parsed by the contract with
`extract` and by `contracts/reference_model.py::parse_avm_blob`.

| offset | length | field |
|---|---|---|
| 0 | 8 | magic `SPAYv1\x00\x00` |
| 8 | 32 | destination — raw Algorand public key |
| 40 | 8 | amount — big-endian uint64, micro-units |
| 48 | 32 | nonce — box key for replay protection |
| 80 | 8 | expires_at — big-endian uint64, unix seconds |
| 88 | 32 | intent_hash — binds the authorization to the canonical intent |
| | **120** | total |

### 3.3 Contract invariants, in execution order

1. `len(args[1]) == 120` and the magic prefix matches; `len(args[2]) == 64`.
2. `GroupSize >= 2` and `gtxn[0]` is a payment.
3. `gtxn[0]` has no `CloseRemainderTo` and no `RekeyTo`; nor does the app call.
   Without this an authorized 0.1 ALGO payment could also close the sender's
   whole balance out to the attacker.
4. `ed25519verify_bare(args[1], args[2], verifier_pk)`.
5. `gtxn[0].Receiver == blob.destination`.
6. `gtxn[0].Amount == blob.amount`.
7. `Global.LatestTimestamp < blob.expires_at`.
8. `spend_today + amount <= max_daily_spend`.
9. `box_create(blob.nonce)` returns true — a false return means this
   authorization was already consumed.
10. `spend_today += amount`.

Any failure aborts the transaction, and because the group is atomic the payment
does not settle either.

### 3.4 Admin operation

`admin_reset_spend` zeroes the cumulative counter and is callable only by the
creator address stored at deploy time. It stands in for the daily rollover the
AVM cannot schedule. It cannot raise the cap, retire a consumed nonce, or change
the verifier key — so a compromised admin key cannot forge an authorization.
The contract also rejects `UpdateApplication` and `DeleteApplication`, which
means rotating the verifier key requires deploying a new app.

## 4. Facilitator Compatibility

The group above is submitted through the GoPlausible x402-avm facilitator
(`https://facilitator.goplausible.xyz`, see `sentinelpay/payments/facilitator.py`).
The facilitator's `paymentGroup` format is explicitly documented as supporting
additional transactions beyond the payment leg (their docs cite "integrating
with other smart contracts on Algorand" by name), and `verify()`/`settle()`
only require specific fields on the transaction at `paymentIndex` — so the
SentinelPay app call at index 1 rides along in the same group without any
facilitator-side changes needed.

## 5. Resource-Server Acceptance Criterion

A signature proves an authorization was *issued*. It does not prove a payment
*settled* — a compromised client can present a validly signed attestation at the
HTTP layer without ever broadcasting anything. So the resource server checks two
independent things before serving:

1. **The authorization**: signature verifies against the configured verifier key,
   `decision == "ALLOW"`, not expired, not issued in the future, and the
   destination, amount and asset match exactly what this resource charges.

2. **The settlement**: the SentinelPay contract holds a box under this
   attestation's 32-byte nonce.

Step 2 is the load-bearing one, and it works because of an equivalence the
contract itself establishes:

```
nonce box exists  <=>  validate_and_pay ran and approved
                  =>   a payment matching the signed destination, amount and
                       expiry settled atomically alongside it
```

So one box lookup transitively proves the whole payment. No indexer, no group
reconstruction, one algod call.

A **bare payment fails here by construction**: with no application call in the
group, no box is ever written, so there is nothing for the server to find.

### Failure modes

| Situation | Response |
|---|---|
| Box present | 200, resource served |
| Box absent | 402 — payment not settled |
| algod unreachable | 402 — fail closed; an outage must not become an open door |
| `SENTINELPAY_APP_ID` unset | Offline demo mode: check skipped, and `enforces_onchain_settlement: false` is reported on `/` and `settlement_verified: false` in the response body, so it is never mistaken for enforcement |

### What the box does not prove

The box says "consumed once, ever" — it cannot distinguish the first redemption
from a later one. Serving the content once per authorization is a separate
concern, handled by the server's own `consumed_nonces` set. That set is
process-local and resets on restart, which is acceptable precisely because it
can only ever *withhold* the resource, never authorize a payment. The money side
is authoritative on-chain.

A failed settlement check releases the nonce back into the serve-once set, so a
genuine retry after the group confirms is not locked out by an early attempt.
