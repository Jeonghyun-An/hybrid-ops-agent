import os
import time
from collections.abc import Mapping

from mcp.shared.exceptions import McpError

from hoa_agent.graph import InvestigationState, build_graph, initial_state
from hoa_agent.llm import build_chat_model, load_profile
from hoa_agent.mcp_tools import MCPSetupError, k8s_read_tools
from hoa_agent.result import InvestigationResult, build_result


def sole_exception(group: BaseExceptionGroup) -> BaseException:
    leaves: list[BaseException] = []
    pending: list[BaseException] = [group]
    while pending:
        current = pending.pop()
        if isinstance(current, BaseExceptionGroup):
            pending.extend(current.exceptions)
        else:
            leaves.append(current)
    return leaves[0] if len(leaves) == 1 else group


def surfaced(exc: BaseException) -> BaseException:
    """도구 실패는 ToolNode가 메시지로 바꾸므로 세션 밖까지 온 McpError는 서버 시작 실패다."""
    cause = sole_exception(exc) if isinstance(exc, BaseExceptionGroup) else exc
    if isinstance(cause, McpError):
        return MCPSetupError(f"the MCP server stopped ({cause}) — see its message above")
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
    except (BaseExceptionGroup, McpError) as exc:
        # 작업 그룹이 묶어 올린 예외를 풀고, MCP 서버 시작 실패는 설정 오류로 바꾼다
        raise surfaced(exc) from None
    if final.diagnosis is None or final.stop_reason is None:
        raise RuntimeError("the investigation ended without a diagnosis")
    return build_result(
        final.messages,
        final.diagnosis,
        final.stop_reason,
        model=profile.model,
        alert=alert,
        elapsed_seconds=time.monotonic() - started,
    )
