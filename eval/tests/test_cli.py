from collections.abc import Callable
from pathlib import Path

import pytest

from hoa_eval import __version__
from hoa_eval.agent import AgentOutcome, AgentReport
from hoa_eval.cli import main
from hoa_eval.cluster import ClusterError, DemoCluster
from hoa_eval.report import load_records


def quiet_cluster() -> DemoCluster:
    def kubectl(*args: str) -> str:
        if "pods" in args:
            return (
                '{"items": [{"metadata": {"name": "p"}, '
                '"status": {"containerStatuses": [{"restartCount": 3}]}}]}'
            )
        return ""

    now = [0.0]

    def sleep(seconds: float) -> None:
        now[0] += seconds

    # 증상이 끝내 안 나오는 시나리오로 돌려도 가짜 시계가 흘러 120초 제한에서 끝난다
    return DemoCluster(kubectl, sleep=sleep, clock=lambda: now[0])


class BrokenCluster:
    def inject(self, fault: object) -> None:
        raise ClusterError("kubectl patch failed: forbidden")

    def reset(self) -> None:
        pass

    def wait_for(self, fault: object, symptom: object) -> float:
        return 0.0


def run_args(tmp_path: Path, *extra: str) -> list[str]:
    return [
        "run",
        "--scenario",
        "bad-config",
        "--pause",
        "0",
        "--results-dir",
        str(tmp_path),
        *extra,
    ]


def test_version_flag_prints_name_and_version(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exc_info:
        main(["--version"])

    assert exc_info.value.code == 0
    assert capsys.readouterr().out.strip() == f"hoa-eval {__version__}"


def test_run_defaults_to_gemma_writes_jsonl_and_prints_the_summary(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    make_report: Callable[..., AgentReport],
) -> None:
    models: list[str] = []

    def agent(alert: str, model: str) -> AgentOutcome:
        models.append(model)
        return AgentOutcome(report=make_report(cause_label="bad_config", target="demo/inventory"))

    code = main(run_args(tmp_path, "--repeat", "1"), cluster=quiet_cluster(), agent=agent)

    out, err = capsys.readouterr()
    assert code == 0
    assert models == ["gemma"]
    [path] = tmp_path.glob("*-gemma.jsonl")
    [record] = load_records([path])
    assert record.score is not None
    assert record.score.label_correct is True
    assert "| bad-config | gemma4-26b-a4b | 1 | 1/1 |" in out
    assert "bad-config #1: 맞음" in err


@pytest.mark.parametrize(
    ("outcome", "code"),
    [
        (AgentOutcome(error="hoa: rate limit", rate_limited=True), 3),
        (AgentOutcome(error="hoa: HOA_GEMMA_BASE_URL is not set", setup_error=True), 2),
    ],
)
def test_run_stops_with_the_agent_failure_code(
    tmp_path: Path, outcome: AgentOutcome, code: int
) -> None:
    def agent(alert: str, model: str) -> AgentOutcome:
        return outcome

    assert main(run_args(tmp_path), cluster=quiet_cluster(), agent=agent) == code


def test_cluster_failures_exit_1(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    code = main(run_args(tmp_path), cluster=BrokenCluster())

    assert code == 1
    assert "kubectl patch failed" in capsys.readouterr().err


def test_unknown_scenario_is_reported(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    code = main(
        ["run", "--scenario", "oom", "--results-dir", str(tmp_path)], cluster=quiet_cluster()
    )

    assert code == 2
    assert "unknown scenario: oom" in capsys.readouterr().err


@pytest.mark.parametrize("option", [["--repeat", "0"], ["--pause", "-1"]])
def test_out_of_range_options_are_usage_errors(tmp_path: Path, option: list[str]) -> None:
    with pytest.raises(SystemExit) as exc_info:
        main(run_args(tmp_path, *option), cluster=quiet_cluster())

    assert exc_info.value.code == 2


def test_report_expands_wildcards_and_prints_both_tables(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    make_report: Callable[..., AgentReport],
) -> None:
    def agent(alert: str, model: str) -> AgentOutcome:
        return AgentOutcome(report=make_report(cause_label="bad_config", target="demo/inventory"))

    main(run_args(tmp_path, "--repeat", "1"), cluster=quiet_cluster(), agent=agent)
    capsys.readouterr()

    assert main(["report", str(tmp_path / "*.jsonl")]) == 0
    out = capsys.readouterr().out
    assert "| bad-config | gemma4-26b-a4b | 1 | 1/1 |" in out
    assert "| bad-config | gemma4-26b-a4b | 1 | bad_config |" in out


def test_report_on_a_missing_file_is_a_usage_error(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert main(["report", str(tmp_path / "none.jsonl")]) == 2
    assert "cannot read results" in capsys.readouterr().err
