import asyncio
from collections.abc import Awaitable, Callable

import anyio
import httpx
import openai
import pytest

from hoa_agent.api import MAX_ALERT_CHARS, create_app
from hoa_agent.graph import DiagnosisSchemaError
from hoa_agent.llm import LLMConfigError
from hoa_agent.mcp_tools import MCPSetupError
from hoa_agent.result import InvestigationResult

pytestmark = pytest.mark.anyio

Investigate = Callable[[str], Awaitable[InvestigationResult]]
ALERT = "KubeDeploymentRolloutStuck — namespace=demo deployment=orders"


def client_for(investigate: Investigate, *, timeout_seconds: float = 5.0) -> httpx.AsyncClient:
    app = create_app(investigate, timeout_seconds=timeout_seconds)
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://agent")


async def test_investigation_returns_the_same_json_as_the_cli(
    result: InvestigationResult,
) -> None:
    seen: list[str] = []

    async def fake(alert: str) -> InvestigationResult:
        seen.append(alert)
        return result

    async with client_for(fake) as client:
        response = await client.post("/investigations", json={"alert": ALERT})

    assert response.status_code == 200
    assert InvestigationResult.model_validate(response.json()) == result
    assert seen == [ALERT]


@pytest.mark.parametrize("alert", ["", "x" * (MAX_ALERT_CHARS + 1)])
async def test_empty_or_huge_alerts_are_rejected_before_investigating(alert: str) -> None:
    async def never(alert: str) -> InvestigationResult:
        raise AssertionError("must not be called")

    async with client_for(never) as client:
        response = await client.post("/investigations", json={"alert": alert})

    assert response.status_code == 422


async def test_a_second_request_while_busy_gets_429_with_retry_after(
    result: InvestigationResult,
) -> None:
    started = asyncio.Event()
    release = asyncio.Event()
    seen: list[str] = []

    async def slow(alert: str) -> InvestigationResult:
        seen.append(alert)
        started.set()
        await release.wait()
        return result

    async with client_for(slow) as client:
        first = asyncio.create_task(client.post("/investigations", json={"alert": "a"}))
        async with asyncio.timeout(5):
            await started.wait()
        second = await client.post("/investigations", json={"alert": "b"})
        release.set()
        assert (await first).status_code == 200

    assert seen == ["a"]
    assert second.status_code == 429
    assert second.headers["retry-after"] == "30"
    assert second.json() == {
        "error": {"kind": "busy", "message": "an investigation is already running"}
    }


async def test_the_lock_is_released_after_a_failure(result: InvestigationResult) -> None:
    calls: list[str] = []

    async def flaky(alert: str) -> InvestigationResult:
        calls.append(alert)
        if len(calls) == 1:
            raise DiagnosisSchemaError("the model broke the diagnosis schema")
        return result

    async with client_for(flaky) as client:
        failed = await client.post("/investigations", json={"alert": "a"})
        passed = await client.post("/investigations", json={"alert": "b"})

    assert (failed.status_code, passed.status_code) == (502, 200)


@pytest.mark.parametrize(
    ("error", "status", "kind"),
    [
        (LLMConfigError("HOA_GEMMA_BASE_URL is not set"), 503, "setup_error"),
        (MCPSetupError("the MCP server could not be reached (ConnectError)"), 503, "setup_error"),
        (DiagnosisSchemaError("the model broke the diagnosis schema"), 502, "investigation_failed"),
    ],
)
async def test_failures_map_to_status_codes(error: Exception, status: int, kind: str) -> None:
    async def failing(alert: str) -> InvestigationResult:
        raise error

    async with client_for(failing) as client:
        response = await client.post("/investigations", json={"alert": ALERT})

    assert response.status_code == status
    assert response.json()["error"]["kind"] == kind


async def test_rate_limit_is_503_with_its_own_kind(
    rate_limit_error: openai.RateLimitError,
) -> None:
    async def limited(alert: str) -> InvestigationResult:
        raise rate_limit_error

    async with client_for(limited) as client:
        response = await client.post("/investigations", json={"alert": ALERT})

    assert response.status_code == 503
    assert response.json()["error"] == {
        "kind": "llm_rate_limited",
        "message": "the LLM rate limit was hit — retry later",
    }


