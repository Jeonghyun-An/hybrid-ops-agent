import json
import logging
from collections.abc import Iterator

import httpx
import openai
import pytest
from fastapi import FastAPI

from hoa_agent import __version__, cli
from hoa_agent.cli import SkipHealthChecks, main
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


@pytest.mark.parametrize("url", ["hoa-mcp:8080/mcp", "ftp://hoa-mcp/mcp", "/mcp"])
def test_serve_refuses_a_non_http_mcp_url(capsys: pytest.CaptureFixture[str], url: str) -> None:
    assert main(["serve"], env={"HOA_MCP_URL": url}, run_server=never_serve) == 2
    assert "must be an http:// or https:// URL" in capsys.readouterr().err


@pytest.fixture
def clean_logging() -> Iterator[None]:
    names = ("", "httpx", "hoa_agent", "uvicorn.access")
    saved = [
        (logging.getLogger(n), logging.getLogger(n).level, list(logging.getLogger(n).filters))
        for n in names
    ]
    handlers = list(logging.getLogger().handlers)
    yield
    for logger, level, filters in saved:
        logger.setLevel(level)
        logger.filters[:] = filters
    logging.getLogger().handlers[:] = handlers


@pytest.mark.usefixtures("clean_logging")
def test_serve_keeps_the_llm_address_out_of_the_logs() -> None:
    env = {"HOA_MCP_URL": "http://hoa-mcp-k8s-read.hoa-system.svc/mcp"}

    assert main(["serve"], env=env, run_server=lambda app, **kwargs: None) == 0

    assert logging.getLogger("httpx").getEffectiveLevel() >= logging.WARNING
    assert logging.getLogger("hoa_agent").getEffectiveLevel() == logging.INFO
    access = logging.getLogger("uvicorn.access")
    assert any(isinstance(f, SkipHealthChecks) for f in access.filters)


def access_record(path: str) -> logging.LogRecord:
    return logging.LogRecord(
        "uvicorn.access",
        logging.INFO,
        __file__,
        0,
        '%s - "GET %s HTTP/1.1" 200',
        ("ip", path),
        None,
    )


def test_health_check_hits_are_dropped_from_the_access_log() -> None:
    skip = SkipHealthChecks()

    assert not skip.filter(access_record("/healthz"))
    assert skip.filter(access_record("/investigations"))


@pytest.mark.usefixtures("clean_logging")
@pytest.mark.anyio
async def test_serve_wires_env_model_and_alert_into_the_investigation(
    monkeypatch: pytest.MonkeyPatch, result: InvestigationResult
) -> None:
    seen: list[tuple[str, str, object]] = []

    async def recorder(alert: str, model: str, env: object = None) -> InvestigationResult:
        seen.append((alert, model, env))
        return result

    monkeypatch.setattr(cli, "run_investigation", recorder)
    apps: list[FastAPI] = []
    env = {"HOA_MCP_URL": "http://hoa-mcp-k8s-read.hoa-system.svc/mcp", "HOA_MODEL": "gemini"}
    main(["serve"], env=env, run_server=lambda app, **kwargs: apps.append(app))

    transport = httpx.ASGITransport(app=apps[0])
    async with httpx.AsyncClient(transport=transport, base_url="http://agent") as client:
        response = await client.post("/investigations", json={"alert": "orders stuck"})

    assert response.status_code == 200
    assert seen == [("orders stuck", "gemini", env)]
