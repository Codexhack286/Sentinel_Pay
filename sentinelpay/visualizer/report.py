"""Shared report producer for the SentinelPay demo visualizer.

Runs the existing DeepAgent for one scene and normalizes the resulting
AgentExecutionLog into a pydantic ScenarioReport. Renderers (terminal, web)
only consume this model; they never compute. No network I/O happens here.
"""

import base64
from typing import List, Optional

from algosdk import transaction
from pydantic import BaseModel, Field

from agent.agent import AgentExecutionLog, DeepAgent
from agent.planner import build_planner
from sentinelpay.config import settings
from sentinelpay.gateway.middleware import SentinelPayGateway
from sentinelpay.payments.algorand import build_protected_group
from sentinelpay.policy.models import AgentPolicy
from sentinelpay.verifier.verifier import LocalSemanticVerifier

DEFAULT_OBJECTIVE = "Research renewable energy datasets and retrieve 2026 statistics"
AGENT_ID = "deep-agent-researcher-01"
EXPLORER_TMPL = "https://testnet.explorer.perawallet.app/group/{group_id}"

# TestNet genesis, used only so the offline group id is stable and realistic.
_TESTNET_GENESIS_ID = "testnet-v1.0"
_TESTNET_GENESIS_HASH = base64.b64decode("SGO1GKSzyE7IEPItTxCByw9x8FmnrCDexi9/cOUJOiI=")


class ScenarioReasoning(BaseModel):
    plan_steps: List[str] = Field(default_factory=list)
    tool_query: str = ""
    tool_result: str = ""
    proposal_goal: str = ""
    proposal_amount: int = 0
    proposal_destination: str = ""
    proposal_derived_from: str = ""


class ScenarioFirewall(BaseModel):
    status: str = ""
    amount: int = 0
    destination: str = ""
    reason: str = ""
    checks_passed: List[str] = Field(default_factory=list)
    checks_failed: List[str] = Field(default_factory=list)
    verifier_decision: str = ""
    attestation_id: Optional[str] = None


class ScenarioGroup(BaseModel):
    tx0: str = ""
    tx1: str = ""
    tx2: str = ""
    nonce: str = ""
    amount: int = 0
    destination: str = ""


class ScenarioReport(BaseModel):
    scene: str
    objective: str
    reasoning: ScenarioReasoning
    firewall: ScenarioFirewall
    atomic_group: ScenarioGroup
    explorer_link: str
    offline: bool = True
    verdict: str


def _policy() -> AgentPolicy:
    return AgentPolicy(
        policy_id="policy-research-v1",
        agent_id=AGENT_ID,
        max_per_transaction=200_000,
        daily_spend_limit=1_000_000,
        allowed_tools=["free_research", "paid_research"],
        allowed_destinations=[settings.RESOURCE_OWNER_ADDRESS],
        allowed_categories=["research", "energy", "solar", "dataset"],
    )


def _build_agent() -> DeepAgent:
    return DeepAgent(
        agent_id=AGENT_ID,
        policy=_policy(),
        gateway=SentinelPayGateway(verifier=LocalSemanticVerifier()),
        planner=build_planner(settings.MODEL_PROVIDER, settings.MODEL_NAME),
        resource_owner=settings.RESOURCE_OWNER_ADDRESS,
    )


def _suggested_params() -> transaction.SuggestedParams:
    # Deterministic: fixed round windows and fee so the offline group id is
    # stable across runs. Only used for display; never submitted.
    return transaction.SuggestedParams(
        fee=1_000,
        first=1_000_000,
        last=1_001_000,
        flat_fee=True,
        gen=_TESTNET_GENESIS_ID,
        gh=base64.b64encode(_TESTNET_GENESIS_HASH).decode(),
    )


def _explorer_link(attestation) -> str:
    # A placeholder (non-address) RESOURCE_OWNER_ADDRESS would make algosdk
    # raise on the sender field; degrade to no link rather than crash the demo.
    try:
        group = build_protected_group(
            sender=settings.RESOURCE_OWNER_ADDRESS,
            receiver=attestation.destination,
            amount=attestation.amount,
            attestation=attestation,
            sentinelpay_app_id=settings.SENTINELPAY_APP_ID or 1,
            budget_app_id=settings.BUDGET_APP_ID or 1,
            suggested_params=_suggested_params(),
        )
        group_id = transaction.calculate_group_id(group)
    except Exception:
        return ""
    return EXPLORER_TMPL.format(group_id=base64.b64encode(group_id).decode())


