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