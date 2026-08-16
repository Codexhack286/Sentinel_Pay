"""Shared Algorand helpers for the operational scripts.

Four scripts previously carried byte-identical copies of `get_algod_client` and
an unbounded `wait_for_confirmation` loop that would spin forever if a
transaction never made it into a block.
"""

import base64
import sys
from typing import Any, Dict, Tuple

from algosdk import mnemonic
from algosdk.account import address_from_private_key
from algosdk.v2client import algod

from sentinelpay.config import settings

# A TestNet round is ~3s, so this is roughly a minute of patience before we
# conclude the transaction is not going to land.
DEFAULT_CONFIRMATION_ROUNDS = 20

EXPLORER_TX = "https://testnet.explorer.perawallet.app/tx/{}"
EXPLORER_APP = "https://testnet.explorer.perawallet.app/application/{}"


def get_algod_client() -> algod.AlgodClient:
    return algod.AlgodClient(settings.ALGOD_TOKEN, settings.ALGOD_ADDRESS, headers={})


def wait_for_confirmation(
    client: algod.AlgodClient, txid: str, max_rounds: int = DEFAULT_CONFIRMATION_ROUNDS
) -> Dict[str, Any]:
    """Block until `txid` is confirmed, or raise once `max_rounds` have passed."""
    start_round = client.status()["last-round"]
    for current in range(start_round, start_round + max_rounds):
        pending = client.pending_transaction_info(txid)
        if pending.get("confirmed-round", 0) > 0:
            return pending
        if pending.get("pool-error"):
            raise RuntimeError(f"Transaction {txid} rejected by the pool: {pending['pool-error']}")
        client.status_after_block(current)
    raise TimeoutError(f"Transaction {txid} was not confirmed within {max_rounds} rounds.")


def account_from_mnemonic(phrase: str) -> Tuple[str, str]:
    """Return (private_key, address) for a 25-word mnemonic."""
    private_key = mnemonic.to_private_key(phrase)
    return private_key, address_from_private_key(private_key)


def compile_teal(client: algod.AlgodClient, source: str) -> bytes:
    """Assemble TEAL source to bytecode via algod's developer API."""
    return base64.b64decode(client.compile(source)["result"])


def require(*names: str) -> None:
    """Exit with a clear message if any named setting is unset or zero."""
    missing = [name for name in names if not getattr(settings, name, None)]
    if missing:
        print(
            "Missing required .env values: " + ", ".join(missing) + "\n"
            "See .env.example and SETUP.md for how to obtain each one.",
            file=sys.stderr,
        )
        sys.exit(1)


def describe_error(exc: Exception) -> str:
    """Pull the useful line out of an algod rejection instead of dumping the blob."""
    text = str(exc)
    for marker in ("logic eval error:", "TransactionPool.Remember:", "rejected by logic"):
        if marker in text:
            return text.split(marker, 1)[1].strip().splitlines()[0]
    return text.strip().splitlines()[0] if text.strip() else repr(exc)
