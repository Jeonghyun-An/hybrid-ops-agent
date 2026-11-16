from collections.abc import Callable
from pathlib import Path

import pytest

from hoa_eval import __version__
from hoa_eval.agent import AgentOutcome, AgentReport
from hoa_eval.cli import main
from hoa_eval.cluster import DemoCluster
from hoa_eval.report import load_records


def quiet_cluster() -> DemoCluster:
    def kubectl(*args: str) -> str:
        if "pods" in args:
            return (
                '{"items": [{"metadata": {"name": "p"}, '
                '"status": {"containerStatuses": [{"restartCount": 3}]}}]}'
            )
        return ""

    return DemoCluster(kubectl)


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

    code = main(
        [
            "run",
            "--repeat",
            "1",
            "--scenario",
            "bad-config",
            "--pause",
            "0",
            "--results-dir",
            str(tmp_path),
        ],
        cluster=quiet_cluster(),
        agent=agent,
    )

    out, err = capsys.readouterr()
    assert code == 0
    assert models == ["gemma"]
    [path] = tmp_path.glob("*-gemma.jsonl")
    [record] = load_records([path])
    assert record.score is not None
    assert record.score.label_correct is True
    assert "| bad-config | gemma4-26b-a4b | 1 | 1/1 |" in out
    assert "bad-config #1: 맞음" in err


def test_run_exits_3_when_the_rate_limit_stops_the_batch(tmp_path: Path) -> None:
    def agent(alert: str, model: str) -> AgentOutcome:
        return AgentOutcome(error="hoa: rate limit", rate_limited=True)

    code = main(
        ["run", "--model", "gemini", "--pause", "0", "--results-dir", str(tmp_path)],
        cluster=quiet_cluster(),
        agent=agent,
    )

    assert code == 3


def test_unknown_scenario_is_reported(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    code = main(
        ["run", "--model", "gemma", "--scenario", "oom", "--results-dir", str(tmp_path)],
        cluster=quiet_cluster(),
    )

    assert code == 2
    assert "unknown scenario: oom" in capsys.readouterr().err
