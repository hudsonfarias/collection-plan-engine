import dataclasses
import datetime as dt
import math

import pytest

from collection_plan.config import Calendar
from collection_plan.workforce import business_days, size_workforce

HOL = [dt.date(2027, 1, 1), dt.date(2027, 2, 8), dt.date(2027, 2, 9), dt.date(2027, 10, 12)]
STANDARD = Calendar(weekdays=(0, 1, 2, 3, 4), saturday_weight=0.5)
RESTRICTED = Calendar(weekdays=(0, 1, 2, 3), exclude_holiday_eves=True)


def test_standard_calendar_counts_half_saturdays():
    # Jan 2027: 21 weekdays - 1 holiday + 5 Saturdays x 0.5
    assert business_days(2027, 1, STANDARD, HOL) == 22.5


def test_restricted_calendar_drops_holidays_and_their_eves():
    # Feb 2027: 16 Mon-Thu days, minus Carnival Mon/Tue (the Monday is also the Tuesday's eve)
    assert business_days(2027, 2, RESTRICTED, HOL) == 14
    # Oct 2027: 16 Mon-Thu days, minus Tue 12 (holiday) and Mon 11 (eve)
    assert business_days(2027, 10, RESTRICTED, HOL) == 14


def test_agents_are_rounded_up_and_regions_sum_at_least_the_total(result, cfg):
    by_group, by_region = size_workforce(result.monthly, cfg.workforce, cfg.plan_year)
    assert (by_group["agents"] == by_group["agents_exact"].map(lambda x: math.ceil(x - 1e-9))).all()
    reg = by_region.groupby(["group", "month"])["agents"].sum()
    tot = by_group.set_index(["group", "month"])["agents"].reindex(reg.index)
    assert (reg >= tot).all()


def test_config_rejects_gain_outside_the_allowed_range(cfg):
    bad_tool = dataclasses.replace(cfg.tools[0], gains={"prod_qty": 0.05})
    bad = dataclasses.replace(cfg, tools=(bad_tool, *cfg.tools[1:]))
    with pytest.raises(ValueError):
        bad.validate()
