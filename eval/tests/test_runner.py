from collections.abc import Callable

import pytest

from hoa_eval.agent import AgentOutcome, AgentReport
from hoa_eval.cluster import ClusterError, SymptomTimeout
from hoa_eval.runner import RunRecord, run_batch, run_once
from hoa_eval.scenario import Fault, Scenario, Symptom


class FakeCluster:
    def __init__(self, *, symptom: bool = True, broken_reset: bool = False) -> None:
        self.log: list[str] = []
        self.symptom = symptom
        self.broken_reset = broken_reset

    def inject(self, fault: Fault) -> None:
        self.log.append(f"inject {fault.deployment}")

    def reset(self) -> None:
        self.log.append("reset")
        if self.broken_reset and len(self.log) > 1:
            raise ClusterError("pods still terminating after reset: p0")

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


def test_one_run_injects_waits_asks_the_agent_resets_and_scores(
    image_pull: Scenario, make_report: Callable[..., AgentReport]
) -> None:
    cluster = FakeCluster()
    agent = FakeAgent([AgentOutcome(report=make_report())])

    record = run_once(image_pull, "gemma", 1, cluster, agent)

    assert cluster.log == ["inject orders", "wait orders", "reset"]
    assert agent.calls == [(image_pull.alert, "gemma")]
    assert record.symptom_seconds == 12.0
    assert record.model_id == "gemma4-26b-a4b"
    assert record.failure is None
    assert record.score is not None
    assert record.score.label_correct is True


def test_missing_symptom_skips_the_agent_but_still_resets(image_pull: Scenario) -> None:
    cluster = FakeCluster(symptom=False)
    agent = FakeAgent([])

    record = run_once(image_pull, "gemma", 1, cluster, agent)

    assert agent.calls == []
    assert cluster.log[-1] == "reset"
    assert (record.error, record.failure) == ("no symptom", "no_symptom")
    assert record.score is None


@pytest.mark.parametrize(
    ("outcome", "failure"),
    [
        (AgentOutcome(error="hoa: boom"), "agent"),
        (AgentOutcome(error="hoa: no key", setup_error=True), "setup"),
        (AgentOutcome(error="hoa: rate limit", rate_limited=True), "rate_limit"),
    ],
)
def test_agent_failures_are_classified(
    image_pull: Scenario, outcome: AgentOutcome, failure: str
) -> None:
    record = run_once(image_pull, "gemma", 1, FakeCluster(), FakeAgent([outcome]))

    assert record.failure == failure


def test_cluster_is_reset_even_when_the_agent_crashes(image_pull: Scenario) -> None:
    cluster = FakeCluster()

    def broken(alert: str, model: str) -> AgentOutcome:
        raise RuntimeError("agent crashed")

    with pytest.raises(RuntimeError):
        run_once(image_pull, "gemma", 1, cluster, broken)
    assert cluster.log[-1] == "reset"


def test_batch_starts_clean_and_repeats_every_scenario_with_pauses(
    image_pull: Scenario, bad_config: Scenario, make_report: Callable[..., AgentReport]
) -> None:
    cluster = FakeCluster()
    agent = FakeAgent([AgentOutcome(report=make_report()) for _ in range(4)])
    pauses: list[float] = []
    written: list[RunRecord] = []

    records = run_batch(
        [image_pull, bad_config],
        "gemma",
        2,
        cluster,
        agent,
        pause_seconds=5,
        sink=written.append,
        sleep=pauses.append,
    )

    assert cluster.log[0] == "reset"
    assert [(r.scenario, r.attempt) for r in records] == [
        ("image-pull", 1),
        ("bad-config", 1),
        ("image-pull", 2),
        ("bad-config", 2),
    ]
    assert written == records
    assert pauses == [5, 5, 5]


@pytest.mark.parametrize(
    "outcome",
    [
        AgentOutcome(error="hoa: rate limit", rate_limited=True),
        AgentOutcome(error="hoa: HOA_GEMMA_BASE_URL is not set", setup_error=True),
    ],
)
def test_batch_stops_when_every_later_run_would_fail_the_same_way(
    image_pull: Scenario, bad_config: Scenario, outcome: AgentOutcome
) -> None:
    records = run_batch(
        [image_pull, bad_config],
        "gemini",
        3,
        FakeCluster(),
        FakeAgent([outcome]),
        pause_seconds=0,
        sink=lambda record: None,
        sleep=lambda seconds: None,
    )

    assert len(records) == 1


def test_a_failed_reset_keeps_the_finished_run_then_stops(
    image_pull: Scenario, bad_config: Scenario, make_report: Callable[..., AgentReport]
) -> None:
    written: list[RunRecord] = []

    with pytest.raises(ClusterError, match="still terminating"):
        run_batch(
            [image_pull, bad_config],
            "gemini",
            1,
            FakeCluster(broken_reset=True),
            FakeAgent([AgentOutcome(report=make_report())]),
            pause_seconds=0,
            sink=written.append,
            sleep=lambda seconds: None,
        )

    assert len(written) == 1
    assert written[0].score is not None
    assert written[0].reset_error is not None
