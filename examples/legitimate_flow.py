"""
Example Scenario A: Legitimate Autonomous Payment Flow
User Objective: "Research renewable energy datasets and purchase relevant reports up to 0.10 ALGO."
"""

import json
from agent.agent import DeepAgent
from sentinelpay.policy.models import AgentPolicy
from sentinelpay.gateway.middleware import SentinelPayGateway
from sentinelpay.verifier.verifier import LocalSemanticVerifier
from sentinelpay.payments.x402 import X402PaymentHandler


def main():
    print("================================================================")
    print(" SCENARIO A: Legitimate Autonomous Agent Payment Flow ")
    print("================================================================")

    # 1. Setup Policy for the Deep Agent
    policy = AgentPolicy(
        policy_id="policy-research-v1",
        agent_id="deep-agent-researcher-01",
        max_per_transaction=200000,  # 0.2 ALGO
        daily_spend_limit=1000000,    # 1.0 ALGO
        allowed_tools=["free_research", "paid_research"],
        allowed_destinations=["RESOURCE_OWNER_ALGORAND_ADDRESS_AAAAAAAAAAAAAAAAAAAAAAAAAAAA"],
        allowed_categories=["research", "energy", "solar", "dataset"],
    )

    # 2. Initialize SentinelPay Gateway and Deep Agent
    gateway = SentinelPayGateway(verifier=LocalSemanticVerifier())
    agent = DeepAgent(agent_id="deep-agent-researcher-01", policy=policy, gateway=gateway)

    # 3. User Goal
    user_goal = "Research renewable energy datasets and retrieve 2026 statistics"
    print(f"\n[USER] Goal: \"{user_goal}\"")

    # 4. Agent Plans and Executes
    print("\n[AGENT] Planning task and querying tools...")
    log = agent.run(user_objective=user_goal, simulate_attack=False)

    print(f"\n[PLAN] Objective: {log.plan.objective}")
    for step in log.plan.steps:
        print(f"       {step}")

    print("\n[AGENT] Free research tool result received:")
    print(f"        {log.tool_calls[0]['result']['content']}")

    print("\n[SENTINELPAY] Processing Payment Request...")
    payment_attempt = log.payment_attempts[0]
    print(f"        Status:      {payment_attempt['status'].upper()}")
    print(f"        Amount:      {payment_attempt['amount']} uALGO (0.1 ALGO)")
    print(f"        Destination: {payment_attempt['destination']}")
    print(f"        Reason:      {payment_attempt['reason']}")

    attestation = payment_attempt.get("attestation")
    if attestation:
        print(f"\n[ATTESTATION ISSUED]")
        print(f"        Attestation ID: {attestation['attestation_id']}")
        print(f"        Intent Hash:    {attestation['intent_hash'][:32]}...")
        print(f"        Nonce:          {attestation['nonce']}")
        print(f"        Signature:      {attestation['signature'][:32]}...")

        # Construct settlement proof
        proof = X402PaymentHandler.construct_settlement_proof(
            attestation=payment_attempt["attestation"],
            tx_id="tx_demo_settle_001",
            group_id="group_demo_settle_001",
        )
        print(f"\n[ALGORAND] Atomic Transaction Group Constructed:")
        print(f"        Tx 0: Payment 100,000 uALGO -> {payment_attempt['destination'][:16]}...")
        print(f"        Tx 1: SentinelPay App Call (Validates Attestation, Nonce, Spend Caps)")
        print(f"        Tx 2: x402 Settlement Note ({proof[:30]}...)")
        print("\n[STATUS] Settlement confirmed on Algorand! Paid resource delivered to agent.")

    print(f"\n[FINAL AGENT RESULT] {log.final_output}")
    print("================================================================\n")


if __name__ == "__main__":
    main()
