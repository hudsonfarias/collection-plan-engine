# Design decisions

Short records of the choices that shape the engine (lightweight ADRs).

## 1. Plan volumes, recompute ratios

**Decision.** Every step produces volumes (qty and value); ticket, productivity and efficiency are
always recomputed from volumes.
**Why.** Averaging ratios gives wrong totals (a 90% region and a 50% region do not average to 70% if
their volumes differ). Recomputing keeps any aggregation (tool, region, quarter, year) consistent.

## 2. One YAML file for every assumption

**Decision.** No business number lives in the code. Gains, curves, targets, overrides, calendars and
holidays are in `config/assumptions.yaml`, validated on load.
**Why.** The plan is negotiated: assumptions change in meetings. Changing a number should not need a
code change, and the validation stops out-of-range values (e.g. a gain outside 0.5-2 p.p.).

## 3. Keep intermediate results

**Decision.** `run_plan` returns a `PlanResult` with, per tool, the regional split, base ticket,
adjustment factor, productivity before/after each rule and the efficiency table.
**Why.** A plan has to be defended. Showing *how* a number was reached matters as much as the number.

## 4. Floor rule acts only on regions that received extra volume

**Decision.** When the consolidated productivity falls below the forecast, only the regions whose share
grew get the extra gain.
**Why.** The drop is caused by moving volume to them; regions that kept their share are not asked for
more than the standard gain.

## 5. New tools borrow, they do not guess

**Decision.** A tool without history declares a `reference` (ticket, productivity, efficiency) and,
optionally, `allocation_from` (regional split) and a reducer or fixed efficiency.
**Why.** Every number keeps a traceable origin, and the assumption is explicit and easy to revise after
the first quarter of real data.

## 6. HTML report without dependencies

**Decision.** The interactive report is one HTML file: the template ships with the package, the data is
embedded as JSON and the charts are drawn as inline SVG by a small script.
**Why.** Business users open it from an e-mail or a shared folder, often offline and behind a corporate
proxy. No server, no CDN and no build step means it always opens.

## 7. Synthetic data with a fixed seed

**Decision.** `generate_history(seed=42)` builds the example base; the real base is never versioned.
**Why.** The repository must be public and reproducible without exposing any real data.
