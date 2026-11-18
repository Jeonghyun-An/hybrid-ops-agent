import json

import httpx
import openai
import pytest
from fastapi import FastAPI

from hoa_agent import __version__
from hoa_agent.cli import main
from hoa_agent.graph import DiagnosisSchemaError
from hoa_agent.llm import LLMConfigError
from hoa_agent.mcp_tools import MCPSetupError
from hoa_agent.result import InvestigationResult


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
    assert "조사: 도구 1번" in err


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


@pytest.mark.parametrize(
    ("error", "code"),
    [
        (DiagnosisSchemaError("the model broke the diagnosis schema"), 1),
        (openai.OpenAIError("finish_reason was length"), 1),
        (MCPSetupError("the MCP server stopped"), 2),
    ],
)
def test_failures_map_to_exit_codes(
    capsys: pytest.CaptureFixture[str], error: Exception, code: int
) -> None:
    async def fake(alert: str, model: str) -> InvestigationResult:
        raise error

    assert main(["investigate", "x"], investigator=fake) == code
    assert str(error) in capsys.readouterr().err


def never_serve(app: object, **kwargs: object) -> None:
    raise AssertionError("must not start the server")


def test_serve_needs_the_mcp_url(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["serve"], env={}, run_server=never_serve) == 2
    assert "HOA_MCP_URL is not set" in capsys.readouterr().err


def test_serve_runs_the_api_on_the_given_port() -> None:
    calls: list[tuple[object, dict[str, object]]] = []

    def fake_run(app: object, **kwargs: object) -> None:
        calls.append((app, kwargs))

    env = {"HOA_MCP_URL": "http://hoa-mcp-k8s-read.hoa-system.svc/mcp", "HOA_MODEL": "gemini"}
    assert main(["serve", "--port", "9000"], env=env, run_server=fake_run) == 0

    [(app, kwargs)] = calls
    assert isinstance(app, FastAPI)
    assert kwargs == {"host": "127.0.0.1", "port": 9000}


@pytest.mark.parametrize(
    ("extra", "message"),
    [
        ({"HOA_MODEL": "gpt"}, "HOA_MODEL must be one of gemma, gemini"),
        ({"HOA_INVESTIGATION_TIMEOUT": "soon"}, "HOA_INVESTIGATION_TIMEOUT must be"),
        ({"HOA_INVESTIGATION_TIMEOUT": "0"}, "HOA_INVESTIGATION_TIMEOUT must be"),
        ({"HOA_INVESTIGATION_TIMEOUT": "nan"}, "HOA_INVESTIGATION_TIMEOUT must be"),
    ],
)
def test_serve_refuses_bad_settings(
    capsys: pytest.CaptureFixture[str], extra: dict[str, str], message: str
) -> None:
    env = {"HOA_MCP_URL": "http://hoa-mcp-k8s-read.hoa-system.svc/mcp", **extra}
    assert main(["serve"], env=env, run_server=never_serve) == 2
    assert message in capsys.readouterr().err
