# LangGraph Wrap for DeepAgent — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Wrap the existing `DeepAgent` harness in a single-node compiled LangGraph so it is deployable to LangSmith Deployments, without rewriting any agent internals.

**Architecture:** A new `agent/graph.py` exposes a compiled `StateGraph` whose one node (`deep_agent_run`) calls the existing `DeepAgent.run()` and returns the resulting `AgentExecutionLog` in state. A root-level `langgraph.json` registers the graph with LangGraph/LangSmith. Tests invoke the graph directly; docs explain local dev and deployment.

**Tech Stack:** Python 3.12, uv, LangGraph (`langgraph`), pydantic, existing SentinelPay packages.

## Global Constraints

- Python `>=3.11`, managed with `uv`; tests run via `uv run python -m pytest -q`.
- Do NOT modify `DeepAgent.run()`, the planner, gateway, policy engine, or verifier.
- The only new dependency is `langgraph` (plus its transitive `langchain-core`). No `langchain-deepagents`.
- Keep all existing `@traceable` decorators untouched.
- The graph must work fully offline with the default `MODEL_PROVIDER=local`.
- Match existing code style: module docstring, no comments unless useful, pydantic models for state-free data.
- Full suite must stay green: existing 153 tests plus the new graph tests.
- Commit after each task.

---

### Task 1: Add the `langgraph` dependency

**Files:**
- Modify: `pyproject.toml` (uv writes it), `uv.lock`

**Interfaces:**
- Consumes: nothing.
- Produces: `langgraph` installed in the venv so `from langgraph.graph import END, START, StateGraph` imports.

- [ ] **Step 1: Add the dependency**

Run: `uv add langgraph`
Expected: `pyproject.toml` gains a `"langgraph"` entry in `dependencies`, `uv.lock` updates, install completes.

- [ ] **Step 2: Verify the import works**

Run: `uv run python -c "from langgraph.graph import END, START, StateGraph; print('ok')"`
Expected: prints `ok`.

- [ ] **Step 3: Commit**

```bash
git add pyproject.toml uv.lock
git commit -m "deps: add langgraph for LangSmith deployment wrap"
```

---

### Task 2: Write the failing graph tests

**Files:**
- Test: `tests/unit/test_langgraph_graph.py`

**Interfaces:**
- Consumes: `agent.graph.build_graph()` (created in Task 3) — a function returning a compiled `StateGraph` that accepts `{"user_objective": str, "simulate_attack": bool}` and returns `{"output": AgentExecutionLog}`.
- Produces: the test contract that `agent/graph.py` must satisfy.

- [ ] **Step 1: Write the test file**

```python
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
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run python -m pytest tests/unit/test_langgraph_graph.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'agent.graph'`.

- [ ] **Step 3: Commit (the failing tests)**

```bash
git add tests/unit/test_langgraph_graph.py
git commit -m "test: failing tests for the DeepAgent LangGraph wrap"
```

---

### Task 3: Implement `agent/graph.py`

**Files:**
- Create: `agent/graph.py`

**Interfaces:**
- Consumes: `DeepAgent` and `AgentExecutionLog` from `agent.agent`; `build_planner` from `agent.planner`; `SentinelPayGateway` from `sentinelpay.gateway.middleware`; `LocalSemanticVerifier` from `sentinelpay.verifier.verifier`; `AgentPolicy` from `sentinelpay.policy.models`; `settings` from `sentinelpay.config`.
- Produces: `build_graph() -> CompiledStateGraph` and module-level `graph` (referenced by `langgraph.json` in Task 4).

- [ ] **Step 1: Write the minimal implementation**

```python
"""Single-node LangGraph wrap around the DeepAgent harness.

The node calls the existing ``DeepAgent.run()`` and returns the resulting
``AgentExecutionLog`` in state. Agent internals (planning, tools, gateway)
are untouched and stay observable through the @traceable decorators.
"""

from typing import TypedDict

from langgraph.graph import END, START, CompiledStateGraph, StateGraph

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


def _build_agent() -> DeepAgent:
    global _agent
    if _agent is None:
        _agent = DeepAgent(
            agent_id=AGENT_ID,
            policy=_default_policy(),
            gateway=SentinelPayGateway(verifier=LocalSemanticVerifier()),
            planner=build_planner(settings.MODEL_PROVIDER, settings.MODEL_NAME),
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
```

- [ ] **Step 2: Run the graph tests to verify they pass**

Run: `uv run python -m pytest tests/unit/test_langgraph_graph.py -v`
Expected: 3 passed.

