"""
Example Scenario B: Prompt Injection / Adversarial Tool Output Attack Flow
Adversarial setup: Search results contain injected prompt attempting to force agent to transfer 1.5 ALGO to attacker.
"""

from agent.agent import DeepAgent
from sentinelpay.policy.models import AgentPolicy
from sentinelpay.gateway.middleware import SentinelPayGateway
from sentinelpay.config import settings
from sentinelpay.verifier.verifier import LocalSemanticVerifier
from agent.planner import build_planner


def main():
    print("================================================================")
    print(" SCENARIO B: Prompt Injection / Economic Attack Defense Flow ")
    print("================================================================")

    # 1. Setup Policy for the Deep Agent
    policy = AgentPolicy(
        policy_id="policy-research-v1",
        agent_id="deep-agent-researcher-01",
        max_per_transaction=200000,  # 0.2 ALGO limit
        daily_spend_limit=1000000,    # 1.0 ALGO daily limit
        allowed_tools=["free_research", "paid_research"],
        allowed_destinations=["RESOURCE_OWNER_ALGORAND_ADDRESS_AAAAAAAAAAAAAAAAAAAAAAAAAAAA"],
        allowed_categories=["research", "energy", "solar", "dataset"],
    )

    # 2. Initialize SentinelPay Gateway and Deep Agent
    gateway = SentinelPayGateway(verifier=LocalSemanticVerifier())
    agent = DeepAgent(
        agent_id="deep-agent-researcher-01",
        policy=policy,
        gateway=gateway,
        planner=build_planner(settings.MODEL_PROVIDER, settings.MODEL_NAME),
    )

    # 3. User Goal
    user_goal = "Research renewable energy datasets and retrieve 2026 statistics"
    print(f"\n[USER] Goal: \"{user_goal}\"")

    # 4. Agent runs and encounters prompt injection in free tool output
    print("\n[AGENT] Querying free research sources...")
    log = agent.run(user_objective=user_goal, simulate_attack=True)

    print("\n[INCOMING MALICIOUS TOOL OUTPUT]:")
    print(f"        \"{log.tool_calls[0]['result']['content']}\"")

    print("\n[AGENT (COMPROMISED)] Attempting to execute injected transfer...")
    proposal = log.proposed_payment
    payment_attempt = log.payment_attempts[0]
    print(f"        Parameters taken from: {proposal.derived_from}")
    print(f"        Proposed Amount:      {payment_attempt['amount']} uALGO (exceeds the 0.2 ALGO cap)")
    print(f"        Proposed Destination: {payment_attempt['destination']}")
    print(
        "        Note: neither number is hardcoded. The agent parsed them out of\n"
        "        the malicious search result above and acted on what it read."
    )

    print("\n[SENTINELPAY FIREWALL ACTIVATED]")
    print(f"        Status:   {payment_attempt['status'].upper()}")
    print(f"        Decision: {payment_attempt['decision'].value}")
    print(f"        Reason:   {payment_attempt['reason']}")

    attestation = payment_attempt.get("attestation")
    if not attestation:
        print("\n[SECURITY ENFORCEMENT RESULT]:")
        print("        [DENIED]  No attestation issued.")
        print("        [BLOCKED] No signed authorization exists, so the atomic group")
        print("                  cannot be built and the contract would reject it anyway.")
        print("        [SECURE]  Zero funds moved; the user's budget is untouched.")
        print(
            "\n        The enforcement is on-chain, not just this message. Prove it with:\n"
            "          uv run python scripts/verify_attack.py --broadcast"
        )

    print(f"\n[FINAL AGENT RESULT] {log.final_output}")
    print("================================================================\n")


if __name__ == "__main__":
    main()
