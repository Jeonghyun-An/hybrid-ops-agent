import time
from collections.abc import Callable, Sequence
from datetime import UTC, datetime
from typing import Protocol

from pydantic import BaseModel

from hoa_eval.agent import AgentOutcome, AgentReport
from hoa_eval.cluster import SymptomTimeout
from hoa_eval.scenario import Fault, Scenario, Symptom
from hoa_eval.scoring import Score, score

Agent = Callable[[str, str], AgentOutcome]


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
    rate_limited: bool = False
    report: AgentReport | None = None


def run_once(
    scenario: Scenario, model: str, attempt: int, cluster: Cluster, agent: Agent
) -> RunRecord:
    record = RunRecord(
        scenario=scenario.name, model=model, attempt=attempt, started_at=datetime.now(UTC)
    )
    try:
        cluster.inject(scenario.fault)
        try:
            record.symptom_seconds = cluster.wait_for(scenario.fault, scenario.wait)
        except SymptomTimeout as exc:
            record.error = str(exc)
            return record
        outcome = agent(scenario.alert, model)
    finally:
        cluster.reset()
    record.error = outcome.error
    record.rate_limited = outcome.rate_limited
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
    """순서대로 한 번에 하나씩 돈다 — 무료 등급 요청 한도에 걸리면 남은 회차는 멈춘다."""
    cluster.reset()
    records: list[RunRecord] = []
    for attempt in range(1, repeat + 1):
        for scenario in scenarios:
            if records:
                sleep(pause_seconds)
            record = run_once(scenario, model, attempt, cluster, agent)
            sink(record)
            records.append(record)
            if record.rate_limited:
                return records
    return records
