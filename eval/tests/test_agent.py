import sys
from collections.abc import Callable

from hoa_eval.agent import AgentReport, run_agent


def python_command(script: str) -> list[str]:
    # 진짜 hoa처럼 표준출력을 UTF-8로 낸다(Windows 파이프의 기본은 로캘 인코딩)
    prelude = "import sys; sys.stdout.reconfigure(encoding='utf-8'); "
    return [sys.executable, "-c", prelude + script]


def test_successful_run_parses_the_report(make_report: Callable[..., AgentReport]) -> None:
    report = make_report()
    script = (
        "assert sys.argv[1:4] == ['investigate', '--json', '--model']; "
        f"print({report.model_dump_json()!r})"
    )

    outcome = run_agent("orders rollout stuck", "gemma", command=python_command(script))

    assert outcome.error is None
    assert outcome.report == report


def test_failed_run_keeps_the_last_error_line() -> None:
    script = "print('trace', file=sys.stderr); print('hoa: boom', file=sys.stderr); sys.exit(1)"

    outcome = run_agent("x", "gemini", command=python_command(script))

    assert outcome.report is None
    assert outcome.error == "hoa: boom"
    assert outcome.rate_limited is False


def test_exit_code_3_marks_a_rate_limit() -> None:
    script = "print('hoa: rate limit', file=sys.stderr); sys.exit(3)"

    outcome = run_agent("x", "gemini", command=python_command(script))

    assert outcome.rate_limited is True


def test_output_outside_the_report_schema_is_an_error() -> None:
    outcome = run_agent("x", "gemma", command=python_command("print('{}')"))

    assert outcome.report is None
    assert outcome.error is not None
    assert "broke the report schema" in outcome.error
