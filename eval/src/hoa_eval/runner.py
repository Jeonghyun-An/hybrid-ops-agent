import time
from collections.abc import Callable, Sequence
from datetime import UTC, datetime
from typing import Literal, Protocol

from pydantic import BaseModel

from hoa_eval.agent import AgentOutcome, AgentReport
from hoa_eval.cluster import ClusterError, SymptomTimeout
from hoa_eval.scenario import Fault, Scenario, Symptom
from hoa_eval.scoring import Score, score

Agent = Callable[[str, str], AgentOutcome]
# rate_limit·setup·no_symptom은 모델이 답할 기회가 없던 회차, agent는 답을 내지 못한 회차
Failure = Literal["rate_limit", "setup", "no_symptom", "agent"]
STOPPING_FAILURES: tuple[Failure, ...] = ("rate_limit", "setup")


class Cluster(Protocol):
    def inject(self, fault: Fault) -> None: ...

    def reset(self) -> None: ...

    def wait_for(self, fault: Fault, symptom: Symptom) -> float: ...


class RunRecord(BaseModel):
    scenario: str
    model: str
    attempt: int
    started_at: datetime
    symptom_seconds: float | None = None
    model_id: str | None = None
    score: Score | None = None
    error: str | None = None
    failure: Failure | None = None
    reset_error: str | None = None
    report: AgentReport | None = None


def failure_of(outcome: AgentOutcome) -> Failure | None:
    if outcome.rate_limited:
        return "rate_limit"
    if outcome.setup_error:
        return "setup"
    return "agent" if outcome.report is None else None


def run_once(
    scenario: Scenario, model: str, attempt: int, cluster: Cluster, agent: Agent
) -> RunRecord:
    record = RunRecord(
        scenario=scenario.name, model=model, attempt=attempt, started_at=datetime.now(UTC)
    )
    outcome: AgentOutcome | None = None
    try:
        cluster.inject(scenario.fault)
        try:
            record.symptom_seconds = cluster.wait_for(scenario.fault, scenario.wait)
        except SymptomTimeout as exc:
            record.error = str(exc)
            record.failure = "no_symptom"
        else:
            outcome = agent(scenario.alert, model)
    finally:
        try:
            cluster.reset()
        except ClusterError as exc:
            # 이미 끝낸 조사(무료 등급 요청을 쓴 결과)를 잃지 않게 기록에 남기고 배치에서 멈춘다
            record.reset_error = str(exc)
    if outcome is not None:
        record.error = outcome.error
        record.failure = failure_of(outcome)
        if outcome.report is not None:
            record.report = outcome.report
            record.model_id = outcome.report.model
            record.score = score(scenario.expected, outcome.report)
    return record


def run_batch(
    scenarios: Sequence[Scenario],
    model: str,
    repeat: int,
    cluster: Cluster,
    agent: Agent,
    *,
    pause_seconds: float,
    sink: Callable[[RunRecord], None],
    sleep: Callable[[float], None] = time.sleep,
) -> list[RunRecord]:
    """순서대로 하나씩 돈다 — 요청 한도·설정 오류면 남은 회차도 같은 이유로 실패하므로 멈춘다."""
    cluster.reset()
    records: list[RunRecord] = []
    for attempt in range(1, repeat + 1):
        for scenario in scenarios:
            if records:
                sleep(pause_seconds)
            record = run_once(scenario, model, attempt, cluster, agent)
            sink(record)
            records.append(record)
            if record.reset_error is not None:
                raise ClusterError(record.reset_error)
            if record.failure in STOPPING_FAILURES:
                return records
    return records
