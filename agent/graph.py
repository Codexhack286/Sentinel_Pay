"""Single-node LangGraph wrap around the DeepAgent harness.

The node calls the existing ``DeepAgent.run()`` and returns the resulting
``AgentExecutionLog`` in state. Agent internals (planning, tools, gateway)
are untouched and stay observable through the @traceable decorators.
"""

import threading
from typing import TypedDict

from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

from agent.agent import AgentExecutionLog, DeepAgent
from agent.planner import build_planner
from sentinelpay.config import settings
from sentinelpay.gateway.middleware import SentinelPayGateway
from sentinelpay.policy.models import AgentPolicy
from sentinelpay.verifier.verifier import LocalSemanticVerifier

AGENT_ID = "deep-agent-researcher-01"


class AgentInput(TypedDict, total=False):
    user_objective: str
    simulate_attack: bool


class AgentState(AgentInput):
    output: AgentExecutionLog


def _default_policy() -> AgentPolicy:
    return AgentPolicy(
        policy_id="policy-research-v1",
        agent_id=AGENT_ID,
        max_per_transaction=200_000,
        daily_spend_limit=1_000_000,
        allowed_tools=["free_research", "paid_research"],
        allowed_destinations=[settings.RESOURCE_OWNER_ADDRESS],
        allowed_categories=["research", "energy", "solar", "dataset"],
    )


_agent: DeepAgent | None = None
_agent_lock = threading.Lock()


def _build_agent() -> DeepAgent:
    global _agent
    with _agent_lock:
        if _agent is None:
            _agent = DeepAgent(
                agent_id=AGENT_ID,
                policy=_default_policy(),
                gateway=SentinelPayGateway(verifier=LocalSemanticVerifier()),
                planner=build_planner(settings.MODEL_PROVIDER, settings.MODEL_NAME),
                resource_owner=settings.RESOURCE_OWNER_ADDRESS,
            )
        return _agent


def run_deep_agent(state: AgentState) -> AgentState:
    objective = state.get("user_objective")
    if not objective:
        raise ValueError("user_objective is required")
    log = _build_agent().run(
        user_objective=objective,
        simulate_attack=state.get("simulate_attack", False),
    )
    return {"output": log}


def build_graph() -> CompiledStateGraph:
    builder = StateGraph(AgentState)
    builder.add_node("deep_agent_run", run_deep_agent)
    builder.add_edge(START, "deep_agent_run")
    builder.add_edge("deep_agent_run", END)
    return builder.compile()


graph = build_graph()
