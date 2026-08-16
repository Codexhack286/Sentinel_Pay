# SentinelPay Threat Model

## 1. Core Invariants

### Invariant 1 — No Direct Wallet Authority
The Deep Agent never possesses unrestricted wallet private keys or generic `sign_transaction(...)` capabilities. All payments must route through SentinelPay authorization.

### Invariant 2 — Exact-Action Authorization Binding
An authorization attestation is cryptographically bound to exact economic parameters:
```text
Authorization = {
    version,
    policy_id,
    agent_id,
    intent_hash,
    task_scope_hash,
    tool_id,
    resource_id,
    destination,
    asset,
    amount,
    nonce,
    issued_at,
    expires_at
}
```
An attestation cannot be retroactively repurposed for a different recipient, higher amount, or different asset.

### Invariant 3 — On-Chain Enforcement
A payment without a valid, matching SentinelPay smart contract authorization app call in the same atomic group **must fail settlement**. The security boundary is enforced at the consensus layer, not merely in advisory client code.

### Invariant 4 — Replay Resistance
Every authorization attestation carries a unique nonce, timestamp, and short expiry. Once consumed on-chain, the nonce is recorded in contract box storage/state, preventing any second payment with the same attestation.

### Invariant 5 — Spend-Cap Enforcement
Cumulative daily and per-transaction spend caps are verified deterministically both in middleware and on-chain in smart contract state. Even a compromised verifier cannot authorize expenditures beyond the contract-enforced hard policy ceiling.

### Invariant 6 — Verifier Isolation
The verifier never ingests arbitrary attacker-controlled raw tool outputs or unstructured web page bodies. Only canonical, structured metadata fields are evaluated to prevent prompt injection hijacking.

### Invariant 7 — Destination Restriction
Payments are strictly confined to whitelisted destinations or authorized payment addresses specified by policy.

---

## 2. Threat Matrix & Mitigations

| Threat | Impact | Mitigation |
|---|---|---|
| **Prompt Injection via Tool Output** | Agent tries to purchase unauthorized premium resource or pay external attacker | Normalizer strips raw text; Verifier checks declared task alignment; Policy rejects non-whitelisted destinations / amounts. |
| **Client / Agent Bypass** | Rogue agent submits raw payment transaction directly | Resource server requires SentinelPay atomic group proof; smart contract enforces attestation requirement. |
| **Attestation Replay** | Attacker intercepts signed attestation and replays it | Contract marks nonce as consumed; transactions have strict block/time expiries. |
| **Amount / Destination Tampering** | Attacker modifies amount or recipient in transit | Amount and destination live *inside* the signed 120-byte blob at fixed offsets; the contract reads them from there and compares to `gtxn[0]`. There is no unsigned copy to modify. |
| **Argument Substitution** | Attacker keeps a genuine signature but supplies their own destination/amount alongside it | Fixed. `validate_and_pay` takes only `[selector, blob, signature]`; every enforced field is derived from the authenticated blob. Regression-tested in `contracts/tests/test_reference_model.py`. |
| **Account Close-Out Rider** | Payment matches the authorized amount but also carries `CloseRemainderTo`, draining the rest of the balance | Contract rejects any `CloseRemainderTo` or `RekeyTo` on the payment and on its own app call. |
| **Expired Authorization** | An old attestation is presented long after issuance | Expiry is inside the signed blob and checked on-chain against `Global.LatestTimestamp`; the resource server checks it too. Policy caps how long an intent may declare. |
| **Spend Cap Exhaustion** | Agent rapidly executes multiple payments near budget | Smart contract atomically updates cumulative spend counter; rejects group if limit exceeded. |
| **Verifier Key Compromise** | Malicious actor signs unauthorized attestations | Private key in env only, never logged or committed; separate TestNet/MainNet keys; the on-chain spend cap bounds the damage. Rotation requires deploying a new app — the contract rejects `UpdateApplication`, so a compromised *admin* key cannot swap in an attacker's verifier identity. |
| **Verifier Key Divergence** | Different processes sign and validate with different keys, so either nothing validates or checks are skipped | One configured identity loaded through `sentinelpay/keys.py`; on-chain paths refuse to run without it rather than falling back to an ephemeral key. |
| **Signature Replayed at the HTTP Layer** | A signed attestation is presented to the resource server without the payment ever being broadcast | The server requires the contract's nonce box to exist before serving. The box is written only by a successful `validate_and_pay`, so it transitively proves a matching payment settled. See `sentinelpay/payments/settlement.py`. |
| **Chain Unreachable During Verification** | An attacker induces or waits for an algod outage and redeems an unsettled authorization | Fail closed. `ChainUnavailable` is never collapsed into "not settled"; the resource is withheld and the request returns 402. |
| **Off-Task but Plausible Purchase** | Agent is steered to something within every hard limit that shares vocabulary with the real task | Two independent layers: a deterministic `blocked_actions` denylist for open-ended commitments (subscriptions, transfers, withdrawals), and a task-scope overlap check requiring at least two shared terms with the user's objective. |
| **Admin Key Compromise** | Attacker resets the on-chain spend counter to widen throughput | `admin_reset_spend` can only zero the counter. It cannot raise the cap, retire a consumed nonce, or change the verifier key, and `UpdateApplication` is rejected outright. Verified on TestNet: a non-admin call fails at `pc=142`. |
