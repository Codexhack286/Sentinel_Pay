# SentinelPay Visualizer Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the terminal + web visualizer that renders both SentinelPay demo scenes (prompt → reasoning → firewall decision → atomic group → explorer link) side by side, fully offline.

**Architecture:** One shared pydantic `ScenarioReport` producer (`sentinelpay/visualizer/report.py`) runs the existing `DeepAgent` for both scenes; two thin renderers consume it — a Rich terminal renderer (`sentinelpay/visualizer/terminal.py` + `scripts/run_visualizer.py`) and a server-rendered HTML page (`GET /visualize` on `services/api/app.py`). Renderers never compute, so they cannot drift.

**Tech Stack:** Python 3.12, uv, pydantic v2, Rich (new dep), FastAPI/TestClient, algosdk.

## Global Constraints

- Working tree on branch `ryan`; every task ends with a commit on `ryan`.
- Test command: `uv run python -m pytest -q` (rootdir `tests`, `contracts/tests`).
- New dependency: add `rich` to `[project] dependencies` in `pyproject.toml` (run `uv add rich`).
- Producer must never do network I/O; runs `DeepAgent` exactly as `examples/legitimate_flow.py` does.
- Explorer group id computed offline with deterministic sample `SuggestedParams` (fixed first/last valid, flat fee, TestNet genesis); the report labels it "would-be group".
- No changes to `agent/`, `sentinelpay/` core, or `examples/` — the visualizer only *consumes*.
- Follow existing pydantic model style (`BaseModel` + `Field(default_factory=...)`).

---
### Task 1: Add `rich` dependency

**Files:**
- Modify: `pyproject.toml`, `uv.lock`

**Interfaces:**
- Consumes: nothing.
- Produces: `rich` available for `sentinelpay/visualizer/terminal.py`.

- [ ] **Step 1: Add the dependency**

Run: `uv add rich`
Expected: `rich` and `markdown-it-py`, `pygments`, `mdurl` resolve and install.

- [ ] **Step 2: Verify import**

Run: `uv run python -c "from importlib.metadata import version; print(version('rich'))"`
Expected: prints a version (rich 15.x removed the `__version__` attribute).

- [ ] **Step 3: Commit**

```bash
git add pyproject.toml uv.lock
git commit -m "deps: add rich for terminal visualizer rendering"
```

---
### Task 2: `ScenarioReport` models and `build_scenario_report`

**Files:**
- Create: `sentinelpay/visualizer/__init__.py`
- Create: `sentinelpay/visualizer/report.py`
- Test: `tests/unit/test_visualizer_report.py`

**Interfaces:**
- Consumes: `agent.agent.DeepAgent`, `agent.planner.build_planner`, `sentinelpay.policy.models.AgentPolicy`, `sentinelpay.gateway.middleware.SentinelPayGateway`, `sentinelpay.verifier.verifier.LocalSemanticVerifier`, `sentinelpay.config.settings`, `sentinelpay.payments.algorand.build_protected_group`.
- Produces:
  - `DEFAULT_OBJECTIVE = "Research renewable energy datasets and retrieve 2026 statistics"`
  - `build_scenario_report(simulate_attack: bool, *, objective: str = DEFAULT_OBJECTIVE) -> ScenarioReport`
  - `ScenarioReport` pydantic model with fields: `scene: str` ("A"/"B"), `objective: str`, `reasoning: ScenarioReasoning`, `firewall: ScenarioFirewall`, `atomic_group: ScenarioGroup`, `explorer_link: str`, `offline: bool = True`, `verdict: str` ("authorized"|"blocked_by_policy"|"awaiting_authorization").
  - `ScenarioReasoning`: `plan_steps: List[str]`, `tool_query: str`, `tool_result: str`, `proposal_goal: str`, `proposal_amount: int`, `proposal_destination: str`, `proposal_derived_from: str`.
  - `ScenarioFirewall`: `status: str`, `amount: int`, `destination: str`, `reason: str`, `checks_passed: List[str]`, `checks_failed: List[str]`, `verifier_decision: str`, `attestation_id: Optional[str]`.
  - `ScenarioGroup`: `tx0: str`, `tx1: str`, `tx2: str`, `nonce: str`, `amount: int`, `destination: str`.
  - `_suggested_params() -> transaction.SuggestedParams` deterministic TestNet params.
  - `_explorer_link(attestation) -> str` builds `https://testnet.explorer.perawallet.app/group/<group_id>`.

