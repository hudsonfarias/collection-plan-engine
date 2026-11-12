"""Command line: generate synthetic data and run the plan.

python -m collection_plan generate-data
python -m collection_plan run
"""

from __future__ import annotations

import argparse
import logging
from pathlib import Path

import pandas as pd

from .config import load_config
from .pipeline import run_plan
from .synthetic import generate_history
from .workforce import size_workforce

log = logging.getLogger("collection_plan")


def cmd_generate(args: argparse.Namespace) -> None:
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    df = generate_history(year=args.year, last_actual_month=args.last_actual_month, seed=args.seed)
    df.to_csv(out, index=False)
    log.info("synthetic history written to %s (%d rows)", out, len(df))


def cmd_run(args: argparse.Namespace) -> None:
    cfg = load_config(args.config)
    history = pd.read_csv(args.data, parse_dates=["month"])
    result = run_plan(history, cfg)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    result.monthly.to_csv(out / "plan_monthly.csv", index=False)
    summary = result.summary()
    summary.to_csv(out / "plan_summary.csv")
    if cfg.workforce:
        by_group, by_region = size_workforce(result.monthly, cfg.workforce, cfg.plan_year)
        by_group.to_csv(out / "workforce_by_group.csv", index=False)
        by_region.to_csv(out / "workforce_by_region.csv", index=False)

    view = pd.DataFrame(
        {
            "qty_plan": summary["qty_executed_plan"].map("{:,.0f}".format),
            "ticket_plan": summary["ticket_plan"].map("{:,.0f}".format),
            "eff_value_plan": summary["eff_value_plan"].map("{:.1%}".format),
            "paid_fc_MM": (summary["value_paid_fc"] / 1e6).map("{:,.1f}".format),
            "paid_plan_MM": (summary["value_paid_plan"] / 1e6).map("{:,.1f}".format),
            "delta": summary["value_paid_delta"].map(lambda x: "new" if pd.isna(x) else f"{x:+.1%}"),
        }
    )
    print(view.to_string())
    log.info("outputs written to %s", out.resolve())


def main(argv: list[str] | None = None) -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    p = argparse.ArgumentParser(
        prog="collection-plan", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    sub = p.add_subparsers(dest="command", required=True)

    g = sub.add_parser("generate-data", help="write a synthetic history base")
    g.add_argument("--out", default="data/raw/history.csv")
    g.add_argument("--year", type=int, default=2026)
    g.add_argument("--last-actual-month", type=int, default=10)
    g.add_argument("--seed", type=int, default=42)
    g.set_defaults(func=cmd_generate)

    r = sub.add_parser("run", help="build the plan from a history base and the assumptions file")
    r.add_argument("--config", default="config/assumptions.yaml")
    r.add_argument("--data", default="data/raw/history.csv")
    r.add_argument("--out", default="outputs")
    r.set_defaults(func=cmd_run)

    args = p.parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()
