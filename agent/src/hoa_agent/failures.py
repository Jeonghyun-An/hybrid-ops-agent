from enum import StrEnum

import openai

from hoa_agent.graph import DiagnosisSchemaError
from hoa_agent.llm import LLMConfigError
from hoa_agent.mcp_tools import MCPSetupError

# 조사 함수가 낼 수 있는 실패 — CLI 종료 코드와 API 상태 코드가 같은 분류를 쓴다
KNOWN_FAILURES = (LLMConfigError, MCPSetupError, DiagnosisSchemaError, openai.OpenAIError)


class FailureKind(StrEnum):
    INVESTIGATION_FAILED = "investigation_failed"
    SETUP_ERROR = "setup_error"
    LLM_RATE_LIMITED = "llm_rate_limited"


EXIT_CODES = {
    FailureKind.INVESTIGATION_FAILED: 1,
    FailureKind.SETUP_ERROR: 2,
    FailureKind.LLM_RATE_LIMITED: 3,
}
HTTP_STATUSES = {
    FailureKind.INVESTIGATION_FAILED: 502,
    FailureKind.SETUP_ERROR: 503,
    FailureKind.LLM_RATE_LIMITED: 503,
}


def classify(exc: Exception) -> FailureKind:
    """KNOWN_FAILURES 하나를 분류한다 — 요청 한도는 OpenAIError의 하위라 먼저 본다."""
    if isinstance(exc, LLMConfigError | MCPSetupError):
        return FailureKind.SETUP_ERROR
    if isinstance(exc, openai.RateLimitError):
        return FailureKind.LLM_RATE_LIMITED
    return FailureKind.INVESTIGATION_FAILED


def operator_message(kind: FailureKind, exc: Exception) -> str:
    """운영자(CLI 표준오류)용 — 원문을 그대로 보인다."""
    if kind is FailureKind.SETUP_ERROR:
        return str(exc)
    if kind is FailureKind.LLM_RATE_LIMITED:
        return f"the LLM rate limit was hit — {exc}"
    return f"investigation failed — {type(exc).__name__}: {exc}"


def public_message(kind: FailureKind, exc: Exception) -> str:
    """API 응답용 — LLM·HTTP 오류 원문에는 내부 주소가 섞일 수 있다.
    우리가 쓴 설정 오류 문장만 그대로 보인다."""
    if kind is FailureKind.SETUP_ERROR:
        return str(exc)
    if kind is FailureKind.LLM_RATE_LIMITED:
        return "the LLM rate limit was hit — retry later"
    return f"investigation failed — {type(exc).__name__}"