- [ ] **Step 1: Write the failing tests**

```python
"""Unit tests for the visualizer report producer (sentinelpay/visualizer/report.py)."""

from sentinelpay.visualizer.report import build_scenario_report


def test_scene_a_report_is_authorized():
    report = build_scenario_report(False)

    assert report.scene == "A"
    assert report.verdict == "authorized"
    assert report.firewall.status == "authorized"
    assert report.firewall.attestation_id is not None
    assert report.reasoning.plan_steps
    assert report.reasoning.tool_result
    assert report.atomic_group.nonce
    assert report.offline is True
    # A real configured payee yields a group id; the placeholder (offline demo
    # default) degrades to an empty link rather than crashing.
    if report.explorer_link:
        assert report.explorer_link.startswith("https://testnet.explorer.perawallet.app/group/")


def test_scene_b_report_is_blocked_by_policy():
    report = build_scenario_report(True)

    assert report.scene == "B"
    assert report.verdict == "blocked_by_policy"
    assert report.firewall.status == "denied"
    assert report.reasoning.proposal_derived_from == "untrusted_tool_output"
    assert report.reasoning.proposal_destination.startswith("ATTACKER_FAKE_ADDR")
    assert report.reasoning.proposal_amount == 1_500_000


def test_custom_objective_flows_into_the_report():
    report = build_scenario_report(False, objective="Research battery storage tech")

    assert report.objective == "Research battery storage tech"
    assert report.reasoning.plan_steps[0].startswith("1.")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run python -m pytest tests/unit/test_visualizer_report.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'sentinelpay.visualizer'`.

- [ ] **Step 3: Implement `sentinelpay/visualizer/__init__.py`**

```python
"""SentinelPay visualizer: terminal and web renderers for the demo scenes."""
```

- [ ] **Step 4: Implement `sentinelpay/visualizer/report.py`**

```python
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
    # stable within a report. Only used for display; never submitted.
    # (algosdk 2.x uses positional first/last and gh; v1-era kwarg names raise.)
    return transaction.SuggestedParams(
        fee=1_000,
        first=1_000_000,
        last=1_001_000,
        gh=base64.b64encode(_TESTNET_GENESIS_HASH).decode(),
        gen=_TESTNET_GENESIS_ID,
        flat_fee=True,
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
    # calculate_group_id returns raw bytes; the explorer expects base64.
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
    # and offline — no spend is recorded on this throwaway evaluator.
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
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run python -m pytest tests/unit/test_visualizer_report.py -v`
Expected: 3 PASS.

- [ ] **Step 6: Run the full suite to confirm nothing regressed**

Run: `uv run python -m pytest -q`
Expected: 166 passed + 3 new = 169 passed.

- [ ] **Step 7: Commit**

```bash
git add sentinelpay/visualizer/__init__.py sentinelpay/visualizer/report.py tests/unit/test_visualizer_report.py
git commit -m "feat: scenario report producer for the demo visualizer"
```

---
### Task 3: Rich terminal renderer + `scripts/run_visualizer.py`

**Files:**
- Create: `sentinelpay/visualizer/terminal.py`
- Create: `scripts/run_visualizer.py`
- Test: `tests/unit/test_visualizer_terminal.py`

**Interfaces:**
- Consumes: `build_scenario_report`, `ScenarioReport` from Task 2.
- Produces:
  - `render_scenarios(reports: Sequence[ScenarioReport]) -> str` — Rich-rendered two-column text (Scene A | Scene B), verdict color-coded.
  - `main() -> None` — prints both scenes.

- [ ] **Step 1: Write the failing tests**

