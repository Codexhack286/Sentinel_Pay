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
  "signature": "base64_ed25519_signature"
}
```

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
   - App Args (matches `contracts/pyteal_contract.py` exactly):
     - `args[0]`: `validate_and_pay`
     - `args[1]`: Attestation `signing_bytes` (canonical JSON payload that was signed)
     - `args[2]`: Ed25519 signature
     - `args[3]`: Destination address (must equal `Tx[0].Receiver`)
     - `args[4]`: Amount, 8-byte big-endian uint64 (must equal `Tx[0].Amount`)
     - `args[5]`: Nonce (Box storage key for replay protection)
   - Logic checks:
     - Verify Ed25519 signature of `args[1]` with stored Verifier Public Key.
     - Verify `Tx[0].receiver == Attestation.destination`.
     - Verify `Tx[0].amount == Attestation.amount`.
     - Verify Nonce is not consumed; record Nonce in Box storage.
     - Verify cumulative spend + amount <= Daily Limit.
     - Update cumulative spend.

## 4. Facilitator Compatibility

The group above is submitted through the GoPlausible x402-avm facilitator
(`https://facilitator.goplausible.xyz`, see `sentinelpay/payments/facilitator.py`).
The facilitator's `paymentGroup` format is explicitly documented as supporting
additional transactions beyond the payment leg (their docs cite "integrating
with other smart contracts on Algorand" by name), and `verify()`/`settle()`
only require specific fields on the transaction at `paymentIndex` — so the
SentinelPay app call at index 1 rides along in the same group without any
facilitator-side changes needed.
