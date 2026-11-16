from collections.abc import Sequence
from pathlib import Path
from typing import Literal, Self

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator

REPO_ROOT = Path(__file__).resolve().parents[3]
SCENARIO_DIR = REPO_ROOT / "eval" / "scenarios"

# hoa_agent.diagnosis.CauseLabel의 값 — 멤버 경계 때문에 import하지 않고 옮겨 둔다
CauseLabel = Literal[
    "image_pull_error",
    "bad_config",
    "oom_killed",
    "probe_failure",
    "service_selector_mismatch",
    "downstream_unavailable",
    "unknown",
]


class ScenarioError(Exception):
    pass


class Fault(BaseModel):
    model_config = ConfigDict(extra="forbid")

    patch: Path
    namespace: str
    deployment: str


class Symptom(BaseModel):
    model_config = ConfigDict(extra="forbid")

    waiting_reasons: list[str] = Field(default_factory=list)
    min_restarts: int | None = Field(default=None, ge=1)
    timeout_seconds: int = Field(default=120, gt=0)

    @model_validator(mode="after")
    def needs_a_condition(self) -> Self:
        if not self.waiting_reasons and self.min_restarts is None:
            raise ValueError("wait needs waiting_reasons or min_restarts")
        return self


class Expected(BaseModel):
    model_config = ConfigDict(extra="forbid")

    cause_label: CauseLabel
    target: str


class Scenario(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    fault: Fault
    wait: Symptom
    alert: str
    expected: Expected


def load_scenario(path: Path) -> Scenario:
    scenario = Scenario.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")))
    if scenario.name != path.stem:
        raise ScenarioError(f"{path.name}: name must match the file name, got {scenario.name}")
    if not (REPO_ROOT / scenario.fault.patch).is_file():
        raise ScenarioError(f"{path.name}: patch file not found: {scenario.fault.patch}")
    return scenario


def load_scenarios(names: Sequence[str] = (), directory: Path = SCENARIO_DIR) -> list[Scenario]:
    paths = sorted(directory.glob("*.yaml"))
    available = {path.stem: path for path in paths}
    unknown = [name for name in names if name not in available]
    if unknown:
        raise ScenarioError(
            f"unknown scenario: {', '.join(unknown)} (have {', '.join(available) or 'none'})"
        )
    chosen = [available[name] for name in names] if names else paths
    return [load_scenario(path) for path in chosen]
