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