"""Typed view of config/assumptions.yaml."""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field
from pathlib import Path

import yaml


@dataclass(frozen=True)
class ToolConfig:
    name: str
    group: str
    volume: float
    gains: dict[str, float] = field(default_factory=dict)
    ticket_target: float | None = None
    reference: str | None = None
    allocation_from: str | None = None
    excluded_regions: tuple[str, ...] = ()
    efficiency_reducer: float = 0.0
    fixed_efficiency: dict[str, float] | None = None
    efficiency_overrides: dict[str, dict[str, float]] = field(default_factory=dict)

    @property
    def is_new(self) -> bool:
        """New tools have no history and borrow it from a reference tool."""
        return self.reference is not None

    def gain(self, key: str) -> float:
        return float(self.gains.get(key, 0.0))


@dataclass(frozen=True)
class Calendar:
    weekdays: tuple[int, ...]
    saturday_weight: float = 0.0
    exclude_holiday_eves: bool = False


@dataclass(frozen=True)
class ExtraVolume:
    name: str
    annual: float
    calendar: str
    shape_from: str


@dataclass(frozen=True)
class WorkforceGroup:
    name: str
    actions_per_day: float
    tools: dict[str, str]  # tool -> calendar name
    extra_volumes: tuple[ExtraVolume, ...] = ()


@dataclass(frozen=True)
class WorkforceConfig:
    calendars: dict[str, Calendar]
    groups: tuple[WorkforceGroup, ...]
    holidays: tuple[dt.date, ...]


@dataclass(frozen=True)
class PlanConfig:
    plan_year: int
    history_year: int
    last_actual_month: int
    gap_weight: float
    min_gain: float
    max_gain: float
    productivity_cap: float
    efficiency_cap: float
    min_quarter_qty: float
    productivity_floor: bool
    prioritize_large_debts: bool
    market_growth: tuple[float, ...]
    seasonality: dict[str, tuple[float, ...]]
    tools: tuple[ToolConfig, ...]
    workforce: WorkforceConfig | None = None

    def tool(self, name: str) -> ToolConfig:
        for t in self.tools:
            if t.name == name:
                return t
        raise KeyError(name)

    def validate(self) -> None:
        names = [t.name for t in self.tools]
        if len(names) != len(set(names)):
            raise ValueError("tool names must be unique")
        if len(self.market_growth) != 12:
            raise ValueError("market_growth needs 12 values")
        for t in self.tools:
            if t.group not in self.seasonality:
                raise ValueError(f"{t.name}: no seasonality for group '{t.group}'")
            for ref in (t.reference, t.allocation_from):
                if ref and ref not in names:
                    raise ValueError(f"{t.name}: unknown tool '{ref}'")
            for k, g in t.gains.items():
                if not (self.min_gain <= g <= self.max_gain):
                    raise ValueError(f"{t.name}: gain {k}={g} outside [{self.min_gain}, {self.max_gain}]")
        for name, curve in self.seasonality.items():
            if len(curve) != 12 or sum(curve) <= 0:
                raise ValueError(f"seasonality '{name}' needs 12 positive values")


def load_config(path: str | Path) -> PlanConfig:
    raw = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    tools = tuple(
        ToolConfig(
            name=t["name"],
            group=t["group"],
            volume=float(t["volume"]),
            gains=t.get("gains", {}),
            ticket_target=t.get("ticket_target"),
            reference=t.get("reference"),
            allocation_from=t.get("allocation_from"),
            excluded_regions=tuple(t.get("excluded_regions", [])),
            efficiency_reducer=float(t.get("efficiency_reducer", 0.0)),
            fixed_efficiency=t.get("fixed_efficiency"),
            efficiency_overrides=t.get("efficiency_overrides", {}),
        )
        for t in raw["tools"]
    )
    wf = None
    if "workforce" in raw:
        w = raw["workforce"]
        wf = WorkforceConfig(
            calendars={
                k: Calendar(
                    tuple(v["weekdays"]), float(v.get("saturday_weight", 0)), bool(v.get("exclude_holiday_eves", False))
                )
                for k, v in w["calendars"].items()
            },
            groups=tuple(
                WorkforceGroup(
                    g["name"],
                    float(g["actions_per_day"]),
                    dict(g["tools"]),
                    tuple(
                        ExtraVolume(e["name"], float(e["annual"]), e["calendar"], e["shape_from"])
                        for e in g.get("extra_volumes", [])
                    ),
                )
                for g in w["groups"]
            ),
            holidays=tuple(d if isinstance(d, dt.date) else dt.date.fromisoformat(str(d)) for d in w["holidays"]),
        )
    cfg = PlanConfig(
        plan_year=int(raw["plan_year"]),
        history_year=int(raw["history_year"]),
        last_actual_month=int(raw["last_actual_month"]),
        gap_weight=float(raw["allocation"]["gap_weight"]),
        min_gain=float(raw["limits"]["min_gain"]),
        max_gain=float(raw["limits"]["max_gain"]),
        productivity_cap=float(raw["limits"]["productivity_cap"]),
        efficiency_cap=float(raw["limits"]["efficiency_cap"]),
        min_quarter_qty=float(raw["ticket"]["min_quarter_qty"]),
        productivity_floor=bool(raw["rules"]["productivity_floor"]),
        prioritize_large_debts=bool(raw["rules"]["prioritize_large_debts"]),
        market_growth=tuple(float(x) for x in raw["market_growth"]),
        seasonality={k: tuple(float(x) for x in v) for k, v in raw["seasonality"].items()},
        tools=tools,
        workforce=wf,
    )
    cfg.validate()
    return cfg
