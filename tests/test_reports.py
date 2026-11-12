"""Reports: the files are written, complete and consistent with the plan."""

import json
import re

import openpyxl
import pytest

from collection_plan.cli import main
from collection_plan.report_excel import write_excel
from collection_plan.report_html import PLACEHOLDER, write_html
from collection_plan.workforce import calendar_table, size_workforce

SHEETS = [
    "Summary",
    "Assumptions",
    "Market_Seasonality",
    "Regional_Split",
    "Ticket",
    "Productivity",
    "Efficiency",
    "Plan_by_Region",
    "Plan_Monthly",
    "Workforce_Group",
    "Workforce_Region",
]


@pytest.fixture(scope="module")
def workforce(result, cfg):
    return size_workforce(result.monthly, cfg.workforce, cfg.plan_year)


def test_excel_has_every_sheet_and_matching_total(result, workforce, tmp_path):
    path = write_excel(result, tmp_path / "plan.xlsx", workforce)
    wb = openpyxl.load_workbook(path)
    assert wb.sheetnames == SHEETS
    ws = wb["Summary"]
    header = [c.value for c in ws[1]]
    total_row = next(r for r in ws.iter_rows(min_row=2, values_only=True) if r[0] == "TOTAL")
    paid = total_row[header.index("value_paid_plan")]
    assert paid == pytest.approx(result.monthly["value_paid"].sum())
    assert ws.cell(2, header.index("eff_value_plan") + 1).number_format == "0.0%"


def test_html_is_self_contained_and_carries_the_plan(result, workforce, cfg, tmp_path):
    path = write_html(result, tmp_path / "plan.html", workforce, calendar_table(cfg.plan_year, cfg.workforce))
    html = path.read_text(encoding="utf-8")
    assert PLACEHOLDER not in html
    assert "<script src=" not in html and "<link " not in html  # works offline
    data = json.loads(re.search(r"const D = (\{.*?\});\n", html, re.S).group(1))
    assert [t["name"] for t in data["tools"]] == [t.name for t in cfg.tools]
    paid = sum(sum(r["value_paid"]) for t in data["plan"].values() for r in t.values())
    assert paid == pytest.approx(result.monthly["value_paid"].sum(), rel=1e-6)


def test_cli_end_to_end(tmp_path, monkeypatch):
    root = __import__("pathlib").Path(__file__).resolve().parents[1]
    data = tmp_path / "history.csv"
    main(["generate-data", "--out", str(data)])
    main(
        [
            "run",
            "--config",
            str(root / "config" / "assumptions.yaml"),
            "--data",
            str(data),
            "--out",
            str(tmp_path / "out"),
        ]
    )
    files = {p.name for p in (tmp_path / "out").iterdir()}
    assert {
        "plan_monthly.csv",
        "plan_summary.csv",
        "plan_report.xlsx",
        "plan_report.html",
        "workforce_by_group.csv",
        "workforce_by_region.csv",
    } <= files
