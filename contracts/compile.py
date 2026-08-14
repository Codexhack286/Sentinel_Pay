"""
Compile the SentinelPay PyTeal contract to TEAL artifacts.

Usage:
    uv run python contracts/compile.py

Writes:
    contracts/build/approval.teal
    contracts/build/clear.teal

These artifacts are what `scripts/deploy_testnet.py` reads and submits in an
ApplicationCreate transaction. Keeping compilation as an explicit, separate
step (rather than compiling inline at deploy time) makes it easy to diff
contract changes in code review and matches the AlgoKit build convention.
"""

from pathlib import Path

from contracts.pyteal_contract import compile_approval, compile_clear

BUILD_DIR = Path(__file__).parent / "build"


def main() -> None:
    BUILD_DIR.mkdir(exist_ok=True)

    approval_teal = compile_approval()
    clear_teal = compile_clear()

    approval_path = BUILD_DIR / "approval.teal"
    clear_path = BUILD_DIR / "clear.teal"

    approval_path.write_text(approval_teal)
    clear_path.write_text(clear_teal)

    print(f"Wrote {approval_path} ({len(approval_teal.splitlines())} lines)")
    print(f"Wrote {clear_path} ({len(clear_teal.splitlines())} lines)")
    print("\nNext: uv run python scripts/deploy_testnet.py")


if __name__ == "__main__":
    main()
