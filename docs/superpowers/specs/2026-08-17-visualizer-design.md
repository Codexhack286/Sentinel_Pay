# SentinelPay Visualizer — Design

**Date**: 2026-08-17
**Status**: Approved
**Branch**: `ryan`

## 1. Purpose

Render the full SentinelPay pipeline for both demo scenes — prompt → reasoning →
firewall decision → atomic group → explorer link — side by side (Scene A beside
Scene B), in two forms: a terminal renderer and a web page. The visualizer is
the competition-facing "what the firewall just did" surface. It must run fully
offline (no chain access required) and show both outcomes with equal honesty.

## 2. Scope

In scope: shared report producer, terminal renderer, web page, tests, docs.

Out of scope (already pending, not part of this work): embeddings verifier,
ASA/USDC (`axfer`) support, nonce-box pruning, facilitator `/verify`+`/settle`
path, demo video/slides, MainNet deployment.

## 3. Architecture

One shared producer, two thin renderers. Renderers never compute anything — they
consume a pydantic `ScenarioReport` so terminal and web cannot drift.

```
agent.DeepAgent.run()          (existing, unchanged)
        │
        ▼
sentinelpay/visualizer/report.py   build_scenario_report(simulate_attack)
        │                                   │
        │                                   ▼
        │                          ScenarioReport (pydantic)
        │                                   │
        ├───────────────────────────────────┼───────────────────────────┐
        ▼                                   ▼                           ▼
scripts/run_visualizer.py      services/api/app.py                 tests
(Rich terminal, two columns)   GET /visualize (HTML grid)
```

### 3.1 `sentinelpay/visualizer/report.py`

`build_scenario_report(simulate_attack: bool, *, objective: str) -> ScenarioReport`

Runs `DeepAgent.run(user_objective=objective, simulate_attack=simulate_attack)`
using the same construction as `examples/legitimate_flow.py` (policy
`policy-research-v1`, `SentinelPayGateway(verifier=LocalSemanticVerifier())`,
`build_planner(settings.MODEL_PROVIDER, settings.MODEL_NAME)`), then folds the
`AgentExecutionLog` and the payment attempt into a structured report:

- `scene`: "A" | "B" (derived from `simulate_attack`)
- `objective` / `prompt`: the user goal
- `reasoning`: plan steps, tool query + result content, derived proposal
  (declared goal, amount, destination, `derived_from` provenance)
- `firewall`: the gateway decision — status, amount, destination, reason,
  policy `checks_passed` / `checks_failed`, verifier decision, attestation id
- `atomic_group`: a deterministic render of the would-be group:
  Tx0 payment, Tx1 `validate_and_pay` (binds attestation/nonce/spend cap),
  Tx2+ budget NoOps, with the real nonce/amount/destination
- `explorer_link`: `https://testnet.explorer.perawallet.app/group/<group_id>`
  computed offline via algosdk `calculate_group_id` over the same transactions
  `build_protected_group` would emit, using deterministic sample params
- `verdict`: `authorized` | `blocked_by_policy` | `awaiting_authorization`

The group id is computed from the real attestation fields but deterministic
sample `SuggestedParams` (frozen `first_valid`/`last_valid`, fixed fee), because
no chain is contacted. This is stated in the report (`offline: true`), and the
link is labeled "would-be group".

### 3.2 `sentinelpay/visualizer/terminal.py`

Rich renderer. `render_scenarios(reports: Sequence[ScenarioReport]) -> str` and
a `main()` that prints Scene A and Scene B in two adjacent columns
(`rich.table.Table` / `Columns`). Verdicts are color-coded: green `ALLOWED` /
red `BLOCKED BY POLICY`. Provenance of a hijacked payment (`derived_from ==
"untrusted_tool_output"`) is highlighted.

### 3.3 Web page (`GET /visualize` on `services/api/app.py`)

Server-rendered HTML, inline CSS grid, two columns (Scene A | Scene B), no JS
build step, no new web dependencies. The endpoint imports
`build_scenario_report` for both scenes and renders a compact page: header,
objective, reasoning, firewall decision (color-coded), atomic group, explorer
link. Runs fully offline.

### 3.4 Entry point

`scripts/run_visualizer.py` — prints both scenarios to the terminal. Mirrors
`scripts/run_demo.py`'s role but renders instead of narrating.

## 4. Data flow

1. User runs `uv run python scripts/run_visualizer.py` (or hits `GET /visualize`).
2. Producer runs both scenes through the existing, unchanged `DeepAgent`.
3. Each run's `AgentExecutionLog` is normalized into a `ScenarioReport`.
4. Terminal/Web render the reports side by side.

## 5. Error handling

- `DeepAgent.run` never raises for either scene (both are deterministic offline
  paths already exercised by `test_agent.py`). The producer still wraps the run
  and surfaces any unexpected exception as a `ScenarioReport` with
  `verdict="error"` and the message in `firewall.reason`, so the renderers never
  crash on a broken environment.
- No network I/O in the producer: `build_planner` is `local` by default;
  if `MODEL_PROVIDER=ollama` is set but unreachable, the planner already falls
  back to rules.

## 6. Testing

- `tests/unit/test_visualizer_report.py`:
  - Scene A report has `verdict="authorized"`, one authorized payment attempt,
    `explorer_link` contains a 52-char group id, non-empty reasoning/plan.
  - Scene B report has `verdict="blocked_by_policy"`, derived proposal
    `derived_from="untrusted_tool_output"` with the attacker amount/destination.
  - `build_scenario_report` never raises and never touches the network.
- `tests/unit/test_visualizer_web.py` (or extend existing API tests):
  `GET /visualize` returns 200, `text/html`, and body contains both `Scene A`
  and `Scene B` verdict text.

## 7. Dependency

`rich` added to `[project] dependencies` (pure-Python terminal rendering).
No other new runtime deps; web page is server-rendered HTML + inline CSS.

## 8. Documentation

- `docs/status.md`: mark the visualizer row done (priority matrix + P2
  presentation section).
- `README.md`: add a "Run the visualizer" snippet under the demos section.