- [ ] **Step 3: Verify the compiled graph imports cleanly**

Run: `uv run python -c "from agent.graph import graph; print(graph.name)"`
Expected: prints a non-empty graph name (e.g. `langgraph`).

- [ ] **Step 4: Run the full suite**

Run: `uv run python -m pytest -q`
Expected: 156 passed (153 existing + 3 new).

- [ ] **Step 5: Commit**

```bash
git add agent/graph.py
git commit -m "feat: single-node LangGraph wrap exposing DeepAgent for LangSmith"
```

---

### Task 4: Add `langgraph.json`

**Files:**
- Create: `langgraph.json` (repo root)

**Interfaces:**
- Consumes: `agent.graph.graph` (compiled graph from Task 3).
- Produces: LangGraph/LangSmith deployment config so `langgraph dev` and LangSmith Deployments can load the graph.

- [ ] **Step 1: Write the config file**

```json
{
  "dependencies": ["."],
  "graphs": {
    "deep_agent": "./agent/graph.py:graph"
  },
  "env": ".env"
}
```

- [ ] **Step 2: Validate JSON parses and the graph reference resolves**

Run:
```powershell
$env:PYTHONPATH='C:\Users\RYAN DAVE FERNANDES\Desktop\Sentinel_Pay'
uv run python -c "import json, importlib; json.load(open('langgraph.json')); m = importlib.import_module('agent.graph'); assert m.graph is not None; print('langgraph.json OK')"
```
Expected: prints `langgraph.json OK`.

- [ ] **Step 3: Commit**

```bash
git add langgraph.json
git commit -m "feat: add langgraph.json registering the DeepAgent graph"
```

---

### Task 5: Update documentation

**Files:**
- Modify: `README.md` (add subsection after the "LangSmith Tracing (optional)" section, before "### Starting the x402 Resource API")
- Modify: `docs/status.md` (add completed items in section 4)

**Interfaces:**
- Consumes: the graph and config from Tasks 3–4.
- Produces: user-facing docs for local dev and deployment.

- [ ] **Step 1: Add a README subsection**

Insert after the LangSmith tracing block:

```markdown
### Deploy the Agent as a LangGraph (optional)

`DeepAgent` is wrapped as a single-node compiled LangGraph at `agent/graph.py`,
so the exact same harness (planning, tools, SentinelPay gateway, policy and
verifier) can run inside LangSmith Deployments without rewriting any internals.
The graph input is `{"user_objective": "...", "simulate_attack": false}` and the
output is an `AgentExecutionLog`.

```bash
# Local dev server (no deploy needed)
uv run --with langgraph-cli[inmem] langgraph dev

# Deploy to LangSmith (builds from langgraph.json, uploads, creates a deployment)
# See https://docs.langchain.com/langsmith/cli#deploy
uv tool install langgraph-cli
langgraph deploy --name sentinelpay-agent
```

The same deployment can be reached over HTTP at `/invoke` (POST) with the graph
state above. Once deployed, traces appear automatically in the deployment's
LangSmith project.
```

- [ ] **Step 2: Update `docs/status.md`**

In section 4, under the `### Agent (`agent/`)` list, add:

```markdown
- [x] Single-node LangGraph wrap (`agent/graph.py` + `langgraph.json`) exposing
      `DeepAgent` to LangSmith Deployments without rewriting the harness
```

Also add one row to the section 6 priority matrix:

```markdown
| Deployment | LangGraph wrap for LangSmith | 🟡 P1 | Low | ✅ Done |
```

- [ ] **Step 3: Verify the docs render (no build step; just sanity-check the file edits)**

Run: `uv run python -c "open('README.md').read(); open('docs/status.md').read(); print('docs OK')"`
Expected: prints `docs OK`.

- [ ] **Step 4: Commit**

```bash
git add README.md docs/status.md
git commit -m "docs: document the LangGraph wrap and LangSmith deployment path"
```

---

### Task 6: Full verification

**Files:**
- None (verification only).

- [ ] **Step 1: Run the full test suite**

Run: `uv run python -m pytest -q`
Expected: 156 passed.

- [ ] **Step 2: Confirm the graph invokes end-to-end offline**

Run:
```powershell
uv run python -c "from agent.graph import graph; r = graph.invoke({'user_objective': 'Research renewable energy datasets'}); print(r['output'].status)"
```
Expected: `completed_successfully`.

- [ ] **Step 3: Confirm git state is clean and branches match**

Run: `git status --short`
Expected: no uncommitted changes (all committed per task).

