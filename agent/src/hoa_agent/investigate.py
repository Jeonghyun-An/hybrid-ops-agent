import os
import time
from collections.abc import Mapping

import httpx
from mcp.shared.exceptions import McpError

from hoa_agent.graph import DiagnosisSchemaError, InvestigationState, build_graph, initial_state
from hoa_agent.llm import build_chat_model, load_profile
from hoa_agent.mcp_tools import MCPSetupError, k8s_read_tools
from hoa_agent.result import InvestigationResult, build_result


def leaf_exceptions(group: BaseExceptionGroup) -> list[BaseException]:
    leaves: list[BaseException] = []
    pending: list[BaseException] = [group]
    while pending:
        current = pending.pop()
        if isinstance(current, BaseExceptionGroup):
            pending.extend(reversed(current.exceptions))
        else:
            leaves.append(current)
    return leaves


def sole_exception(group: BaseExceptionGroup) -> BaseException:
    leaves = leaf_exceptions(group)
    return leaves[0] if len(leaves) == 1 else group


def surfaced(exc: BaseException) -> BaseException:
    """도구 실패는 ToolNode가 메시지로 바꾸므로 세션 밖까지 온 MCP·HTTP 오류는 서버 연결 실패다."""
    cause = sole_exception(exc) if isinstance(exc, BaseExceptionGroup) else exc
    if isinstance(cause, BaseExceptionGroup):
        leaves = leaf_exceptions(cause)
        if all(isinstance(leaf, McpError | httpx.HTTPError) for leaf in leaves):
            cause = leaves[0]
    if isinstance(cause, McpError):
        return MCPSetupError(
            f"the MCP server closed the session ({cause}) — see the MCP server log"
        )
    if isinstance(cause, httpx.HTTPError):
        # 원문에는 MCP 서버 주소가 들어 있다 — 종류(와 상태 코드)만 알린다
        # (LLM 오류는 openai가 따로 감싼다)
        detail = type(cause).__name__
        if isinstance(cause, httpx.HTTPStatusError):
            detail += f" {cause.response.status_code}"
        return MCPSetupError(f"the MCP server could not be reached ({detail}) — check HOA_MCP_URL")
    return cause


async def run_investigation(
    alert: str, model_name: str, env: Mapping[str, str] | None = None
) -> InvestigationResult:
    settings = os.environ if env is None else env
    profile = load_profile(model_name, settings)
    model = build_chat_model(profile)
    started = time.monotonic()
    try:
        async with k8s_read_tools(settings) as tools:
            final = InvestigationState.model_validate(
                await build_graph(model, tools).ainvoke(initial_state(alert))
            )
    except (BaseExceptionGroup, McpError, httpx.HTTPError) as exc:
        # 작업 그룹이 묶어 올린 예외를 풀고, MCP 서버 시작 실패는 설정 오류로 바꾼다
        error = surfaced(exc)
        # 새로 만든 설정 오류는 원인을 잇고, 풀어 낸 잎 예외는 그대로 올린다
        raise error from (exc if isinstance(error, MCPSetupError) else None)
    if final.diagnosis is None or final.stop_reason is None:
        raise DiagnosisSchemaError("the investigation ended without a diagnosis")
    return build_result(
        final.messages,
        final.diagnosis,
        final.stop_reason,
        model=profile.model,
        alert=alert,
        elapsed_seconds=time.monotonic() - started,
    )
