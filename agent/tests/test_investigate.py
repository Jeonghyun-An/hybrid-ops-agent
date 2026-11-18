import httpx
import pytest
from mcp.shared.exceptions import McpError
from mcp.types import ErrorData

from hoa_agent import investigate
from hoa_agent.investigate import run_investigation, sole_exception, surfaced
from hoa_agent.mcp_tools import MCPSetupError


def test_a_single_wrapped_exception_is_unwrapped() -> None:
    cause = ValueError("schema")
    group = ExceptionGroup("tasks", [ExceptionGroup("inner", [cause])])

    assert sole_exception(group) is cause


def test_several_exceptions_stay_grouped() -> None:
    group = ExceptionGroup("tasks", [ValueError("a"), KeyError("b")])

    assert sole_exception(group) is group


def test_an_mcp_server_that_dies_while_starting_is_a_setup_error() -> None:
    closed = McpError(ErrorData(code=-32000, message="Connection closed"))

    assert isinstance(surfaced(closed), MCPSetupError)
    assert isinstance(surfaced(ExceptionGroup("tasks", [closed])), MCPSetupError)


def test_other_errors_pass_through_unwrapped() -> None:
    cause = RuntimeError("model down")

    assert surfaced(ExceptionGroup("tasks", [cause])) is cause


def test_an_unreachable_mcp_url_is_a_setup_error_without_the_address() -> None:
    refused = httpx.ConnectError("connection refused: http://hoa-mcp-k8s-read.hoa-system.svc/mcp")

    for raised in (refused, ExceptionGroup("tasks", [refused])):
        error = surfaced(raised)
        assert isinstance(error, MCPSetupError)
        assert "ConnectError" in str(error)
        assert "hoa-system.svc" not in str(error)


def test_an_http_status_error_reports_the_code_but_not_the_address() -> None:
    request = httpx.Request("POST", "http://hoa-mcp-k8s-read.hoa-system.svc/mcp")
    response = httpx.Response(421, request=request)
    rejected = httpx.HTTPStatusError("misdirected", request=request, response=response)

    error = surfaced(rejected)

    assert isinstance(error, MCPSetupError)
    assert "HTTPStatusError 421" in str(error)
    assert "hoa-system.svc" not in str(error)


def test_several_http_failures_in_one_group_are_still_a_setup_error() -> None:
    group = ExceptionGroup("tasks", [httpx.ConnectError("a"), httpx.ReadTimeout("b")])

    error = surfaced(group)

    assert isinstance(error, MCPSetupError)
    assert "ConnectError" in str(error)


def test_a_mixed_group_stays_grouped() -> None:
    group = ExceptionGroup("tasks", [httpx.ConnectError("a"), KeyError("b")])

    assert surfaced(group) is group


def test_the_mcp_error_message_does_not_assume_a_child_process() -> None:
    closed = McpError(ErrorData(code=-32000, message="Connection closed"))

    assert "MCP server log" in str(surfaced(closed))


class BrokenSession:
    def __init__(self, leaf: Exception) -> None:
        self.leaf = leaf

    async def __aenter__(self) -> None:
        raise ExceptionGroup("tasks", [self.leaf])

    async def __aexit__(self, *exc: object) -> None:
        return None


def break_mcp(monkeypatch: pytest.MonkeyPatch, leaf: Exception) -> None:
    monkeypatch.setattr(investigate, "load_profile", lambda name, env: object())
    monkeypatch.setattr(investigate, "build_chat_model", lambda profile: object())
    monkeypatch.setattr(investigate, "k8s_read_tools", lambda env: BrokenSession(leaf))


@pytest.mark.anyio
async def test_a_new_setup_error_keeps_the_original_as_its_cause(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    refused = httpx.ConnectError("connection refused")
    break_mcp(monkeypatch, refused)

    with pytest.raises(MCPSetupError) as raised:
        await run_investigation("alert", "gemma", {})

    assert isinstance(raised.value.__cause__, ExceptionGroup)
    assert raised.value.__cause__.exceptions == (refused,)


@pytest.mark.anyio
async def test_an_unwrapped_leaf_keeps_its_own_cause(monkeypatch: pytest.MonkeyPatch) -> None:
    refused = httpx.ConnectError("connection refused")
    leaf = RuntimeError("model down")
    leaf.__cause__ = refused
    break_mcp(monkeypatch, leaf)

    with pytest.raises(RuntimeError) as raised:
        await run_investigation("alert", "gemma", {})

    assert raised.value is leaf
    assert raised.value.__cause__ is refused


@pytest.mark.anyio
async def test_an_unwrapped_leaf_without_a_cause_hides_the_group_context(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    break_mcp(monkeypatch, RuntimeError("model down"))

    with pytest.raises(RuntimeError) as raised:
        await run_investigation("alert", "gemma", {})

    assert raised.value.__cause__ is None
    assert raised.value.__suppress_context__
