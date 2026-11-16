import json

import httpx
import openai
import pytest

from hoa_agent import __version__
from hoa_agent.cli import main
from hoa_agent.diagnosis import Diagnosis
from hoa_agent.llm import LLMConfigError
from hoa_agent.result import InvestigationResult, Usage


@pytest.fixture
def result(diagnosis: Diagnosis) -> InvestigationResult:
    return InvestigationResult(
        model="gemini-3.5-flash",
        alert="orders rollout stuck",
        diagnosis=diagnosis,
        stop_reason="answered",
        steps=[],
        invalid_tool_calls=0,
        usage=Usage(model_calls=2, input_tokens=1_500, output_tokens=200, total_tokens=1_700),
        elapsed_seconds=4.2,
    )


def test_version_flag_prints_name_and_version(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exc_info:
        main(["--version"])

    assert exc_info.value.code == 0
    assert capsys.readouterr().out.strip() == f"hoa {__version__}"


def test_no_arguments_prints_help_and_succeeds(capsys: pytest.CaptureFixture[str]) -> None:
    assert main([]) == 0
    assert "usage: hoa" in capsys.readouterr().out


def test_investigate_prints_json_and_a_korean_summary(
    capsys: pytest.CaptureFixture[str], result: InvestigationResult
) -> None:
    seen: list[tuple[str, str]] = []

    async def fake(alert: str, model: str) -> InvestigationResult:
        seen.append((alert, model))
        return result

    code = main(["investigate", "--model", "gemini", "orders rollout stuck"], investigator=fake)

    out, err = capsys.readouterr()
    assert code == 0
    assert seen == [("orders rollout stuck", "gemini")]
    assert InvestigationResult.model_validate(json.loads(out)) == result
    assert "원인: image_pull_error" in err
    assert "[get_events] Failed to pull image" in err


def test_model_defaults_to_gemma(result: InvestigationResult) -> None:
    seen: list[str] = []

    async def fake(alert: str, model: str) -> InvestigationResult:
        seen.append(model)
        return result

    assert main(["investigate", "orders rollout stuck"], investigator=fake) == 0
    assert seen == ["gemma"]


def test_json_flag_keeps_stderr_quiet(
    capsys: pytest.CaptureFixture[str], result: InvestigationResult
) -> None:
    async def fake(alert: str, model: str) -> InvestigationResult:
        return result

    assert main(["investigate", "--json", "--model", "gemma", "x"], investigator=fake) == 0
    assert capsys.readouterr().err == ""


def test_missing_settings_exit_with_code_2_and_a_message(
    capsys: pytest.CaptureFixture[str],
) -> None:
    async def fake(alert: str, model: str) -> InvestigationResult:
        raise LLMConfigError("GEMINI_API_KEY is not set")

    assert main(["investigate", "--model", "gemini", "x"], investigator=fake) == 2
    assert "GEMINI_API_KEY is not set" in capsys.readouterr().err


def test_unknown_model_is_a_usage_error() -> None:
    with pytest.raises(SystemExit) as exc_info:
        main(["investigate", "--model", "gpt", "x"])

    assert exc_info.value.code == 2


def test_rate_limit_exits_with_code_3_so_the_eval_runner_can_stop(
    capsys: pytest.CaptureFixture[str],
) -> None:
    async def fake(alert: str, model: str) -> InvestigationResult:
        request = httpx.Request("POST", "https://llm.test/v1/chat/completions")
        response = httpx.Response(429, request=request)
        raise openai.RateLimitError("quota exceeded", response=response, body=None)

    assert main(["investigate", "--model", "gemini", "x"], investigator=fake) == 3
    assert "rate limit" in capsys.readouterr().err
