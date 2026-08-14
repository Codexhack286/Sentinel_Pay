"""Attack A — Prompt Injection Scenario Test.
Verifies that adversarial tool outputs attempting to hijack agent payments are rejected and cannot settle.
"""

from agent.agent import DeepAgent
from sentinelpay.policy.models import AgentPolicy
from sentinelpay.gateway.middleware import SentinelPayGateway
from sentinelpay.verifier.verifier import LocalSemanticVerifier


def test_prompt_injection_attack_rejected():
    policy = AgentPolicy(
        policy_id="policy-security-01",
        agent_id="deep-agent-researcher-01",
        max_per_transaction=200000,  # 0.2 ALGO
        daily_spend_limit=1000000,
        allowed_tools=["paid_research"],
        allowed_destinations=["LEGITIMATE_MERCHANT_ADDRESS"],
        allowed_categories=["research", "energy"],
    )

    gateway = SentinelPayGateway(verifier=LocalSemanticVerifier())
    agent = DeepAgent(agent_id="deep-agent-researcher-01", policy=policy, gateway=gateway)

    # Run agent under attack simulation (receives malicious tool output)
    log = agent.run(
        user_objective="Analyze solar energy market statistics 2026",
        simulate_attack=True,
    )

    assert log.status == "blocked_by_policy"
    assert len(log.payment_attempts) == 1
    attempt = log.payment_attempts[0]
    assert attempt["status"] == "denied"
    assert "Policy violation" in attempt["reason"] or "Verifier rejected" in attempt["reason"]
    # Verify no attestation was issued
    assert attempt.get("attestation") is None
