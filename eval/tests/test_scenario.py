from pathlib import Path

import pytest

from hoa_eval.scenario import ScenarioError, load_scenario, load_scenarios

VALID = """\
name: {name}
fault:
  patch: {patch}
  namespace: {namespace}
  deployment: orders
wait:
  {wait}
alert: "orders rollout stuck"
expected:
  cause_label: {label}
  target: {target}
"""


def write(
    tmp_path: Path,
    *,
    name: str = "sample",
    patch: str = "deploy/kind/faults/image-pull.yaml",
    namespace: str = "demo",
    wait: str = "min_restarts: 1",
    label: str = "image_pull_error",
    target: str = "demo/orders",
) -> Path:
    path = tmp_path / "sample.yaml"
    text = VALID.format(
        name=name, patch=patch, namespace=namespace, wait=wait, label=label, target=target
    )
    path.write_text(text, encoding="utf-8")
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


def test_a_valid_file_loads(tmp_path: Path) -> None:
    assert load_scenario(write(tmp_path)).expected.target == "demo/orders"


@pytest.mark.parametrize(
    ("change", "message"),
    [
        ({"wait": "timeout_seconds: 60"}, "waiting_reasons or min_restarts"),
        ({"label": "network_partition"}, "cause_label"),
        ({"namespace": "kube-system"}, "namespace"),
        ({"name": "other"}, "must match the file name"),
        ({"patch": "deploy/kind/demo/20-orders.yaml"}, "under deploy/kind/faults"),
        ({"patch": "../outside.yaml"}, "under deploy/kind/faults"),
        ({"patch": "deploy/kind/faults/missing.yaml"}, "under deploy/kind/faults"),
        ({"target": "demo/inventory"}, "must be the fault target demo/orders"),
    ],
)
def test_scenarios_outside_the_rules_are_rejected(
    tmp_path: Path, change: dict[str, str], message: str
) -> None:
    with pytest.raises(ScenarioError, match=message):
        load_scenario(write(tmp_path, **change))


def test_broken_yaml_is_a_scenario_error(tmp_path: Path) -> None:
    path = tmp_path / "broken.yaml"
    path.write_text("name: [unclosed", encoding="utf-8")

    with pytest.raises(ScenarioError, match="broken.yaml"):
        load_scenario(path)
