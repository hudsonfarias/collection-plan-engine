"""Integration tests: business rules that must hold on the full plan."""

import pytest

from collection_plan.forecast import annual


def test_annual_volume_matches_the_official_volume(result, cfg):
    by_tool = result.monthly.groupby("tool")["qty_executed"].sum()
    for t in cfg.tools:
        assert by_tool[t.name] == pytest.approx(t.volume)


def test_excluded_region_has_no_volume(result):
    m = result.monthly
    assert m[(m["tool"] == "symbolic_disconnection") & (m["region"] == "Capital")]["qty_executed"].sum() == 0


def test_selected_ticket_never_exceeds_executed_ticket(result):
    a = annual(result.monthly, ["tool", "region"])
    a = a[a["qty_executed"] > 0]
    sel = a["value_selected"] / a["qty_selected"]
    assert (sel <= a["ticket"] * (1 + 1e-9)).all()
    t = annual(result.monthly, ["tool"])
    assert (t["value_selected"] / t["qty_selected"] <= t["ticket"] * (1 + 1e-9)).all()


def test_consolidated_productivity_not_below_forecast(result, cfg):
    plan = annual(result.monthly, ["tool"]).set_index("tool")
    fc = annual(result.forecast, ["tool"]).set_index("tool")
    for t in cfg.tools:
        if t.is_new:
            continue
        assert plan.loc[t.name, "prod_qty"] >= fc.loc[t.name, "prod_qty"] - 1e-9
        assert plan.loc[t.name, "prod_value"] >= fc.loc[t.name, "prod_value"] - 1e-9


def test_ticket_target_is_met(result, cfg):
    plan = annual(result.monthly, ["tool"]).set_index("tool")
    for t in cfg.tools:
        if t.ticket_target and not t.is_new:
            assert plan.loc[t.name, "ticket"] == pytest.approx(t.ticket_target)


def test_new_tool_efficiency_rules(result):
    plan = annual(result.monthly, ["tool"]).set_index("tool")
    assert plan.loc["digital_notice", "eff_value"] == pytest.approx(0.38)
    ref = plan.loc["remote_disconnection", "eff_value"]
    assert plan.loc["symbolic_disconnection", "eff_value"] == pytest.approx(ref * (1 - 0.36))


def test_contracted_efficiency_override(result):
    m = result.monthly
    cap = m[(m["tool"] == "re_disconnection") & (m["region"] == "Capital")]
    assert cap["value_paid"].sum() / cap["value_executed"].sum() == pytest.approx(0.062)


def test_summary_total_matches_monthly(result):
    s = result.summary()
    assert s.loc["TOTAL", "value_paid_plan"] == pytest.approx(result.monthly["value_paid"].sum())
