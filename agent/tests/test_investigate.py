from mcp.shared.exceptions import McpError
from mcp.types import ErrorData

from hoa_agent.investigate import sole_exception, surfaced
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
