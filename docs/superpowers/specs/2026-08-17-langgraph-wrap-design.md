# LangGraph Wrap for DeepAgent — Design

**Date**: 2026-08-17
**Status**: Approved
**Scope**: Wrap-not-rewrite LangGraph integration so the existing `DeepAgent` harness is deployable to LangSmith Deployments.

## 1. Goal

Make `agent.agent.DeepAgent` deployable to LangSmith Deployments (and locally testable
with `langgraph dev`) by wrapping the existing `DeepAgent.run()` in a single-node
compiled LangGraph. The agent internals are **not** rewritten: planning, tools, planner,
gateway, policy engine and verifier stay exactly as they are, and remain observable
through the existing `@traceable` decorators.

Explicitly out of scope:
- Multi-node graph mirroring the pipeline (would re-architect `run()`).
- Managed Deep Agents (`mda`) project layout or `langchain-deepagents`.
- A FastAPI endpoint for the agent.
- Any change to the SentinelPay security boundary.
- Audit findings from the project review (deferred, handled separately).

## 2. Architecture

Single-node graph:

```
START -> deep_agent_run -> END
```

The node constructs a `DeepAgent` (cached at module level after first use) and calls
`run()`, returning the resulting `AgentExecutionLog`.

Data flow:

```
{user_objective, simulate_attack?}  --invoke-->  DeepAgent.run()  -->  AgentExecutionLog
```

The `DeepAgent` is built with:
- The demo policy from `examples/legitimate_flow.py` (mirrored as a default).
- `SentinelPayGateway(verifier=LocalSemanticVerifier())`.
- Planner from `build_planner(settings.MODEL_PROVIDER, settings.MODEL_NAME)`.

## 3. New file: `agent/graph.py`

- `AgentState(TypedDict, total=False)`:
  - `user_objective: str` (required input)
  - `simulate_attack: bool` (optional input, demo parity)
  - `output: AgentExecutionLog` (result)
- `run_deep_agent(state) -> AgentState` node: builds/caches the agent, calls `run()`,
  returns `{"output": log}`.
- Module-level `graph` (compiled, referenced by `langgraph.json`) and `build_graph()`
  (returns a fresh compiled graph for tests).

## 4. `langgraph.json` (repo root)

```json
{
  "dependencies": ["."],
  "graphs": { "deep_agent": "./agent/graph.py:graph" },
  "env": ".env"
}
```

## 5. Dependencies

- Add `langgraph` via `uv add langgraph` (latest). `langchain-core` comes transitively.
- No `langchain-deepagents`, no extra model SDK.

## 6. Testing

New `tests/unit/test_langgraph_graph.py` (offline, rule planner):
- Legitimate objective -> `output.status == "completed_successfully"`, full log with
  plan, tool_calls, payment_attempts, attestation.
- `simulate_attack=True` -> `output.status == "blocked_by_policy"`.
- Existing 153 tests must stay green.

## 7. Docs

- README: new "Deploy the agent as a LangGraph" subsection (local `langgraph dev`,
  deploy via LangSmith UI or `langgraph deploy`).
- `docs/status.md`: mark the LangGraph wrap completed in the pending/hardening section.

## 8. Verification

- `uv run python -m pytest -q` full suite green.
- `uv run python -c "from agent.graph import graph; print(graph.name)"` imports cleanly.
- Local invocation of `graph.invoke({"user_objective": ...})` returns an
  `AgentExecutionLog` with `status` populated.