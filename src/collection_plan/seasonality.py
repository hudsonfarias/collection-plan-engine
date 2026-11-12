"""Step 3: spread the annual volume over the months with the group's seasonality curve."""

from __future__ import annotations

from collections.abc import Sequence

import numpy as np
import pandas as pd

MONTHS = list(range(1, 13))


def normalize(curve: Sequence[float]) -> np.ndarray:
    """Scale a 12-month curve so it sums to exactly 1 (official curves often sum to 100.005%)."""
    arr = np.asarray(curve, dtype=float)
    if arr.shape != (12,) or (arr < 0).any() or arr.sum() <= 0:
        raise ValueError("seasonality needs 12 non-negative values with a positive sum")
    return arr / arr.sum()


def spread(annual_by_region: pd.Series, curve: Sequence[float]) -> pd.DataFrame:
    """Regions x months matrix whose rows sum back to the annual volume."""
    w = normalize(curve)
    data = np.outer(annual_by_region.to_numpy(dtype=float), w)
    return pd.DataFrame(data, index=annual_by_region.index, columns=MONTHS)
