from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

from hoa_eval.agent import AgentReport
from hoa_eval.report import load_records, runs_table, short_error, summary_table
from hoa_eval.runner import RunRecord
from hoa_eval.scenario import Scenario
from hoa_eval.scoring import score

STARTED = datetime(2026, 11, 16, tzinfo=UTC)


def scored_record(
    scenario: Scenario, report: AgentReport, attempt: int, model: str = "gemma"
) -> RunRecord:
    return RunRecord(
        scenario=scenario.name,
        model=model,
        attempt=attempt,
        started_at=STARTED,
        model_id=report.model,
        score=score(scenario.expected, report),
        report=report,
    )


def failed_record(scenario: str, attempt: int, failure: str, error: str) -> RunRecord:
    return RunRecord.model_validate(
        {
            "scenario": scenario,
            "model": "gemma",
            "attempt": attempt,
            "started_at": STARTED,
            "failure": failure,
            "error": error,
        }
    )


def test_summary_leaves_runs_the_model_never_saw_out_of_the_ratios(
    image_pull: Scenario, make_report: Callable[..., AgentReport]
) -> None:
    records = [
        scored_record(image_pull, make_report(), 1),
        scored_record(image_pull, make_report(cause_label="oom_killed"), 2),
        failed_record("image-pull", 3, "agent", "hoa: schema"),
        failed_record("image-pull", 4, "rate_limit", "hoa: rate limit"),
        failed_record("image-pull", 5, "no_symptom", "no symptom"),
    ]

    row = summary_table(records).splitlines()[2]

    assert row == (
        "| image-pull | gemma4-26b-a4b | 3 | 1/3 | 2/3 | 2/2 | 2.0 | 2 | 2 | 6.5 | 4,000 "
        "| 1 | 한도 1, 증상 없음 1 |"
    )


def test_summary_shows_groups_without_any_scored_run(image_pull: Scenario) -> None:
    records = [failed_record("bad-config", 1, "rate_limit", "hoa: rate limit")]

    row = summary_table(records).splitlines()[2]

    assert row == "| bad-config | gemma | 0 | 0/0 | 0/0 | - | - | - | - | - | - | 0 | 한도 1 |"


def test_summary_keeps_one_row_per_scenario_and_profile(
    image_pull: Scenario, bad_config: Scenario, make_report: Callable[..., AgentReport]
) -> None:
    records = [
        scored_record(image_pull, make_report(), 1),
        scored_record(bad_config, make_report(), 1),
        scored_record(image_pull, make_report(model="gemini-3.5-flash-lite"), 1, model="gemini"),
    ]

    lines = summary_table(records).splitlines()[2:]

    assert [line.split(" | ")[:2] for line in lines] == [
        ["| image-pull", "gemma4-26b-a4b"],
        ["| bad-config", "gemma4-26b-a4b"],
        ["| image-pull", "gemini-3.5-flash-lite"],
    ]


def test_runs_table_marks_wrong_labels_and_tidies_errors(
    image_pull: Scenario, make_report: Callable[..., AgentReport]
) -> None:
    home = str(Path.home())
    records = [
        scored_record(image_pull, make_report(cause_label="oom_killed"), 1),
        failed_record("image-pull", 2, "agent", f"hoa: MCP kubeconfig not found: {home}/x | y"),
    ]

    lines = runs_table(records).splitlines()

    assert "oom_killed ✗" in lines[2]
    assert lines[3].endswith("| hoa: MCP kubeconfig not found: ~/x \\| y |")


def test_long_errors_are_cut() -> None:
    assert len(short_error("x" * 500)) == 120


def test_records_round_trip_through_jsonl(
    tmp_path: Path, image_pull: Scenario, make_report: Callable[..., AgentReport]
) -> None:
    record = scored_record(image_pull, make_report(), 1)
    path = tmp_path / "run.jsonl"
    path.write_text(record.model_dump_json() + "\n\n", encoding="utf-8")

    assert load_records([path]) == [record]
