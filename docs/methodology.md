# Methodology

This document explains how the plan is built, step by step, and why each rule exists.
Notation: *history year* = the year with targets and actuals (2026 in the example); *plan year* = the
year being planned (2027).

## Indicators

| Indicator | Formula | Reading |
|---|---|---|
| Executed qty / value | actions carried out in the field and the debt they covered | volume |
| Selected qty / value | customers/debt sent to the field | how much must be selected |
| Paid qty / value | customers/debt paid after the action | collected cash |
| Ticket | executed value / executed qty | average debt per action |
| Productivity (qty, value) | executed / selected | out of 100 selected, how many were executed |
| Efficiency (qty, value) | paid / executed | how much of the executed debt came back as cash |

Ratios are never planned directly from other ratios: the engine plans volumes and recomputes ratios
from volumes, so totals and averages are always consistent.

## 0. Forecast of the history year

`forecast = actuals for months <= cut-off + targets for the remaining months`

The forecast, and not the target, is the base for the plan: the plan starts from what the operation
actually delivers. With a cut-off in October, the last quarter mixes October actuals with
November/December targets. Comparing the plan with raw actuals would make Q4 look artificially low.

## 1. Volume

The annual executed volume per tool comes from the corporate volume file (`tools[].volume`). The engine
does not change it: everything else is built so the plan adds back exactly to this number (tested).

## 2. Regional split ("contribution degree")

1. `base_share` = region's share of the history-year **target**.
2. `gap = max(0, 1 - forecast / target)`: how far below target the region finished.
3. `weight = base_share x (1 + gap_weight x gap)`.
4. `share = weight / sum(weight)`.

Why:

* Regions that delivered below target get *a little* more volume (they have room to recover), but
  only a fraction of the gap (`gap_weight = 25%`), so the plan stays credible.
* Regions above target get **no extra pressure**: delivering is not punished.
* A region with no target in the history year keeps no target: the plan does not invent operations.
* `excluded_regions` removes a region by agreement (e.g. a new tool that must not compete with an
  existing one there); the others are renormalised.

New tools can take the split from another tool (`allocation_from`).

## 3. Seasonality

`monthly qty = annual qty x normalised curve(month)`

Curves are per tool group (field disconnections peak mid-year; soft-collection actions peak in
December). Official curves often sum to 100.005%, so the engine normalises them, which keeps the
annual total exact.

## 4. Ticket

1. Quarterly executed tickets of the forecast; quarters with fewer than `min_quarter_qty` executions are
   ignored (a tool that started late would otherwise contribute a meaningless ticket).
2. `base = mean of the valid quarterly tickets`, per region (regions without history use the tool total).
3. `ticket(month) = base x (1 + market_growth(month)) x factor`.
4. `factor = ticket_target / unadjusted average ticket` when a target exists, else 1.

Why the quarterly mean: a single month or the annual ratio is dominated by one strong or weak period;
the mean of quarters smooths peaks and valleys. Why market growth: the volume is almost flat over the
year, but the average debt grows with tariffs and consumption, so the value grows in the second half.
Why a factor (and not a fixed ticket): it keeps the monthly shape and regional differences while
hitting the agreed average. Used when the volume jump changes the debt profile (much more volume
reaches customers with smaller debts).

## 5. Productivity and selected volume

`plan productivity = min(cap, forecast + gain)` per region, with the gain limited to 0.5-2 p.p.

**Floor rule.** Sending volume to regions with lower productivity reduces the tool's consolidated
productivity even when every region improves (composition effect). If the consolidated value falls
below the forecast, the regions that received extra volume get one common extra gain:

```
factor = (total / floor - selected_without_extra) / selected_with_extra
prod(region with extra) = prod / factor
```

so the consolidated productivity equals the forecast exactly.

**Largest-debts-first rule.** `selected ticket = executed ticket x prod_qty / prod_value`. If value
productivity is below qty productivity, the plan selects larger debts than it executes, i.e. it leaves
the largest debts behind. The engine sets `prod_value >= prod_qty` in every region and then applies one
factor so that the rule also holds for the tool's consolidated ticket (regions with high tickets weigh
more in the selected value).

`selected = executed / productivity` (qty and value).

## 6. Efficiency and paid volume

`plan efficiency = min(cap, forecast + gain)`; `paid = executed x efficiency`.

Exceptions, all in the YAML:

* `efficiency_overrides`: a region with a contracted value (e.g. an agreement with the distributor).
* New tools: `efficiency = reference tool's consolidated plan efficiency x (1 - reducer)`, or a
  `fixed_efficiency` (e.g. a digital channel known to be less effective than field work).

## 7. Workforce

`agents(month) = sum over tools of volume(month) / (business days of the tool's calendar x actions/day)`

* Each team has a productivity (actions per agent per day).
* Each tool runs on a calendar: e.g. Mon-Fri plus half-day Saturdays, or Mon-Thu only, never on a
  holiday or the day before one.
* Extra work that is not in the plan (e.g. reconnections) can be added with the shape of another tool.
* Agents are rounded up per month. By region they are rounded up again, because agents do not move
  between regions, so the regional sum is higher than the consolidated need.
