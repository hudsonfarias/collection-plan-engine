"""Unit tests: one rule per test, on small hand-made inputs."""

import math

import numpy as np
import pandas as pd
import pytest

from collection_plan.allocation import regional_shares
from collection_plan.efficiency import plan_efficiency
from collection_plan.forecast import build_forecast
from collection_plan.productivity import plan_productivity
from collection_plan.seasonality import normalize, spread
from collection_plan.ticket import adjustment_factor, base_ticket, monthly_ticket

REG = ["A", "B", "C"]


# ---------------------------------------------------------------- forecast
def test_forecast_uses_actuals_until_cutoff_then_targets(history):
    fc = build_forecast(history, last_actual_month=10)
    exe = history[history["stage"] == "executed"]
    act = exe[(exe["base"] == "actual") & (exe["month"].dt.month <= 10)]["qty"].sum()
    tgt = exe[(exe["base"] == "target") & (exe["month"].dt.month > 10)]["qty"].sum()
    assert fc["qty_executed"].sum() == pytest.approx(act + tgt)


# ---------------------------------------------------------------- allocation
def test_shares_sum_to_one_and_reward_regions_below_target():
    target = pd.Series([100.0, 100.0, 0.0], index=REG)
    fc = pd.Series([120.0, 50.0, 10.0], index=REG)  # A above, B 50% below, C without target
    s = regional_shares(target, fc, gap_weight=0.25, regions=REG)
    assert s["share"].sum() == pytest.approx(1.0)
    assert s.loc["A", "gap"] == 0 and s.loc["B", "gap"] == pytest.approx(0.5)
    assert s.loc["B", "share"] > s.loc["A", "share"]  # below target gets more
    assert s.loc["C", "share"] == 0  # no target -> no target


def test_excluded_region_gets_zero_and_others_are_renormalised():
    target = pd.Series([80.0, 10.0, 10.0], index=REG)
    s = regional_shares(target, target, gap_weight=0.25, excluded=["A"], regions=REG)
    assert s.loc["A", "share"] == 0
    assert s.loc["B", "share"] == pytest.approx(0.5) and s["share"].sum() == pytest.approx(1.0)


def test_allocation_without_target_falls_back_to_forecast_split():
    s = regional_shares(pd.Series(0.0, index=REG), pd.Series([1.0, 3.0, 0.0], index=REG), 0.25, regions=REG)
    assert list(s["share"]) == pytest.approx([0.25, 0.75, 0.0])


def test_allocation_fails_when_everything_is_excluded():
    with pytest.raises(ValueError):
        regional_shares(
            pd.Series([1.0, 0, 0], index=REG), pd.Series([1.0, 0, 0], index=REG), 0.25, excluded=["A"], regions=REG
        )


# ---------------------------------------------------------------- seasonality
def test_seasonality_is_normalised_and_preserves_the_annual_volume():
    curve = [0.0712, 0.0636, 0.0928, 0.0758, 0.0804, 0.0882, 0.0997, 0.095, 0.0843, 0.0812, 0.0797, 0.0882]
    assert normalize(curve).sum() == pytest.approx(1.0)
    m = spread(pd.Series([1200.0, 600.0], index=["A", "B"]), curve)
    assert list(m.sum(axis=1)) == pytest.approx([1200.0, 600.0])


def test_seasonality_rejects_bad_curves():
    with pytest.raises(ValueError):
        normalize([1.0] * 11)


# ---------------------------------------------------------------- ticket
def test_base_ticket_ignores_quarters_with_too_few_executions():
    q = pd.DataFrame(
        {
            "region": "A",
            "quarter": [1, 2, 3, 4],
            "qty_executed": [1, 100, 100, 100],
            "value_executed": [5_000, 1_000, 2_000, 3_000],
        }
    )
    assert base_ticket(q, min_qty=30)["A"] == pytest.approx(20.0)  # mean of 10, 20, 30; Q1 ignored


def test_adjustment_factor_hits_the_target_average_ticket():
    base = pd.Series([1000.0, 1500.0], index=["A", "B"])
    qty = pd.DataFrame(np.full((2, 12), 10.0), index=["A", "B"], columns=range(1, 13))
    growth = [0.0] * 6 + [0.5] * 6
    factor, _ = adjustment_factor(base, qty, growth, target=900)
    tk = monthly_ticket(base, growth, factor)
    assert (tk * qty).to_numpy().sum() / qty.to_numpy().sum() == pytest.approx(900)


def test_no_target_means_factor_one():
    base = pd.Series([1000.0], index=["A"])
    qty = pd.DataFrame(np.ones((1, 12)), index=["A"], columns=range(1, 13))
    assert adjustment_factor(base, qty, [0.1] * 12, None)[0] == 1.0


# ---------------------------------------------------------------- productivity
def _prod_case(floor, prioritize):
    fc = pd.DataFrame({"prod_qty": [0.90, 0.50], "prod_value": [0.90, 0.40]}, index=["A", "B"])
    qty = pd.Series([100.0, 100.0], index=["A", "B"])  # plan sends half of the volume to low-productivity B
    val = pd.Series([100_000.0, 200_000.0], index=["A", "B"])
    extra = pd.Series([False, True], index=["A", "B"])
    return plan_productivity(fc, 0.01, 0.01, 1.0, qty, val, extra, floor, prioritize), qty, val


def test_floor_rule_lifts_consolidated_productivity_to_the_forecast():
    res, qty, _ = _prod_case(floor=(0.80, 0.70), prioritize=False)
    consolidated = qty.sum() / (qty / res.table["prod_qty"]).sum()
    assert consolidated == pytest.approx(0.80)
    assert res.table.loc["A", "prod_qty"] == pytest.approx(0.91)  # region without extra volume untouched


def test_floor_rule_does_nothing_when_already_above():
    res, _, _ = _prod_case(floor=(0.10, 0.10), prioritize=False)
    assert res.floor_factor_qty == 1.0 and res.table.loc["B", "prod_qty"] == pytest.approx(0.51)


def test_large_debts_first_keeps_selected_ticket_at_or_below_executed():
    res, qty, val = _prod_case(floor=None, prioritize=True)
    t = res.table
    assert (t["prod_value"] >= t["prod_qty"] - 1e-12).all()
    sel_ticket = (val / t["prod_value"]).sum() / (qty / t["prod_qty"]).sum()
    assert sel_ticket <= val.sum() / qty.sum() + 1e-9


# ---------------------------------------------------------------- efficiency
def test_efficiency_gain_cap_and_override():
    fc = pd.DataFrame({"eff_qty": [0.995, 0.5], "eff_value": [0.02, 0.3]}, index=["A", "B"])
    e = plan_efficiency(fc, 0.01, 0.005, 1.0, {"A": {"eff_value": 0.062}})
    assert e.loc["A", "eff_qty"] == 1.0  # capped
    assert e.loc["A", "eff_value"] == pytest.approx(0.062)  # contracted override
    assert e.loc["B", "eff_value"] == pytest.approx(0.305)
    assert math.isclose(e.loc["B", "eff_qty"], 0.51)
