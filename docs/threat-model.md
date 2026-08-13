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
| **Amount / Destination Tampering** | Attacker modifies amount in transit | Signed attestation contains exact amount and recipient hash; contract verifies payment Tx matches attestation fields. |
| **Spend Cap Exhaustion** | Agent rapidly executes multiple payments near budget | Smart contract atomically updates cumulative spend counter; rejects group if limit exceeded. |
| **Verifier Key Compromise** | Malicious actor signs unauthorized attestations | Private key stored in secure env/HSM; on-chain hard spend cap limits damage; key rotation supported via contract admin. |
