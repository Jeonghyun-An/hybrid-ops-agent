import os
import time
from collections.abc import Mapping

from hoa_agent.graph import InvestigationState, build_graph, initial_state
from hoa_agent.llm import build_chat_model, load_profile
from hoa_agent.mcp_tools import k8s_read_tools
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
    except BaseExceptionGroup as group:
        # MCP 클라이언트의 anyio 작업 그룹이 그래프의 예외를 묶어 올린다 — 하나면 풀어 올린다
        raise sole_exception(group) from None
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