```python
"""Unit tests for the Rich terminal renderer (sentinelpay/visualizer/terminal.py)."""

from sentinelpay.visualizer.report import build_scenario_report
from sentinelpay.visualizer.terminal import main, render_scenarios


def test_render_scenarios_contains_both_verdicts():
    a = build_scenario_report(False)
    b = build_scenario_report(True)

    out = render_scenarios([a, b])

    assert "ALLOWED" in out
    assert "BLOCKED BY POLICY" in out
    assert "Scene A" in out
    assert "Scene B" in out


def test_main_does_not_raise():
    main()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run python -m pytest tests/unit/test_visualizer_terminal.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'sentinelpay.visualizer.terminal'`.

- [ ] **Step 3: Implement `sentinelpay/visualizer/terminal.py`**

```python
"""Rich terminal renderer for SentinelPay demo scenes.

Prints Scene A (legitimate) and Scene B (prompt injection) side by side,
color-coding the firewall verdict so the demo reads at a glance.
"""

import io
from typing import Sequence

from rich.console import Console, Group
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from sentinelpay.visualizer.report import ScenarioReport, build_scenario_report


def _verdict_label(report: ScenarioReport) -> Text:
    if report.verdict == "authorized":
        return Text("ALLOWED", style="bold green")
    if report.verdict == "blocked_by_policy":
        return Text("BLOCKED BY POLICY", style="bold red")
    return Text("AWAITING AUTHORIZATION", style="bold yellow")


def _scene_panel(report: ScenarioReport) -> Panel:
    table = Table.grid(padding=(0, 1))
    table.add_column(justify="left")

    provenance = ""
    if report.reasoning.proposal_derived_from == "untrusted_tool_output":
        provenance = "[bold red]derived from untrusted tool output[/bold red]"

    table.add_row(f"[bold]Objective:[/bold] {report.objective}")
    table.add_row("")
    table.add_row(f"[bold]Reasoning:[/bold] {report.reasoning.tool_query}")
    table.add_row(report.reasoning.tool_result[:160])
    table.add_row("")
    table.add_row(f"[bold]Plan:[/bold]")
    for step in report.reasoning.plan_steps:
        table.add_row(f"  {step}")
    table.add_row("")
    table.add_row(f"[bold]Proposed payment:[/bold] {report.reasoning.proposal_amount} uALGO "
                  f"-> {report.reasoning.proposal_destination[:16]}... {provenance}")
    table.add_row("")
    table.add_row(f"[bold]Firewall:[/bold] {report.firewall.status}")
    table.add_row(f"[bold]Reason:[/bold] {report.firewall.reason}")
    table.add_row(f"[bold]Checks passed:[/bold] {len(report.firewall.checks_passed)}")
    table.add_row(f"[bold]Checks failed:[/bold] {len(report.firewall.checks_failed)}")
    if report.firewall.attestation_id:
        table.add_row(f"[bold]Attestation:[/bold] {report.firewall.attestation_id}")
    table.add_row("")
    table.add_row(f"[bold]Atomic group:[/bold]")
    table.add_row(f"  {report.atomic_group.tx0}")
    table.add_row(f"  {report.atomic_group.tx1}")
    table.add_row(f"  {report.atomic_group.tx2}")
    table.add_row(f"[bold]Nonce:[/bold] {report.atomic_group.nonce[:16]}...")
    table.add_row("")
    verdict_row = Text.from_markup("[bold]Verdict:[/bold] ")
    verdict_row.append_text(_verdict_label(report))
    table.add_row(verdict_row)
    if report.explorer_link:
        table.add_row(f"[bold]Explorer:[/bold] [link={report.explorer_link}]{report.explorer_link}[/link]")

    return Panel(
        Group(table),
        title=f"Scene {report.scene}",
        border_style="cyan" if report.scene == "A" else "magenta",
    )


def render_scenarios(reports: Sequence[ScenarioReport]) -> str:
    console = Console(file=io.StringIO(), width=160)
    table = Table.grid(expand=True)
    table.add_column(ratio=1)
    table.add_column(ratio=1)
    for index in range(0, len(reports), 2):
        row = [_scene_panel(reports[index])]
        if index + 1 < len(reports):
            row.append(_scene_panel(reports[index + 1]))
        table.add_row(*row)
    console.print(table)
    return console.file.getvalue()


def main() -> None:
    reports = [
        build_scenario_report(False),
        build_scenario_report(True),
    ]
    print(render_scenarios(reports))
```

