from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

from hoa_eval.agent import AgentReport
from hoa_eval.report import load_records, runs_table, summary_table
from hoa_eval.runner import RunRecord
from hoa_eval.scenario import Scenario
from hoa_eval.scoring import score

STARTED = datetime(2026, 11, 16, tzinfo=UTC)


def scored_record(scenario: Scenario, report: AgentReport, attempt: int) -> RunRecord:
    return RunRecord(
        scenario=scenario.name,
        model="gemma",
        attempt=attempt,
        started_at=STARTED,
        model_id=report.model,
        score=score(scenario.expected, report),
        report=report,
    )


def test_summary_counts_correct_runs_and_failures(
    image_pull: Scenario, make_report: Callable[..., AgentReport]
) -> None:
    records = [
        scored_record(image_pull, make_report(), 1),
        scored_record(image_pull, make_report(cause_label="oom_killed"), 2),
        RunRecord(
            scenario="image-pull", model="gemma", attempt=3, started_at=STARTED, error="timed out"
        ),
    ]

    row = summary_table(records).splitlines()[2]

    assert row == (
        "| image-pull | gemma4-26b-a4b | 3 | 1/3 | 2/3 | 2/2 | 2.0 | 2 | 6.5 | 4,000 | 1 |"
    )


def test_runs_table_marks_wrong_labels_and_errors(
    image_pull: Scenario, make_report: Callable[..., AgentReport]
) -> None:
    records = [
        scored_record(image_pull, make_report(cause_label="oom_killed"), 1),
        RunRecord(
            scenario="image-pull", model="gemini", attempt=2, started_at=STARTED, error="429"
        ),
    ]

    lines = runs_table(records).splitlines()

    assert "oom_killed ✗" in lines[2]
    assert lines[3].endswith("| 429 |")


def test_records_round_trip_through_jsonl(
    tmp_path: Path, image_pull: Scenario, make_report: Callable[..., AgentReport]
) -> None:
    record = scored_record(image_pull, make_report(), 1)
    path = tmp_path / "run.jsonl"
    path.write_text(record.model_dump_json() + "\n\n", encoding="utf-8")

    assert load_records([path]) == [record]
