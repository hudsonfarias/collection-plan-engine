"""Step 4: executed ticket (average debt per executed action).

base ticket  = simple mean of the history-year quarterly tickets (quarters with too few executions
               are ignored), kept flat over the plan year
monthly      = base x (1 + market growth of the month) x adjustment factor
factor       = target average ticket / unadjusted average ticket (1 when there is no target)
"""

from __future__ import annotations

from collections.abc import Sequence

import numpy as np
import pandas as pd

from .seasonality import MONTHS


def quarterly_tickets(qty: pd.Series, value: pd.Series, min_qty: float) -> pd.Series:
    """qty/value indexed by quarter (1..4) -> ticket per valid quarter (NaN when below min_qty)."""
    t = value / qty
    return t.where(qty >= min_qty)


def base_ticket(fc_quarterly: pd.DataFrame, min_qty: float) -> pd.Series:
    """Mean of valid quarterly tickets per region; regions without a valid quarter use the tool total.

    fc_quarterly: columns region, quarter, qty_executed, value_executed.
    """

    def mean_valid(df: pd.DataFrame) -> float:
        tk = quarterly_tickets(df["qty_executed"], df["value_executed"], min_qty)
        return float(tk.mean()) if tk.notna().any() else np.nan

    per_region = fc_quarterly.groupby("region")[["quarter", "qty_executed", "value_executed"]].apply(mean_valid)
    total_q = fc_quarterly.groupby("quarter")[["qty_executed", "value_executed"]].sum()
    total = mean_valid(total_q)
    if np.isnan(total):
        q, v = total_q["qty_executed"].sum(), total_q["value_executed"].sum()
        total = v / q if q else np.nan
    return per_region.fillna(total)


def monthly_ticket(base: pd.Series, market_growth: Sequence[float], factor: float = 1.0) -> pd.DataFrame:
    growth = 1 + np.asarray(market_growth, dtype=float)
    return pd.DataFrame(np.outer(base.to_numpy(dtype=float), growth) * factor, index=base.index, columns=MONTHS)


def adjustment_factor(
    base: pd.Series, monthly_qty: pd.DataFrame, market_growth: Sequence[float], target: float | None
) -> tuple[float, float]:
    """Return (factor, unadjusted average ticket). The factor keeps the monthly shape and hits the target."""
    tk = monthly_ticket(base.reindex(monthly_qty.index), market_growth)
    qty = monthly_qty.to_numpy().sum()
    unadjusted = float((tk * monthly_qty).to_numpy().sum() / qty) if qty else float("nan")
    if not target:
        return 1.0, unadjusted
    return float(target) / unadjusted, unadjusted
