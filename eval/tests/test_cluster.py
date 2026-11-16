import json
import subprocess

import pytest

from hoa_eval import cluster
from hoa_eval.cluster import (
    ClusterError,
    ContainerStatus,
    DemoCluster,
    Kubectl,
    SymptomTimeout,
    container_statuses,
    symptom_met,
)
from hoa_eval.scenario import Scenario, Symptom


def pods_json(*statuses: dict[str, object]) -> str:
    return json.dumps({"items": [{"status": {"containerStatuses": list(statuses)}}]})


def pod_list(*terminating: bool) -> str:
    return json.dumps(
        {
            "items": [
                {"metadata": {"name": f"p{i}", "deletionTimestamp": "now" if gone else None}}
                for i, gone in enumerate(terminating)
            ]
        }
    )


class FakeKubectl:
    def __init__(self, pod_answers: list[str]) -> None:
        self.calls: list[tuple[str, ...]] = []
        self.pod_answers = pod_answers

    def __call__(self, *args: str) -> str:
        self.calls.append(args)
        return self.pod_answers.pop(0) if "pods" in args else ""


class FakeClock:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.now += seconds


def test_container_statuses_read_waiting_reason_and_restarts() -> None:
    pods = pods_json(
        {"restartCount": 2, "state": {"waiting": {"reason": "CrashLoopBackOff"}}},
        {"restartCount": 0, "state": {"running": {}}},
    )

    assert container_statuses(pods) == [
        ContainerStatus(restart_count=2, waiting_reason="CrashLoopBackOff"),
        ContainerStatus(restart_count=0, waiting_reason=None),
    ]


def test_pending_pod_without_statuses_has_no_symptom() -> None:
    assert container_statuses(json.dumps({"items": [{"status": {}}]})) == []


@pytest.mark.parametrize(
    ("status", "met"),
    [
        (ContainerStatus(restart_count=0, waiting_reason="ImagePullBackOff"), True),
        (ContainerStatus(restart_count=0, waiting_reason="ContainerCreating"), False),
        (ContainerStatus(restart_count=1, waiting_reason=None), True),
    ],
)
def test_symptom_matches_waiting_reasons_or_restarts(status: ContainerStatus, met: bool) -> None:
    symptom = Symptom(waiting_reasons=["ErrImagePull", "ImagePullBackOff"], min_restarts=1)

    assert symptom_met([status], symptom) is met


def test_kubectl_always_names_the_context(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: list[list[str]] = []

    def fake_run(argv: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        seen.append(argv)
        return subprocess.CompletedProcess(argv, 0, stdout="ok", stderr="")

    monkeypatch.setattr(cluster.subprocess, "run", fake_run)

    assert Kubectl()("get", "pods") == "ok"
    assert seen == [["kubectl", "--context", "kind-hoa", "get", "pods"]]


@pytest.mark.parametrize(
    "failure",
    [
        subprocess.CompletedProcess(["kubectl"], 1, stdout="", stderr="forbidden"),
        subprocess.TimeoutExpired(["kubectl"], 240),
        FileNotFoundError("kubectl"),
    ],
)
def test_kubectl_failures_become_cluster_errors(
    monkeypatch: pytest.MonkeyPatch, failure: object
) -> None:
    def fake_run(argv: list[str], **kwargs: object) -> object:
        if isinstance(failure, BaseException):
            raise failure
        return failure

    monkeypatch.setattr(cluster.subprocess, "run", fake_run)

    with pytest.raises(ClusterError, match="kubectl get pods failed"):
        Kubectl()("get", "pods")


def test_inject_patches_the_target_with_the_scenario_file(image_pull: Scenario) -> None:
    kubectl = FakeKubectl([])

    DemoCluster(kubectl).inject(image_pull.fault)

    args = kubectl.calls[0]
    assert args[:4] == ("-n", "demo", "patch", "deployment/orders")
    assert args[-1].endswith("image-pull.yaml")


def test_reset_reapplies_restarts_waits_for_old_pods_and_clears_events() -> None:
    clock = FakeClock()
    kubectl = FakeKubectl([pod_list(False, True), pod_list(False)])

    DemoCluster(kubectl, sleep=clock.sleep, clock=clock).reset()

    assert kubectl.calls[0][0] == "apply"
    assert kubectl.calls[1] == ("-n", "demo", "rollout", "restart", "deployment")
    assert [c[4] for c in kubectl.calls[2:5]] == [
        "deployment/inventory",
        "deployment/orders",
        "deployment/gateway",
    ]
    assert kubectl.calls[-1] == ("-n", "demo", "delete", "events", "--all")
    assert len(kubectl.calls) == 8
    assert clock.now == 3.0


def test_reset_fails_when_old_pods_never_leave() -> None:
    clock = FakeClock()
    kubectl = FakeKubectl([pod_list(True)] * 100)

    with pytest.raises(ClusterError, match="still terminating after reset: p0"):
        DemoCluster(kubectl, sleep=clock.sleep, clock=clock).reset()


def test_wait_polls_until_the_symptom_shows(image_pull: Scenario) -> None:
    clock = FakeClock()
    kubectl = FakeKubectl(
        [
            pods_json({"restartCount": 0, "state": {"waiting": {"reason": "ContainerCreating"}}}),
            pods_json({"restartCount": 0, "state": {"waiting": {"reason": "ErrImagePull"}}}),
        ]
    )

    waited = DemoCluster(kubectl, sleep=clock.sleep, clock=clock).wait_for(
        image_pull.fault, image_pull.wait
    )

    assert waited == 3.0
    assert kubectl.calls[0][-4:] == ("-l", "app=orders", "-o", "json")


def test_wait_gives_up_after_the_timeout(bad_config: Scenario) -> None:
    clock = FakeClock()
    healthy = pods_json({"restartCount": 0, "state": {"running": {}}})
    kubectl = FakeKubectl([healthy] * 100)

    with pytest.raises(SymptomTimeout, match="within 120s"):
        DemoCluster(kubectl, sleep=clock.sleep, clock=clock).wait_for(
            bad_config.fault, bad_config.wait
        )
