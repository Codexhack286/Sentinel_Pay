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

## Two implementations, same invariants

- `contracts/sentinelpay.py` — pure-Python **reference model** (`SentinelPayContractLogic`). Fast to unit test, used by the off-chain gateway/tests to check invariants without touching a chain.
- `contracts/pyteal_contract.py` — the **real, deployable** AVM v8 program. Compiles via PyTeal to actual TEAL bytecode. Uses Box storage for the nonce replay-protection check described above (invariant 4).

Both encode the same 6 invariants; `contracts/tests/test_pyteal_contract.py` checks the compiled TEAL contains the expected ops (group-size assert, `ed25519verify_bare`, `box_create`/`box_put`, selector check) so the two can't silently drift apart.

## Testing & Deployment
- Reference-model unit tests: `pytest contracts/tests/test_sentinelpay.py`
- PyTeal compilation tests: `pytest contracts/tests/test_pyteal_contract.py`
- Compile to TEAL: `uv run python contracts/compile.py` → `contracts/build/{approval,clear}.teal`
- TestNet account generation: `scripts/fund_testnet.py`
- TestNet deployment: `scripts/deploy_testnet.py` (written and reviewed; run it from a machine with Algorand TestNet connectivity — see `docs/status.md` for what's still network-gated)
