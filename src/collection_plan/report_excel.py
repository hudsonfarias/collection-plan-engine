"""Excel report: one sheet per step, formatted, so the plan can be reviewed without Python."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.worksheet import Worksheet

from .forecast import annual
from .pipeline import PlanResult

HEADER_FILL = PatternFill("solid", fgColor="1F4E79")
HEADER_FONT = Font(color="FFFFFF", bold=True)
TOTAL_FILL = PatternFill("solid", fgColor="D9E1F2")

# first match wins: ratios before volumes ("prod_qty" is a percentage, "qty_executed" a count)
FORMATS = [
    ("delta", "+0.0%;-0.0%;0.0%"),
    ("factor", "0.0000"),
    ("reducer", "0%"),
    ("gain", "0.0%"),
    ("season", "0.00%"),
    ("prod", "0.0%"),
    ("eff", "0.0%"),
    ("share", "0.0%"),
    ("gap", "0.0%"),
    ("adherence", "0.0%"),
    ("growth", "0.0%"),
    ("weight", "0.0000"),
    ("ticket", "#,##0.00"),
    ("agents_exact", "0.00"),
    ("agents", "0"),
    ("qty", "#,##0"),
    ("value", "#,##0"),
    ("volume", "#,##0"),
    ("target", "#,##0"),
    ("forecast", "#,##0"),
]


def _fmt_for(col: str) -> str | None:
    c = col.lower()
    for key, fmt in FORMATS:
        if key in c:
            return fmt
    return None


def _style(ws: Worksheet, df: pd.DataFrame, total_label: str | None = "TOTAL") -> None:
    for cell in ws[1]:
        cell.fill, cell.font = HEADER_FILL, HEADER_FONT
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
    ws.row_dimensions[1].height = 30
    cols = list(df.columns)
    for j, col in enumerate(cols, start=1):
        fmt = _fmt_for(str(col))
        width = max(10, min(28, len(str(col)) + 2))
        ws.column_dimensions[get_column_letter(j)].width = width
        if fmt:
            for row in ws.iter_rows(min_row=2, min_col=j, max_col=j):
                row[0].number_format = fmt
    if total_label:
        for row in ws.iter_rows(min_row=2):
            if str(row[0].value) == total_label:
                for c in row:
                    c.fill, c.font = TOTAL_FILL, Font(bold=True)
    ws.freeze_panes = "B2"
    ws.auto_filter.ref = ws.dimensions


def _write(writer: pd.ExcelWriter, name: str, df: pd.DataFrame, total_label: str | None = "TOTAL") -> None:
    df.to_excel(writer, sheet_name=name, index=False)
    _style(writer.sheets[name], df, total_label)


def build_tables(
    result: PlanResult, workforce: tuple[pd.DataFrame, pd.DataFrame] | None = None
) -> dict[str, pd.DataFrame]:
    """All report tables, keyed by sheet name (also handy for notebooks)."""
    cfg = result.config
    tables: dict[str, pd.DataFrame] = {}

    s = result.summary().reset_index().rename(columns={"index": "tool"})
    tables["Summary"] = s

    rows = []
    for t in cfg.tools:
        rows.append(
            {
                "tool": t.name,
                "group": t.group,
                "volume": t.volume,
                "reference": t.reference or "",
                "allocation_from": t.allocation_from or "",
                "excluded_regions": ", ".join(t.excluded_regions),
                "ticket_target": t.ticket_target,
                "efficiency_reducer": t.efficiency_reducer or None,
                "fixed_efficiency": str(t.fixed_efficiency or ""),
                "overrides": str(t.efficiency_overrides or ""),
                **{f"gain_{k}": v for k, v in t.gains.items()},
            }
        )
    tables["Assumptions"] = pd.DataFrame(rows)
    tables["Market_Seasonality"] = pd.DataFrame(
        {"month": range(1, 13), "growth": cfg.market_growth}
        | {f"season_{g}": [v / sum(c) for v in c] for g, c in cfg.seasonality.items()}
    )

    split, ticket, prod, eff = [], [], [], []
    for name, tp in result.tools.items():
        split.append(tp.shares.reset_index().assign(tool=name, plan_qty=tp.shares["share"].values * tp.tool.volume))
        ticket.append(
            pd.DataFrame(
                {
                    "tool": name,
                    "region": tp.base_ticket.index,
                    "base_ticket": tp.base_ticket.values,
                    "adjustment_factor": tp.ticket_factor,
                }
            )
        )
        prod.append(
            tp.productivity.table.reset_index()
            .rename(columns={"index": "region"})
            .assign(
                tool=name,
                floor_factor_qty=tp.productivity.floor_factor_qty,
                floor_factor_value=tp.productivity.floor_factor_value,
                consolidated_factor=tp.productivity.consolidated_factor,
            )
        )
        eff.append(tp.efficiency.reset_index().rename(columns={"index": "region"}).assign(tool=name))

    def front(df: pd.DataFrame) -> pd.DataFrame:
        return df[["tool", *[c for c in df.columns if c != "tool"]]]

    tables["Regional_Split"] = front(pd.concat(split, ignore_index=True))
    tables["Ticket"] = front(pd.concat(ticket, ignore_index=True))
    tables["Productivity"] = front(pd.concat(prod, ignore_index=True))
    tables["Efficiency"] = front(pd.concat(eff, ignore_index=True))

    by_tr = annual(result.monthly, ["tool", "region"])
    tables["Plan_by_Region"] = by_tr
    m = result.monthly.copy()
    m["month"] = m["month"].dt.strftime("%Y-%m")
    tables["Plan_Monthly"] = m
    if workforce is not None:
        tables["Workforce_Group"] = workforce[0]
        tables["Workforce_Region"] = workforce[1]
    return tables


def write_excel(
    result: PlanResult, path: str | Path, workforce: tuple[pd.DataFrame, pd.DataFrame] | None = None
) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tables = build_tables(result, workforce)
    with pd.ExcelWriter(path, engine="openpyxl") as writer:
        for name, df in tables.items():
            _write(writer, name, df, total_label="TOTAL" if name == "Summary" else None)
    return path
