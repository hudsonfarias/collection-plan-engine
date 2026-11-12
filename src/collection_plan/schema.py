"""Column names and allowed values shared by every module."""

from __future__ import annotations

import pandas as pd

REGIONS = ["Capital", "North", "South", "East", "West"]
BASES = ("target", "actual")
STAGES = ("selected", "executed", "paid")
HISTORY_COLUMNS = ["base", "month", "region", "tool", "stage", "qty", "value"]

# Indicators of the plan, in the order they are built
VOLUME_COLS = ["qty_executed", "value_executed", "qty_selected", "value_selected", "qty_paid", "value_paid"]
RATIO_COLS = ["ticket", "prod_qty", "prod_value", "eff_qty", "eff_value"]


def validate_history(df: pd.DataFrame) -> pd.DataFrame:
    """Check the history base and return a clean copy (month as Timestamp, no negatives)."""
    missing = set(HISTORY_COLUMNS) - set(df.columns)
    if missing:
        raise ValueError(f"history base is missing columns: {sorted(missing)}")
    out = df[HISTORY_COLUMNS].copy()
    out["month"] = pd.to_datetime(out["month"])
    bad_base = set(out["base"]) - set(BASES)
    bad_stage = set(out["stage"]) - set(STAGES)
    if bad_base or bad_stage:
        raise ValueError(f"unknown values: base={bad_base or '-'} stage={bad_stage or '-'}")
    if (out[["qty", "value"]] < 0).any().any():
        raise ValueError("qty and value must be non-negative")
    return out


def add_ratios(df: pd.DataFrame) -> pd.DataFrame:
    """Add ticket, productivity and efficiency columns from the volume columns (0 when undefined)."""
    out = df.copy()

    def div(a, b):
        return (out[a] / out[b]).where(out[b] > 0, 0.0)

    out["ticket"] = div("value_executed", "qty_executed")
    out["prod_qty"] = div("qty_executed", "qty_selected")
    out["prod_value"] = div("value_executed", "value_selected")
    out["eff_qty"] = div("qty_paid", "qty_executed")
    out["eff_value"] = div("value_paid", "value_executed")
    return out
