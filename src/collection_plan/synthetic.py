"""Synthetic history generator.

Builds a fictional history-year base (targets for 12 months, actuals for the first months)
with the same shape as a real collection-operations extract. Seeded, so it is reproducible.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from .schema import BASES, REGIONS, STAGES

# tool -> (annual target qty, executed ticket, prod_qty, prod_value, eff_qty, eff_value, first target month)
TOOL_PROFILE = {
    "field_disconnection": (51_000, 1_700, 0.70, 0.78, 0.73, 0.39, 1),
    "re_disconnection": (14_400, 9_600, 0.16, 0.19, 0.18, 0.032, 1),
    "special_notice": (133_000, 575, 0.95, 0.95, 0.65, 0.46, 1),
    "remote_disconnection": (14_500, 920, 0.70, 0.70, 0.83, 0.58, 4),
    "field_visit": (55_500, 1_200, 0.85, 0.84, 0.60, 0.28, 1),
}

# how actuals behave against targets: (volume factor, ticket factor, prod_q, prod_v, eff_q, eff_v)
ACTUAL_PROFILE = {
    "field_disconnection": (1.09, 0.97, 0.47, 0.40, 0.85, 0.48),
    "re_disconnection": (0.80, 1.05, 0.19, 0.26, 0.23, 0.025),
    "special_notice": (1.05, 1.48, 0.975, 0.966, 0.60, 0.561),
    "remote_disconnection": (0.86, 0.98, 0.56, 0.50, 0.886, 0.64),
    "field_visit": (1.18, 1.08, 0.92, 0.95, 0.49, 0.23),
}

# regional split of targets (share) and actual delivery vs target (adherence)
REGION_SHARE = {
    "field_disconnection": [0.70, 0.09, 0.05, 0.08, 0.08],
    "re_disconnection": [0.87, 0.04, 0.03, 0.03, 0.03],
    "special_notice": [0.92, 0.035, 0.02, 0.015, 0.01],
    "remote_disconnection": [1.0, 0.0, 0.0, 0.0, 0.0],
    "field_visit": [0.86, 0.075, 0.02, 0.03, 0.015],
}
REGION_ADHERENCE = {
    "field_disconnection": [1.03, 1.25, 1.18, 1.16, 1.30],
    "re_disconnection": [0.78, 1.20, 0.90, 0.77, 0.79],
    "special_notice": [1.08, 0.80, 0.17, 1.10, 0.47],
    "remote_disconnection": [0.86, 0, 0, 0, 0],
    "field_visit": [1.22, 1.16, 0.63, 0.77, 0.45],
}
# monthly ramp of actuals (remote_disconnection only "switched on" mid-year)
RAMP = {"remote_disconnection": [0.0, 0.0, 0.0, 0.02, 0.07, 0.12, 0.75, 1.15, 1.12, 1.1, 1.0, 1.0]}
SEASON = np.array([0.080, 0.068, 0.088, 0.084, 0.080, 0.088, 0.088, 0.088, 0.084, 0.080, 0.080, 0.092])


def generate_history(year: int = 2026, last_actual_month: int = 10, seed: int = 42) -> pd.DataFrame:
    """Return the long-format history base: base, month, region, tool, stage, qty, value."""
    rng = np.random.default_rng(seed)
    season = SEASON / SEASON.sum()
    rows = []
    for tool, (annual, ticket, pq, pv, eq, ev, first_month) in TOOL_PROFILE.items():
        a_vol, a_tk, a_pq, a_pv, a_eq, a_ev = ACTUAL_PROFILE[tool]
        months = np.arange(1, 13)
        active = (months >= first_month).astype(float)
        t_season = season * active / (season * active).sum()
        for r_idx, region in enumerate(REGIONS):
            share = REGION_SHARE[tool][r_idx]
            if share == 0:
                continue
            adherence = REGION_ADHERENCE[tool][r_idx]
            for m in months:
                base_qty = annual * share * t_season[m - 1]
                # targets: smooth, no noise
                _append(rows, "target", year, m, region, tool, base_qty, ticket, pq, pv, eq, ev)
                if m <= last_actual_month:
                    ramp = RAMP.get(tool, [1.0] * 12)[m - 1]
                    qty = annual * share * season[m - 1] * a_vol * adherence * ramp * rng.normal(1, 0.06)
                    tk = ticket * a_tk * rng.normal(1, 0.08)
                    _append(
                        rows,
                        "actual",
                        year,
                        m,
                        region,
                        tool,
                        max(qty, 0),
                        tk,
                        min(1, a_pq * rng.normal(1, 0.04)),
                        min(1, a_pv * rng.normal(1, 0.05)),
                        min(1, a_eq * rng.normal(1, 0.03)),
                        min(1, a_ev * rng.normal(1, 0.06)),
                    )
    df = pd.DataFrame(rows)
    df["qty"] = df["qty"].round(0)
    df["value"] = df["value"].round(2)
    df = df[df["qty"] > 0].reset_index(drop=True)
    assert set(df["base"]) <= set(BASES) and set(df["stage"]) <= set(STAGES)
    return df


def _append(rows, base, year, month, region, tool, qty_exec, ticket, pq, pv, eq, ev):
    value_exec = qty_exec * ticket
    date = pd.Timestamp(year=year, month=int(month), day=1)
    for stage, qty, value in (
        ("selected", qty_exec / pq, value_exec / pv),
        ("executed", qty_exec, value_exec),
        ("paid", qty_exec * eq, value_exec * ev),
    ):
        rows.append(
            {"base": base, "month": date, "region": region, "tool": tool, "stage": stage, "qty": qty, "value": value}
        )