async def test_upstream_error_text_stays_out_of_the_response() -> None:
    async def unreachable(alert: str) -> InvestigationResult:
        request = httpx.Request("POST", "http://vllm.internal:8000/v1/chat/completions")
        raise openai.APIConnectionError(
            message="cannot reach http://vllm.internal:8000/v1", request=request
        )

    async with client_for(unreachable) as client:
        response = await client.post("/investigations", json={"alert": ALERT})

    assert response.status_code == 502
    assert "vllm.internal" not in response.text


async def test_a_slow_investigation_times_out_with_504() -> None:
    async def hang(alert: str) -> InvestigationResult:
        await asyncio.sleep(10)
        raise AssertionError("must be cancelled")

    async with client_for(hang, timeout_seconds=0.05) as client:
        response = await client.post("/investigations", json={"alert": ALERT})

    assert response.status_code == 504
    assert response.json()["error"]["kind"] == "timeout"


async def test_health_check_does_not_investigate() -> None:
    async def never(alert: str) -> InvestigationResult:
        raise AssertionError("must not be called")

    async with client_for(never) as client:
        response = await client.get("/healthz")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


async def test_the_lock_is_released_after_a_timeout(result: InvestigationResult) -> None:
    calls: list[str] = []

    async def sometimes_hangs(alert: str) -> InvestigationResult:
        calls.append(alert)
        if len(calls) == 1:
            await asyncio.sleep(10)
        return result

    async with client_for(sometimes_hangs, timeout_seconds=0.05) as client:
        first = await client.post("/investigations", json={"alert": "a"})
        second = await client.post("/investigations", json={"alert": "b"})

    assert (first.status_code, second.status_code) == (504, 200)


async def test_the_timeout_cancels_nested_task_groups() -> None:
    cleaned_up = False

    async def with_children(alert: str) -> InvestigationResult:
        nonlocal cleaned_up
        try:
            async with anyio.create_task_group() as group:
                group.start_soon(anyio.sleep, 10)
                await anyio.sleep(10)
        finally:
            cleaned_up = True
        raise AssertionError("must be cancelled")

    async with client_for(with_children, timeout_seconds=0.05) as client:
        response = await client.post("/investigations", json={"alert": ALERT})

    assert response.status_code == 504
    assert cleaned_up


async def test_an_unclassified_error_is_a_500_with_only_its_type() -> None:
    async def crashing(alert: str) -> InvestigationResult:
        raise KeyError("secret http://vllm.internal")

    async with client_for(crashing) as client:
        response = await client.post("/investigations", json={"alert": ALERT})

    assert response.status_code == 500
    assert response.json() == {"error": {"kind": "internal_error", "message": "KeyError"}}


async def test_a_timeout_error_that_is_not_ours_is_a_500(
    caplog: pytest.LogCaptureFixture,
) -> None:
    async def leaking(alert: str) -> InvestigationResult:
        raise TimeoutError("inner deadline")

    async with client_for(leaking) as client:
        response = await client.post("/investigations", json={"alert": ALERT})

    assert response.status_code == 500
    assert response.json()["error"]["kind"] == "internal_error"
    logged = [r.exc_info[1] for r in caplog.records if r.exc_info and r.exc_info[1]]
    assert [error.args for error in logged] == [("inner deadline",)]


@pytest.mark.parametrize(
    "body",
    [{"alert": "   "}, {"alert": ALERT, "model": "gemini"}, {}],
    ids=["blank", "extra", "missing"],
)
async def test_blank_or_unknown_request_fields_are_rejected(body: dict[str, str]) -> None:
    async def never(alert: str) -> InvestigationResult:
        raise AssertionError("must not be called")

    async with client_for(never) as client:
        response = await client.post("/investigations", json=body)

    assert response.status_code == 422
