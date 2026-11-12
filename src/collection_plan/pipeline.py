"""Orchestrates the steps for every tool and returns the monthly plan.

volume -> regional split -> seasonality -> ticket -> productivity (selected) -> efficiency (paid)
"""

from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd

from .allocation import regional_shares
from .config import PlanConfig, ToolConfig
from .efficiency import borrowed_efficiency, plan_efficiency
from .forecast import annual, build_forecast, quarterly, to_wide
from .productivity import ProductivityResult, plan_productivity
from .schema import REGIONS, VOLUME_COLS, add_ratios, validate_history
from .seasonality import MONTHS, spread
from .ticket import adjustment_factor, base_ticket, monthly_ticket


@dataclass
class ToolPlan:
    """Everything computed for one tool: the intermediate steps are kept for reports and audits."""

    tool: ToolConfig
    shares: pd.DataFrame
    base_ticket: pd.Series
    ticket_factor: float
    ticket_unadjusted: float
    productivity: ProductivityResult
    efficiency: pd.DataFrame
    monthly: pd.DataFrame  # region, month + volume and ratio columns


@dataclass
class PlanResult:
    config: PlanConfig
    forecast: pd.DataFrame  # wide forecast of the history year (tool, region, month)
    targets: pd.DataFrame  # wide targets of the history year
    tools: dict[str, ToolPlan] = field(default_factory=dict)

    @property
    def monthly(self) -> pd.DataFrame:
        frames = [tp.monthly.assign(tool=name, group=tp.tool.group) for name, tp in self.tools.items()]
        cols = ["tool", "group", "region", "month", *VOLUME_COLS]
        return add_ratios(pd.concat(frames, ignore_index=True)[cols])

    def summary(self) -> pd.DataFrame:
        """Annual totals per tool: forecast vs plan."""
        plan = annual(self.monthly, ["tool"]).set_index("tool").reindex(list(self.tools))
        fc = annual(self.forecast, ["tool"]).set_index("tool").reindex(plan.index).fillna(0.0)  # new tools: 0
        out = pd.DataFrame(
            {
                "qty_executed_fc": fc["qty_executed"],
                "qty_executed_plan": plan["qty_executed"],
                "ticket_fc": fc["ticket"],
                "ticket_plan": plan["ticket"],
                "eff_value_fc": fc["eff_value"],
                "eff_value_plan": plan["eff_value"],
                "value_paid_fc": fc["value_paid"],
                "value_paid_plan": plan["value_paid"],
            }
        )
        out["value_paid_delta"] = (out["value_paid_plan"] / out["value_paid_fc"] - 1).where(out["value_paid_fc"] > 0)
        sums = out[["qty_executed_fc", "qty_executed_plan", "value_paid_fc", "value_paid_plan"]].sum()
        out.loc["TOTAL"] = {
            **sums.to_dict(),
            "ticket_fc": _ratio(self.forecast, "value_executed", "qty_executed"),
            "ticket_plan": _ratio(self.monthly, "value_executed", "qty_executed"),
            "eff_value_fc": _ratio(self.forecast, "value_paid", "value_executed"),
            "eff_value_plan": _ratio(self.monthly, "value_paid", "value_executed"),
            "value_paid_delta": sums["value_paid_plan"] / sums["value_paid_fc"] - 1,
        }
        return out


def _ratio(df: pd.DataFrame, num: str, den: str) -> float:
    d = df[den].sum()
    return float(df[num].sum() / d) if d else float("nan")


def _region_ratios(fc_tool: pd.DataFrame, regions: list[str]) -> pd.DataFrame:
    """Forecast ratios per region; regions without history fall back to the tool's consolidated ratios."""
    by_region = annual(fc_tool, ["region"]).set_index("region")
    total = annual(fc_tool, []).iloc[0]
    out = by_region.reindex(regions)
    for col in ["ticket", "prod_qty", "prod_value", "eff_qty", "eff_value"]:
        has_base = out["qty_executed"].fillna(0) > 0
        out[col] = out[col].where(has_base, total[col])
    return out


def run_plan(history: pd.DataFrame, cfg: PlanConfig, regions: list[str] | None = None) -> PlanResult:
    regions = regions or REGIONS
    hist = validate_history(history)
    forecast = build_forecast(hist, cfg.last_actual_month)
    targets = to_wide(hist).query("base == 'target'").drop(columns="base")
    result = PlanResult(cfg, forecast, targets)

    # tools with their own history first, so new tools can borrow from them
    ordered = sorted(cfg.tools, key=lambda t: t.is_new)
    for tool in ordered:
        result.tools[tool.name] = _plan_tool(tool, cfg, forecast, targets, result, regions)
    # keep the configuration order
    result.tools = {t.name: result.tools[t.name] for t in cfg.tools}
    return result


