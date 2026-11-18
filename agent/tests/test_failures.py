import httpx
import openai
import pytest

from hoa_agent.failures import (
    EXIT_CODES,
    HTTP_STATUSES,
    FailureKind,
    classify,
    operator_message,
    public_message,
)
from hoa_agent.graph import DiagnosisSchemaError
from hoa_agent.llm import LLMConfigError
from hoa_agent.mcp_tools import MCPSetupError


def connection_error() -> openai.APIConnectionError:
    request = httpx.Request("POST", "http://vllm.internal:8000/v1/chat/completions")
    return openai.APIConnectionError(
        message="cannot reach http://vllm.internal:8000/v1", request=request
    )


@pytest.mark.parametrize(
    ("error", "kind", "code", "status"),
    [
        (LLMConfigError("HOA_GEMMA_BASE_URL is not set"), FailureKind.SETUP_ERROR, 2, 503),
        (MCPSetupError("the MCP server stopped"), FailureKind.SETUP_ERROR, 2, 503),
        (
            DiagnosisSchemaError("the model broke the diagnosis schema"),
            FailureKind.INVESTIGATION_FAILED,
            1,
            502,
        ),
        (connection_error(), FailureKind.INVESTIGATION_FAILED, 1, 502),
    ],
)
def test_each_failure_has_one_kind_exit_code_and_status(
    error: Exception, kind: FailureKind, code: int, status: int
) -> None:
    assert classify(error) is kind
    assert EXIT_CODES[kind] == code
    assert HTTP_STATUSES[kind] == status


def test_rate_limit_is_its_own_kind_before_other_openai_errors(
    rate_limit_error: openai.RateLimitError,
) -> None:
    kind = classify(rate_limit_error)
    assert kind is FailureKind.LLM_RATE_LIMITED
    assert (EXIT_CODES[kind], HTTP_STATUSES[kind]) == (3, 503)


def test_operator_message_keeps_the_original_text() -> None:
    error = connection_error()
    assert operator_message(classify(error), error) == (
        "investigation failed — APIConnectionError: cannot reach http://vllm.internal:8000/v1"
    )


def test_public_message_hides_upstream_error_text() -> None:
    error = connection_error()
    assert public_message(classify(error), error) == "investigation failed — APIConnectionError"


def test_public_message_keeps_our_own_setup_hints() -> None:
    error = LLMConfigError("HOA_GEMMA_BASE_URL is not set — put it in .env")
    assert public_message(classify(error), error) == str(error)


def test_public_rate_limit_message_drops_the_provider_text(
    rate_limit_error: openai.RateLimitError,
) -> None:
    message = public_message(classify(rate_limit_error), rate_limit_error)
    assert message == "the LLM rate limit was hit — retry later"
