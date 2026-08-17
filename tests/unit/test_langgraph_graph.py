"""Tests for the single-node LangGraph wrap around DeepAgent."""

import pytest

from agent.graph import build_graph

OBJECTIVE = "Research renewable energy datasets and retrieve 2026 statistics"


def test_langgraph_legitimate_flow_is_authorized():
    result = build_graph().invoke({"user_objective": OBJECTIVE})

    log = result["output"]
    assert log.status == "completed_successfully"
    assert log.plan.objective == OBJECTIVE
    assert len(log.tool_calls) == 1
    assert log.payment_attempts[0]["status"] == "authorized"
    assert log.payment_attempts[0]["attestation"] is not None


def test_langgraph_injected_flow_is_blocked_by_policy():
    result = build_graph().invoke(
        {"user_objective": OBJECTIVE, "simulate_attack": True}
    )

    log = result["output"]
    assert log.status == "blocked_by_policy"
    assert log.payment_attempts[0]["status"] == "denied"
    assert log.payment_attempts[0].get("attestation") is None


def test_langgraph_requires_user_objective():
    with pytest.raises(ValueError):
        build_graph().invoke({})