- [ ] **Step 4: Implement `scripts/run_visualizer.py`**

```python
"""Run the SentinelPay demo visualizer in the terminal."""

from sentinelpay.visualizer.terminal import main

if __name__ == "__main__":
    main()
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run python -m pytest tests/unit/test_visualizer_terminal.py -v`
Expected: 2 PASS.

- [ ] **Step 6: Smoke-test the CLI**

Run: `uv run python scripts/run_visualizer.py`
Expected: prints two side-by-side panels; Scene A shows ALLOWED, Scene B shows BLOCKED BY POLICY.

- [ ] **Step 7: Commit**

```bash
git add sentinelpay/visualizer/terminal.py scripts/run_visualizer.py tests/unit/test_visualizer_terminal.py
git commit -m "feat: Rich terminal visualizer rendering both demo scenes"
```

---
### Task 4: Web page `GET /visualize`

**Files:**
- Modify: `services/api/app.py`
- Test: `tests/unit/test_visualizer_web.py`

**Interfaces:**
- Consumes: `build_scenario_report` from Task 2.
- Produces: `GET /visualize` on the existing FastAPI app → `text/html` 200 page with both scenes.

- [ ] **Step 1: Write the failing test**

```python
"""Tests for the GET /visualize web page (services/api/app.py)."""

from fastapi.testclient import TestClient

from services.api.app import app

client = TestClient(app)


def test_visualize_page_renders_both_scenes():
    resp = client.get("/visualize")

    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/html")
    assert "Scene A" in resp.text
    assert "Scene B" in resp.text
    assert "AUTHORIZED" in resp.text
    assert "DENIED" in resp.text
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run python -m pytest tests/unit/test_visualizer_web.py -v`
Expected: FAIL with `404` (route not found).

- [ ] **Step 3: Implement the endpoint in `services/api/app.py`**

Add near the health endpoint (imports stay at top; HTML is inline):

```python
from html import escape  # add to the top imports of services/api/app.py
```

Then append the endpoint:

```python
def _scene_html(title: str, report) -> str:
    verdict_class = "ok" if report.verdict == "authorized" else "blocked"
    attestation = f"<p><b>Attestation:</b> {escape(report.firewall.attestation_id or '')}</p>"
    explorer = (
        f'<p><a href="{report.explorer_link}" target="_blank">View group on TestNet explorer</a></p>'
        if report.explorer_link
        else ""
    )
    return f"""
    <section class="scene {report.scene.lower()}">
      <h2>{title}</h2>
      <p><b>Objective:</b> {escape(report.objective)}</p>
      <h3>Reasoning</h3>
      <p><b>Query:</b> {escape(report.reasoning.tool_query)}</p>
      <p>{escape(report.reasoning.tool_result[:200])}</p>
      <h3>Plan</h3>
      <ul>{''.join(f'<li>{escape(s)}</li>' for s in report.reasoning.plan_steps)}</ul>
      <p><b>Proposed payment:</b> {report.reasoning.proposal_amount} uALGO &rarr;
         {escape(report.reasoning.proposal_destination[:16])}...
         <em>{escape(report.reasoning.proposal_derived_from)}</em></p>
      <h3>Firewall decision</h3>
      <p class="verdict {verdict_class}"><b>{escape(report.firewall.status.upper())}</b></p>
      <p>{escape(report.firewall.reason)}</p>
      <p>Checks passed: {len(report.firewall.checks_passed)} &middot;
         Checks failed: {len(report.firewall.checks_failed)}</p>
      {attestation}
      <h3>Atomic group</h3>
      <ul>
        <li>{escape(report.atomic_group.tx0)}</li>
        <li>{escape(report.atomic_group.tx1)}</li>
        <li>{escape(report.atomic_group.tx2)}</li>
      </ul>
      <p><b>Nonce:</b> {escape(report.atomic_group.nonce[:16])}...</p>
      <p><b>Verdict:</b> <span class="verdict {verdict_class}">{escape(report.verdict)}</span></p>
      {explorer}
    </section>
    """


@app.get("/visualize", response_class=Response)
def visualize():
    """HTML page rendering Scene A and Scene B side by side."""
    from sentinelpay.visualizer.report import build_scenario_report

    scene_a = build_scenario_report(False)
    scene_b = build_scenario_report(True)
    html = f"""<!doctype html>
<html><head><meta charset="utf-8"><title>SentinelPay Visualizer</title>
<style>
  body {{ font-family: system-ui, sans-serif; margin: 2rem; background: #0f172a; color: #e2e8f0; }}
  h1 {{ text-align: center; }}
  .grid {{ display: grid; grid-template-columns: 1fr 1fr; gap: 1.5rem; }}
  .scene {{ border: 2px solid #334155; border-radius: 8px; padding: 1rem 1.5rem; background: #1e293b; }}
  .scene.a {{ border-color: #22c55e; }}
  .scene.b {{ border-color: #ef4444; }}
  .verdict {{ font-weight: bold; }}
  .verdict.ok {{ color: #4ade80; }}
  .verdict.blocked {{ color: #f87171; }}
  a {{ color: #60a5fa; }}
</style></head>
<body>
  <h1>SentinelPay — Firewall Visualizer</h1>
  <p style="text-align:center">offline demo (no chain access)</p>
  <div class="grid">
    {_scene_html("Scene A — Legitimate flow", scene_a)}
    {_scene_html("Scene B — Prompt injection", scene_b)}
  </div>
</body></html>"""
    return Response(content=html, media_type="text/html")
```

