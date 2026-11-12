"""Step 0: history-year forecast = actuals up to the cut-off month + targets for the remaining months."""

from __future__ import annotations

import pandas as pd

from .schema import VOLUME_COLS, add_ratios

KEYS = ["tool", "region", "month"]


def to_wide(long: pd.DataFrame) -> pd.DataFrame:
    """Long (stage, qty, value) -> one row per base/tool/region/month with the six volume columns."""
    piv = long.pivot_table(
        index=["base", *KEYS], columns="stage", values=["qty", "value"], aggfunc="sum", fill_value=0.0
    )
    piv.columns = [f"{measure}_{stage}" for measure, stage in piv.columns]
    for col in VOLUME_COLS:
        if col not in piv.columns:
            piv[col] = 0.0
    return piv[VOLUME_COLS].reset_index()


def build_forecast(history: pd.DataFrame, last_actual_month: int) -> pd.DataFrame:
    """Return the wide forecast: actual rows for months <= cut-off, target rows afterwards."""
    wide = to_wide(history)
    month_no = wide["month"].dt.month
    keep = ((wide["base"] == "actual") & (month_no <= last_actual_month)) | (
        (wide["base"] == "target") & (month_no > last_actual_month)
    )
    fc = wide[keep].drop(columns="base")
    fc = fc.groupby(KEYS, as_index=False)[VOLUME_COLS].sum()
    fc.insert(0, "base", "forecast")
    return fc


def annual(wide: pd.DataFrame, by: list[str]) -> pd.DataFrame:
    """Sum the volume columns over the year and recompute the ratios (by=[] gives one total row)."""
    if not by:
        return add_ratios(wide[VOLUME_COLS].sum().to_frame().T)
    out = wide.groupby(by, as_index=False)[VOLUME_COLS].sum()
    return add_ratios(out)


def quarterly(wide: pd.DataFrame, by: list[str]) -> pd.DataFrame:
    """Sum by quarter (column 'quarter' = 1..4) and recompute the ratios."""
    w = wide.assign(quarter=wide["month"].dt.quarter)
    out = w.groupby([*by, "quarter"], as_index=False)[VOLUME_COLS].sum()
    return add_ratios(out)
