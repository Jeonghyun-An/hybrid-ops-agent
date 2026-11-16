from collections.abc import Callable

import pytest

from hoa_eval.agent import AgentOutcome, AgentReport
from hoa_eval.cluster import SymptomTimeout
from hoa_eval.runner import RunRecord, run_batch, run_once
from hoa_eval.scenario import Fault, Scenario, Symptom


class FakeCluster:
    def __init__(self, *, symptom: bool = True) -> None:
        self.log: list[str] = []
        self.symptom = symptom

    def inject(self, fault: Fault) -> None:
        self.log.append(f"inject {fault.deployment}")

    def reset(self) -> None:
        self.log.append("reset")

    def wait_for(self, fault: Fault, symptom: Symptom) -> float:
        self.log.append(f"wait {fault.deployment}")
        if not self.symptom:
            raise SymptomTimeout("no symptom")
        return 12.0


class FakeAgent:
    def __init__(self, outcomes: list[AgentOutcome]) -> None:
        self.calls: list[tuple[str, str]] = []
        self.outcomes = outcomes

    def __call__(self, alert: str, model: str) -> AgentOutcome:
        self.calls.append((alert, model))
        return self.outcomes.pop(0)


def test_one_run_injects_waits_asks_the_agent_scores_and_resets(
    image_pull: Scenario, make_report: Callable[..., AgentReport]
) -> None:
    cluster = FakeCluster()
    agent = FakeAgent([AgentOutcome(report=make_report())])

    record = run_once(image_pull, "gemma", 1, cluster, agent)

    assert cluster.log == ["inject orders", "wait orders", "reset"]
    assert agent.calls == [(image_pull.alert, "gemma")]
    assert record.symptom_seconds == 12.0
    assert record.model_id == "gemma4-26b-a4b"
    assert record.score is not None
    assert record.score.label_correct is True


def test_missing_symptom_skips_the_agent_but_still_resets(image_pull: Scenario) -> None:
    cluster = FakeCluster(symptom=False)
    agent = FakeAgent([])

    record = run_once(image_pull, "gemma", 1, cluster, agent)

    assert agent.calls == []
    assert cluster.log[-1] == "reset"
    assert record.error == "no symptom"
    assert record.score is None


def test_cluster_is_reset_even_when_the_agent_crashes(image_pull: Scenario) -> None:
    cluster = FakeCluster()

    def broken(alert: str, model: str) -> AgentOutcome:
        raise RuntimeError("agent crashed")

    with pytest.raises(RuntimeError):
        run_once(image_pull, "gemma", 1, cluster, broken)
    assert cluster.log[-1] == "reset"


def test_batch_repeats_every_scenario_with_pauses_between_runs(
    image_pull: Scenario, bad_config: Scenario, make_report: Callable[..., AgentReport]
) -> None:
    agent = FakeAgent([AgentOutcome(report=make_report()) for _ in range(4)])
    pauses: list[float] = []
    written: list[RunRecord] = []

    records = run_batch(
        [image_pull, bad_config],
        "gemma",
        2,
        FakeCluster(),
        agent,
        pause_seconds=5,
        sink=written.append,
        sleep=pauses.append,
    )

    assert [(r.scenario, r.attempt) for r in records] == [
        ("image-pull", 1),
        ("bad-config", 1),
        ("image-pull", 2),
        ("bad-config", 2),
    ]
    assert written == records
    assert pauses == [5, 5, 5]


def test_batch_stops_at_the_first_rate_limit(image_pull: Scenario, bad_config: Scenario) -> None:
    agent = FakeAgent([AgentOutcome(error="hoa: rate limit", rate_limited=True)])

    records = run_batch(
        [image_pull, bad_config],
        "gemini",
        3,
        FakeCluster(),
        agent,
        pause_seconds=0,
        sink=lambda record: None,
        sleep=lambda seconds: None,
    )

    assert len(records) == 1
    assert records[0].rate_limited is True
