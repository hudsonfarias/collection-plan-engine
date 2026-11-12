"""Collection plan engine: builds an annual debt-collection plan from history and assumptions."""

from .config import PlanConfig, load_config
from .pipeline import PlanResult, run_plan

__all__ = ["PlanConfig", "PlanResult", "load_config", "run_plan"]
__version__ = "0.1.0"
