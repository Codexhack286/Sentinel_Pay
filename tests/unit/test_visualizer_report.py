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
        prefix = "https://testnet.explorer.perawallet.app/group/"
        assert report.explorer_link.startswith(prefix)
        # The base64 group id is URL-encoded: no path-unsafe characters remain.
        group_id = report.explorer_link[len(prefix):]
        assert not any(c in group_id for c in "/+=")


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