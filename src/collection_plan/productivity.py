"""Step 5: productivity (executed / selected), which defines how much must be selected.

1. plan = forecast + gain, capped.
2. Floor rule: moving volume to regions with lower productivity drags the tool's consolidated
   productivity down (composition effect). If it falls below the forecast, the regions that received
   extra volume get a single extra gain until the consolidated value matches the forecast.
3. Large-debts-first rule: value productivity >= qty productivity in every region, so the selected
   ticket never exceeds the executed ticket; then a single factor fixes the consolidated ticket too.
"""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd


@dataclass
class ProductivityResult:
    table: pd.DataFrame  # region: prod_qty, prod_value (+ intermediate columns)
    floor_factor_qty: float = 1.0
    floor_factor_value: float = 1.0
    consolidated_factor: float = 1.0


def _floor(prod: pd.Series, volume: pd.Series, extra: pd.Series, floor: float, cap: float) -> tuple[pd.Series, float]:
    vol = volume.astype(float)
    sel_extra = (vol / prod)[extra].sum()
    sel_other = (vol / prod)[~extra].sum()
    total = vol.sum()
    consolidated = total / (sel_extra + sel_other) if (sel_extra + sel_other) else 0.0
    if consolidated >= floor or sel_extra <= 0:
        return prod, 1.0
    factor = max(1e-4, (total / floor - sel_other) / sel_extra)
    out = prod.copy()
    out[extra] = (prod[extra] / factor).clip(upper=cap)
    return out, factor


def plan_productivity(
    fc_prod: pd.DataFrame,
    gain_qty: float,
    gain_value: float,
    cap: float,
    qty_executed: pd.Series,
    value_executed: pd.Series,
    extra_volume: pd.Series,
    floor: tuple[float, float] | None,
    prioritize_large_debts: bool,
) -> ProductivityResult:
    """fc_prod: region -> prod_qty, prod_value (forecast). Volumes are the plan's annual executed totals."""
    idx = qty_executed.index
    pq = (fc_prod["prod_qty"].reindex(idx) + gain_qty).clip(upper=cap)
    pv = (fc_prod["prod_value"].reindex(idx) + gain_value).clip(upper=cap)
    table = pd.DataFrame(
        {
            "fc_prod_qty": fc_prod["prod_qty"].reindex(idx),
            "fc_prod_value": fc_prod["prod_value"].reindex(idx),
            "gain_prod_qty": pq,
            "gain_prod_value": pv,
        }
    )
    fq = fv = 1.0
    extra = extra_volume.reindex(idx, fill_value=False).astype(bool)
    if floor is not None:
        pq, fq = _floor(pq, qty_executed, extra, floor[0], cap)
        pv, fv = _floor(pv, value_executed, extra, floor[1], cap)
    consolidated = 1.0
    if prioritize_large_debts:
        pv = pd.concat([pv, pq], axis=1).max(axis=1)
        q, v = qty_executed.sum(), value_executed.sum()
        if q > 0 and v > 0:
            ticket_selected = (value_executed / pv).sum() / (qty_executed / pq).sum()
            consolidated = max(1.0, ticket_selected / (v / q))
            pv = (pv * consolidated).clip(upper=cap)
    table["prod_qty"] = pq
    table["prod_value"] = pv
    return ProductivityResult(table, fq, fv, consolidated)
