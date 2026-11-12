"""Step 6: efficiency (paid / executed), which turns execution into collected cash.

plan = forecast + gain, capped. Overrides fix a region's value (e.g. a contracted target).
"""

from __future__ import annotations

import pandas as pd


def plan_efficiency(
    fc_eff: pd.DataFrame,
    gain_qty: float,
    gain_value: float,
    cap: float,
    overrides: dict[str, dict[str, float]] | None = None,
) -> pd.DataFrame:
    """fc_eff: region -> eff_qty, eff_value (forecast). Returns region -> eff_qty, eff_value."""
    out = pd.DataFrame(
        {
            "eff_qty": (fc_eff["eff_qty"] + gain_qty).clip(upper=cap),
            "eff_value": (fc_eff["eff_value"] + gain_value).clip(upper=cap),
        }
    )
    for region, values in (overrides or {}).items():
        for col, v in values.items():
            if col not in out.columns:
                raise KeyError(f"unknown efficiency column '{col}'")
            out.loc[region, col] = min(cap, float(v))
    return out


def borrowed_efficiency(
    regions: pd.Index, reference_qty: float, reference_value: float, reducer: float
) -> pd.DataFrame:
    """New tool: the reference tool's consolidated plan efficiency x (1 - reducer), same in every region."""
    return pd.DataFrame(
        {"eff_qty": reference_qty * (1 - reducer), "eff_value": reference_value * (1 - reducer)}, index=regions
    )
