from pathlib import Path

import pytest
from pydantic import ValidationError

from hoa_eval.scenario import ScenarioError, load_scenario, load_scenarios

VALID = """\
name: {name}
fault:
  patch: deploy/kind/faults/image-pull.yaml
  namespace: demo
  deployment: orders
wait:
  {wait}
alert: "orders rollout stuck"
expected:
  cause_label: {label}
  target: demo/orders
"""


def write(
    tmp_path: Path,
    *,
    name: str = "sample",
    wait: str = "min_restarts: 1",
    label: str = "image_pull_error",
) -> Path:
    path = tmp_path / "sample.yaml"
    path.write_text(VALID.format(name=name, wait=wait, label=label), encoding="utf-8")
    return path


def test_shipped_scenarios_load_with_their_fault_targets() -> None:
    scenarios = {s.name: s for s in load_scenarios()}

    assert set(scenarios) == {"image-pull", "bad-config"}
    assert scenarios["image-pull"].fault.deployment == "orders"
    assert scenarios["bad-config"].expected.cause_label == "bad_config"


def test_scenarios_can_be_picked_by_name() -> None:
    assert [s.name for s in load_scenarios(["bad-config"])] == ["bad-config"]


def test_unknown_scenario_name_lists_what_exists() -> None:
    with pytest.raises(ScenarioError, match="have bad-config, image-pull"):
        load_scenarios(["oom"])


def test_wait_needs_at_least_one_condition(tmp_path: Path) -> None:
    with pytest.raises(ValidationError, match="waiting_reasons or min_restarts"):
        load_scenario(write(tmp_path, wait="timeout_seconds: 60"))


def test_expected_label_must_be_one_the_agent_can_answer(tmp_path: Path) -> None:
    with pytest.raises(ValidationError):
        load_scenario(write(tmp_path, label="network_partition"))


def test_name_must_match_the_file(tmp_path: Path) -> None:
    with pytest.raises(ScenarioError, match="must match the file name"):
        load_scenario(write(tmp_path, name="other"))
