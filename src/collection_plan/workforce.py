"""Step 7: field workforce sizing.

agents(month) = volume of the month / (business days of the month x productive actions per day),
rounded up. Each tool runs on its own calendar (e.g. some actions only Mon-Thu, never on a holiday
or the day before one). Regions are sized separately because agents do not move between regions.
"""

from __future__ import annotations

import calendar as _cal
import datetime as dt
import math
from collections.abc import Iterable

import pandas as pd

from .config import Calendar, WorkforceConfig
from .seasonality import MONTHS


def business_days(year: int, month: int, cal: Calendar, holidays: Iterable[dt.date]) -> float:
    hol = set(holidays)
    eves = {h - dt.timedelta(days=1) for h in hol} if cal.exclude_holiday_eves else set()
    days = 0.0
    for d in range(1, _cal.monthrange(year, month)[1] + 1):
        day = dt.date(year, month, d)
        if day in hol or day in eves:
            continue
        if day.weekday() in cal.weekdays:
            days += 1
        elif day.weekday() == 5:
            days += cal.saturday_weight
    return days


def calendar_table(year: int, wf: WorkforceConfig) -> pd.DataFrame:
    """Business days per calendar (rows) and month (columns)."""
    return pd.DataFrame(
        {name: [business_days(year, m, c, wf.holidays) for m in MONTHS] for name, c in wf.calendars.items()},
        index=MONTHS,
    ).T


def size_workforce(monthly_plan: pd.DataFrame, wf: WorkforceConfig, year: int) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Return (by_group, by_region).

    by_group : group, month, volume, agents_exact, agents
    by_region: group, region, month, agents_exact, agents
    """
    days = calendar_table(year, wf)
    plan = monthly_plan.assign(m=monthly_plan["month"].dt.month)
    vol = plan.pivot_table(index=["tool", "region"], columns="m", values="qty_executed", aggfunc="sum", fill_value=0.0)

    group_rows, region_rows = [], []
    for g in wf.groups:
        # work items: (label, calendar, region x month volume)
        items = []
        for tool, cal_name in g.tools.items():
            if tool not in vol.index.get_level_values(0):
                raise KeyError(f"workforce group '{g.name}': tool '{tool}' not in the plan")
            items.append((tool, cal_name, vol.loc[tool]))
        for extra in g.extra_volumes:
            shape = vol.loc[extra.shape_from]
            items.append((extra.name, extra.calendar, shape / shape.to_numpy().sum() * extra.annual))
        regions = sorted({r for _, _, v in items for r in v.index})
        exact_region = pd.DataFrame(0.0, index=regions, columns=MONTHS)
        for _, cal_name, v in items:
            exact_region = exact_region.add(
                v.reindex(regions, fill_value=0.0) / (days.loc[cal_name] * g.actions_per_day), fill_value=0.0
            )
        exact_total = exact_region.sum()
        volume_total = sum(v.to_numpy().sum(axis=0) for _, _, v in items)
        for m in MONTHS:
            group_rows.append(
                {
                    "group": g.name,
                    "month": m,
                    "volume": float(volume_total[m - 1]),
                    "agents_exact": float(exact_total[m]),
                    "agents": math.ceil(exact_total[m] - 1e-9),
                }
            )
            for r in regions:
                x = float(exact_region.loc[r, m])
                region_rows.append(
                    {"group": g.name, "region": r, "month": m, "agents_exact": x, "agents": math.ceil(x - 1e-9)}
                )
    return pd.DataFrame(group_rows), pd.DataFrame(region_rows)