def _plan_tool(
    tool: ToolConfig,
    cfg: PlanConfig,
    forecast: pd.DataFrame,
    targets: pd.DataFrame,
    result: PlanResult,
    regions: list[str],
) -> ToolPlan:
    hist_tool = tool.reference or tool.name
    alloc_tool = tool.allocation_from or hist_tool
    fc_tool = forecast[forecast["tool"] == hist_tool]
    if fc_tool.empty:
        raise ValueError(f"{tool.name}: no history for '{hist_tool}'")

    # 1-2. volume and regional split
    fc_alloc = forecast[forecast["tool"] == alloc_tool].groupby("region")["qty_executed"].sum()
    tg_alloc = targets[targets["tool"] == alloc_tool].groupby("region")["qty_executed"].sum()
    shares = regional_shares(tg_alloc, fc_alloc, cfg.gap_weight, tool.excluded_regions, regions)
    qty_year = tool.volume * shares["share"]

    # 3. seasonality
    qty_month = spread(qty_year, cfg.seasonality[tool.group])

    # 4. ticket
    if tool.is_new:
        # same base ticket and adjustment factor as the reference tool (regions without
        # reference history already carry the reference's consolidated base)
        ref_plan = result.tools[tool.reference]
        base = ref_plan.base_ticket.reindex(regions)
        factor, unadjusted = ref_plan.ticket_factor, float("nan")
    else:
        base = base_ticket(quarterly(fc_tool, ["region"]), cfg.min_quarter_qty).reindex(regions)
        base = base.fillna(
            base_ticket(quarterly(fc_tool.assign(region="ALL"), ["region"]), cfg.min_quarter_qty).iloc[0]
        )
        factor, unadjusted = adjustment_factor(base, qty_month, cfg.market_growth, tool.ticket_target)
    ticket_month = monthly_ticket(base, cfg.market_growth, factor)
    value_month = qty_month * ticket_month

    # 5. productivity
    ratios = _region_ratios(fc_tool, regions)
    fc_share = (fc_alloc / fc_alloc.sum()).reindex(regions, fill_value=0.0) if fc_alloc.sum() else 0.0
    extra = (shares["share"] > fc_share) & (qty_year > 0)
    floor = None
    if cfg.productivity_floor and not tool.is_new:
        total = annual(fc_tool, []).iloc[0]
        floor = (float(total["prod_qty"]), float(total["prod_value"]))
    prod = plan_productivity(
        ratios[["prod_qty", "prod_value"]],
        tool.gain("prod_qty"),
        tool.gain("prod_value"),
        cfg.productivity_cap,
        qty_year,
        value_month.sum(axis=1),
        extra,
        floor,
        cfg.prioritize_large_debts,
    )

    # 6. efficiency
    if tool.fixed_efficiency:
        eff = pd.DataFrame(
            {"eff_qty": tool.fixed_efficiency["eff_qty"], "eff_value": tool.fixed_efficiency["eff_value"]},
            index=pd.Index(regions, name="region"),
        )
    elif tool.is_new:
        ref_m = result.tools[tool.reference].monthly
        eff = borrowed_efficiency(
            pd.Index(regions, name="region"),
            _ratio(ref_m, "qty_paid", "qty_executed"),
            _ratio(ref_m, "value_paid", "value_executed"),
            tool.efficiency_reducer,
        )
    else:
        eff = plan_efficiency(
            ratios[["eff_qty", "eff_value"]],
            tool.gain("eff_qty"),
            tool.gain("eff_value"),
            cfg.efficiency_cap,
            tool.efficiency_overrides,
        )

    monthly = _assemble(qty_month, value_month, prod.table, eff, cfg.plan_year)
    return ToolPlan(tool, shares, base, factor, unadjusted, prod, eff, monthly)


def _assemble(
    qty_month: pd.DataFrame, value_month: pd.DataFrame, prod: pd.DataFrame, eff: pd.DataFrame, year: int
) -> pd.DataFrame:
    rows = []
    for region in qty_month.index:
        pq, pv = prod.loc[region, "prod_qty"], prod.loc[region, "prod_value"]
        eq, ev = eff.loc[region, "eff_qty"], eff.loc[region, "eff_value"]
        for m in MONTHS:
            q, v = qty_month.loc[region, m], value_month.loc[region, m]
            rows.append(
                {
                    "region": region,
                    "month": pd.Timestamp(year=year, month=m, day=1),
                    "qty_executed": q,
                    "value_executed": v,
                    "qty_selected": q / pq if pq else 0.0,
                    "value_selected": v / pv if pv else 0.0,
                    "qty_paid": q * eq,
                    "value_paid": v * ev,
                }
            )
    return add_ratios(pd.DataFrame(rows))