def _reasoning(log: AgentExecutionLog) -> ScenarioReasoning:
    plan = log.plan
    proposal = log.proposed_payment
    tool_call = log.tool_calls[0] if log.tool_calls else {}
    return ScenarioReasoning(
        plan_steps=plan.steps,
        tool_query=tool_call.get("query", ""),
        tool_result=(tool_call.get("result") or {}).get("content", ""),
        proposal_goal=proposal.declared_goal if proposal else "",
        proposal_amount=proposal.amount if proposal else 0,
        proposal_destination=proposal.destination if proposal else "",
        proposal_derived_from=proposal.derived_from if proposal else "",
    )


def _firewall(log: AgentExecutionLog, policy: AgentPolicy) -> ScenarioFirewall:
    attempt = log.payment_attempts[0] if log.payment_attempts else {}
    attestation = attempt.get("attestation") or {}
    reason = attempt.get("reason", "")

    # The gateway's GatewayResponse only carries the final decision; the
    # per-check results live in PolicyEvaluationResult, which the gateway does
    # not surface. Re-running the deterministic evaluation for display is pure
    # and offline â€” no spend is recorded on this throwaway evaluator.
    checks_passed: List[str] = []
    checks_failed: List[str] = []
    decision = ""
    canonical = attempt.get("canonical_intent")
    if canonical:
        from sentinelpay.intent.models import CanonicalIntent
        from sentinelpay.policy.evaluator import PolicyEvaluator

        result = PolicyEvaluator().evaluate(CanonicalIntent(**canonical), policy)
        checks_passed = list(result.checks_passed)
        checks_failed = list(result.checks_failed)
        decision = str(result.decision.value)

    return ScenarioFirewall(
        status=attempt.get("status", ""),
        amount=attempt.get("amount", 0),
        destination=attempt.get("destination", ""),
        reason=reason,
        checks_passed=checks_passed,
        checks_failed=checks_failed,
        verifier_decision=decision,
        attestation_id=attestation.get("attestation_id"),
    )


def _atomic_group(log: AgentExecutionLog) -> ScenarioGroup:
    attestation = (log.payment_attempts[0].get("attestation") or {}) if log.payment_attempts else {}
    return ScenarioGroup(
        tx0=(
            "Tx 0: Payment {amount} uALGO -> {destination}".format(
                amount=attestation.get("amount", 0),
                destination=(attestation.get("destination") or "")[:16] + "...",
            )
        ),
        tx1="Tx 1: SentinelPay validate_and_pay (binds attestation, nonce, spend cap)",
        tx2="Tx 2+: Opcode-budget NoOps",
        nonce=attestation.get("nonce", ""),
        amount=attestation.get("amount", 0),
        destination=attestation.get("destination", ""),
    )


def build_scenario_report(
    simulate_attack: bool, *, objective: str = DEFAULT_OBJECTIVE
) -> ScenarioReport:
    policy = _policy()
    log = _build_agent().run(user_objective=objective, simulate_attack=simulate_attack)

    attestation = (
        (log.payment_attempts[0].get("attestation") or {}) if log.payment_attempts else {}
    )
    explorer = ""
    if attestation:
        from sentinelpay.verifier.attestation import Attestation

        explorer = _explorer_link(Attestation(**attestation))

    # AgentExecutionLog.status uses "completed_successfully" for an authorized
    # scene; the report's verdict vocabulary is shorter.
    verdict = {
        "completed_successfully": "authorized",
        "blocked_by_policy": "blocked_by_policy",
    }.get(log.status, "awaiting_authorization")

    return ScenarioReport(
        scene="A" if not simulate_attack else "B",
        objective=objective,
        reasoning=_reasoning(log),
        firewall=_firewall(log, policy),
        atomic_group=_atomic_group(log),
        explorer_link=explorer,
        verdict=verdict,
    )