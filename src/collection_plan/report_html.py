"""Interactive HTML report: a single self-contained file that walks through every step of the plan.

The page has no external dependencies (charts are plain SVG), so it opens offline and can be attached
to an e-mail. Data is embedded as JSON.
"""

from __future__ import annotations

import datetime as dt
import json
from importlib import resources
from pathlib import Path

import pandas as pd

from .forecast import quarterly
from .pipeline import PlanResult
from .schema import VOLUME_COLS

PLACEHOLDER = "/*__DATA__*/null"


def _round(x, nd=6):
    return None if x is None or pd.isna(x) else round(float(x), nd)


def build_payload(
    result: PlanResult,
    workforce: tuple[pd.DataFrame, pd.DataFrame] | None = None,
    calendars: pd.DataFrame | None = None,
) -> dict:
    cfg = result.config
    regions = list(next(iter(result.tools.values())).shares.index)
    month = result.monthly.assign(m=result.monthly["month"].dt.month)

    def series_by(df: pd.DataFrame, keys: list[str], index_col: str, size: int) -> dict:
        """Nested dict keys[0] -> keys[1] -> column -> list over index_col (1..size)."""
        out: dict = {}
        for key_vals, g in df.groupby(keys):
            key_vals = key_vals if isinstance(key_vals, tuple) else (key_vals,)
            node = out
            for k in key_vals[:-1]:
                node = node.setdefault(k, {})
            g = g.set_index(index_col)[VOLUME_COLS].reindex(range(1, size + 1), fill_value=0.0)
            node[key_vals[-1]] = {c: [_round(v, 2) for v in g[c]] for c in VOLUME_COLS}
        return out

    fc_q = quarterly(result.forecast, ["tool", "region"])
    tg_q = quarterly(result.targets, ["tool", "region"])
    tools = []
    for name, tp in result.tools.items():
        t = tp.tool
        tools.append(
            {
                "name": name,
                "group": t.group,
                "volume": t.volume,
                "is_new": t.is_new,
                "reference": t.reference,
                "allocation_from": t.allocation_from,
                "excluded": list(t.excluded_regions),
                "ticket_target": t.ticket_target,
                "ticket_factor": _round(tp.ticket_factor),
                "ticket_unadjusted": _round(tp.ticket_unadjusted, 2),
                "gains": t.gains,
                "reducer": t.efficiency_reducer,
                "fixed_efficiency": t.fixed_efficiency,
                "overrides": t.efficiency_overrides,
                "floor_factor": [_round(tp.productivity.floor_factor_qty), _round(tp.productivity.floor_factor_value)],
                "consolidated_factor": _round(tp.productivity.consolidated_factor),
                "shares": {r: {k: _round(v) for k, v in row.items()} for r, row in tp.shares.iterrows()},
                "base_ticket": {r: _round(v, 2) for r, v in tp.base_ticket.items()},
                "prod": {r: {k: _round(v) for k, v in row.items()} for r, row in tp.productivity.table.iterrows()},
                "eff": {r: {k: _round(v) for k, v in row.items()} for r, row in tp.efficiency.iterrows()},
            }
        )
    payload = {
        "generated": dt.datetime.now().strftime("%Y-%m-%d %H:%M"),
        "plan_year": cfg.plan_year,
        "history_year": cfg.history_year,
        "last_actual_month": cfg.last_actual_month,
        "gap_weight": cfg.gap_weight,
        "min_quarter_qty": cfg.min_quarter_qty,
        "market_growth": list(cfg.market_growth),
        "seasonality": {g: [v / sum(c) for v in c] for g, c in cfg.seasonality.items()},
        "regions": regions,
        "tools": tools,
        "plan": series_by(month, ["tool", "region"], "m", 12),
        "forecast_q": series_by(fc_q, ["tool", "region"], "quarter", 4),
        "target_q": series_by(tg_q, ["tool", "region"], "quarter", 4),
    }
    if workforce is not None:
        g, r = workforce
        payload["workforce"] = {
            "groups": [
                {
                    "name": wg.name,
                    "actions_per_day": wg.actions_per_day,
                    "tools": wg.tools,
                    "extra": [e.name for e in wg.extra_volumes],
                }
                for wg in cfg.workforce.groups
            ],
            "by_group": g.to_dict(orient="records"),
            "by_region": r.to_dict(orient="records"),
            "calendars": {} if calendars is None else {k: list(v) for k, v in calendars.iterrows()},
        }
    return payload


def write_html(
    result: PlanResult,
    path: str | Path,
    workforce: tuple[pd.DataFrame, pd.DataFrame] | None = None,
    calendars: pd.DataFrame | None = None,
) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    template = resources.files("collection_plan").joinpath("templates/report.html").read_text(encoding="utf-8")
    data = json.dumps(build_payload(result, workforce, calendars), default=str).replace("</", "<\\/")
    path.write_text(template.replace(PLACEHOLDER, data), encoding="utf-8")
    return path
