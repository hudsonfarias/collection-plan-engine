"""Step 2: split a tool's annual volume across regions ("contribution degree").

Rule: start from each region's share of the history-year target. A region that delivered below
target receives extra weight = share x (1 + gap_weight x gap), gap = 1 - forecast / target.
Regions at or above target get no extra pressure. Weights are normalised to sum to 100%.
A region with no target keeps no target. Excluded regions get zero.
"""

from __future__ import annotations

from collections.abc import Iterable

import pandas as pd


def regional_shares(
    target: pd.Series,
    forecast: pd.Series,
    gap_weight: float,
    excluded: Iterable[str] = (),
    regions: Iterable[str] | None = None,
) -> pd.DataFrame:
    """Return a frame indexed by region with target, forecast, adherence, gap, base_share, weight, share."""
    idx = pd.Index(regions if regions is not None else target.index.union(forecast.index), name="region")
    t = target.reindex(idx, fill_value=0.0).astype(float)
    f = forecast.reindex(idx, fill_value=0.0).astype(float)

    adherence = (f / t).where(t > 0, 0.0)
    gap = (1 - adherence).clip(lower=0).where(t > 0, 0.0)
    if t.sum() > 0:
        base_share = t / t.sum()
    elif f.sum() > 0:  # no target at all: fall back to the forecast split
        base_share = f / f.sum()
    else:
        raise ValueError("cannot allocate: no target and no forecast volume")

    weight = base_share * (1 + gap_weight * gap)
    weight[weight.index.isin(list(excluded))] = 0.0
    if weight.sum() <= 0:
        raise ValueError("cannot allocate: every region with volume is excluded")
    share = weight / weight.sum()
    return pd.DataFrame(
        {
            "target": t,
            "forecast": f,
            "adherence": adherence,
            "gap": gap,
            "base_share": base_share,
            "weight": weight,
            "share": share,
        }
    )