Note: `Response` is already imported in `services/api/app.py`; `escape` must be added to the imports at the top.

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run python -m pytest tests/unit/test_visualizer_web.py -v`
Expected: 1 PASS.

- [ ] **Step 5: Full suite**

Run: `uv run python -m pytest -q`
Expected: 172 passed (169 + 2 terminal + 1 web).

- [ ] **Step 6: Commit**

```bash
git add services/api/app.py tests/unit/test_visualizer_web.py
git commit -m "feat: server-rendered /visualize web page"
```

---
### Task 5: Documentation + final verification

**Files:**
- Modify: `docs/status.md`
- Modify: `README.md`

**Interfaces:**
- Consumes: nothing new.

- [ ] **Step 1: Update `docs/status.md`**

- In section 5, under `### P2 — Presentation`, change the visualizer bullet to checked:
  `- [x] Terminal or web visualizer: prompt → reasoning → firewall decision → atomic group → explorer link, Scene A beside Scene B`
- In section 6 (priority matrix), change the visualizer row's Status column from `Not started` to `✅ Done`.
- Update the executive summary test count line `166/166` → `172/172` and the `### Tests — 166 passing` heading → `### Tests — 172 passing`.

- [ ] **Step 2: Update `README.md`**

After the "Run the Demos" code block (around line 189), add:

```markdown
# Render both scenes in the terminal visualizer
uv run python scripts/run_visualizer.py

# Or view the same pipeline as a web page (then open http://127.0.0.1:8000/visualize)
uv run python -m services.api.app
```

- [ ] **Step 3: Full suite**

Run: `uv run python -m pytest -q`
Expected: 172 passed.

- [ ] **Step 4: CLI + web smoke tests**

Run: `uv run python scripts/run_visualizer.py`
Expected: two panels render, verdicts colored.

Run: `uv run python -c "from fastapi.testclient import TestClient; from services.api.app import app; c=TestClient(app); r=c.get('/visualize'); print(r.status_code, r.headers['content-type']); assert 'AUTHORIZED' in r.text and 'DENIED' in r.text"`
Expected: `200 text/html; charset=utf-8`.

- [ ] **Step 5: Confirm clean tree and commit**

Run: `git status --short`
Expected: only `docs/status.md` and `README.md` modified.

```bash
git add docs/status.md README.md
git commit -m "docs: document the visualizer and refresh status"
```

- [ ] **Step 6: Push the branch**

```bash
git push -u origin ryan
```