# SentinelPay Smart Contracts

## Overview
The SentinelPay smart contract is an Algorand Virtual Machine (AVM) application deployed to Algorand TestNet/MainNet.

It serves as the **hard cryptographic enforcement boundary** for agent payments.

## Responsibilities
1. **Atomic Group Verification**: Ensures payment transaction (Tx 0) and SentinelPay authorization call (Tx 1) execute together atomically.
2. **Signature Verification**: Verifies the Ed25519 signature of the attestation payload against the registered `verifier_pk`.
3. **Exact Field Matching**: Ensures `Tx[0].receiver == Attestation.destination` and `Tx[0].amount == Attestation.amount`.
4. **Replay Protection**: Records consumed nonces in AVM Box Storage to guarantee single-use.
5. **Spend Cap Tracking**: Atomically maintains cumulative daily spend state.

## Testing & Deployment
- Unit tests: `pytest contracts/tests/test_sentinelpay.py`
- TestNet deployment script: `scripts/fund_testnet.py`
