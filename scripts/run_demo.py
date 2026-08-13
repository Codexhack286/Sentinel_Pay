"""Interactive CLI runner for SentinelPay Demo Scenarios."""

import sys
import subprocess


def run_demo():
    print("=" * 60)
    print(" SentinelPay Demo: Autonomous Agent Economic Authorization ")
    print("=" * 60)
    print("\nSelect Demo Scenario:")
    print("1. Scenario A: Legitimate Autonomous Paid Research Flow")
    print("2. Scenario B: Prompt Injection / Malicious Tool Output Attack Flow")
    print("3. Run Both Scenarios")
    print("0. Exit")

    choice = input("\nEnter choice [1/2/3/0]: ").strip()
    if choice == "1":
        import examples.legitimate_flow
        examples.legitimate_flow.main()
    elif choice == "2":
        import examples.prompt_injection_flow
        examples.prompt_injection_flow.main()
    elif choice == "3":
        print("\n--- Running Scenario A ---")
        import examples.legitimate_flow
        examples.legitimate_flow.main()
        print("\n--- Running Scenario B ---")
        import examples.prompt_injection_flow
        examples.prompt_injection_flow.main()
    else:
        print("Exiting demo.")


if __name__ == "__main__":
    run_demo()
