from collections.abc import Sequence
from typing import Annotated, Literal

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import (
    AIMessage,
    AnyMessage,
    BaseMessage,
    HumanMessage,
    SystemMessage,
    ToolMessage,
)
from langchain_core.tools import BaseTool
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages
from langgraph.graph.state import CompiledStateGraph
from langgraph.prebuilt import ToolNode
from pydantic import BaseModel, ValidationError

from hoa_agent.diagnosis import Diagnosis
from hoa_agent.prompts import DIAGNOSE_PROMPT, SYSTEM_PROMPT

StopReason = Literal["answered", "tool_budget", "token_budget"]
SKIPPED_TOOL_CALL = "Not run: the investigation budget is used up."
INVALID_TOOL_CALL = "Not run: the arguments were not valid JSON ({error}). Call the tool again."
# 실행하지 않은 도구 호출에 붙인 답의 표시 — 결과의 도구 기록에서 실행한 호출과 나눈다
NOT_RUN = {"not_run": True}


class DiagnosisSchemaError(Exception):
    pass


class Budget(BaseModel):
    """GPU 티어 Gemma의 32K 문맥 안에 진단까지 들어가도록 조사를 끊는 한도."""

    max_tool_calls: int = 6
    max_context_tokens: int = 26_000


class InvestigationState(BaseModel):
    alert: str
    messages: Annotated[list[AnyMessage], add_messages]
    tool_calls: int = 0
    context_tokens: int = 0
    stop_reason: StopReason | None = None
    diagnosis: Diagnosis | None = None


def initial_state(alert: str) -> InvestigationState:
    return InvestigationState(
        alert=alert, messages=[SystemMessage(SYSTEM_PROMPT), HumanMessage(alert)]
    )


def last_reply(messages: Sequence[BaseMessage]) -> AIMessage:
    return next(m for m in reversed(messages) if isinstance(m, AIMessage))


def stop_reason(state: InvestigationState, budget: Budget) -> StopReason | None:
    reply = last_reply(state.messages)
    if not reply.tool_calls and not reply.invalid_tool_calls:
        return "answered"
    if state.context_tokens >= budget.max_context_tokens:
        return "token_budget"
    if state.tool_calls > budget.max_tool_calls:
        return "tool_budget"
    return None


def invalid_call_answers(reply: AIMessage) -> list[ToolMessage]:
    """인자 JSON이 깨진 도구 호출에도 오류 답을 붙인다 — 모델이 고쳐 다시 부르게 한다."""
    return [
        ToolMessage(
            INVALID_TOOL_CALL.format(error=call.get("error") or "unparsable"),
            tool_call_id=call["id"],
            name=call.get("name") or "",
            status="error",
            artifact=NOT_RUN,
        )
        for call in reply.invalid_tool_calls
        if call.get("id")
    ]


def unanswered_calls(messages: Sequence[BaseMessage]) -> list[ToolMessage]:
    """예산 때문에 실행하지 않은 도구 호출에도 답을 붙인다 — 답 없는 tool_calls는 API가 거절한다."""
    index = max(i for i, m in enumerate(messages) if isinstance(m, AIMessage))
    reply = messages[index]
    answered = {m.tool_call_id for m in messages[index + 1 :] if isinstance(m, ToolMessage)}
    return [
        ToolMessage(
            SKIPPED_TOOL_CALL,
            tool_call_id=call["id"],
            name=call["name"],
            status="error",
            artifact=NOT_RUN,
        )
        for call in reply.tool_calls
        if call["id"] not in answered
    ]


def build_graph(
    model: BaseChatModel, tools: Sequence[BaseTool], *, budget: Budget | None = None
) -> CompiledStateGraph:
    limits = budget or Budget()
    investigator = model.bind_tools(tools)
    diagnoser = model.with_structured_output(Diagnosis, method="json_schema", include_raw=True)

    async def investigate(state: InvestigationState) -> dict[str, object]:
        reply = await investigator.ainvoke(state.messages)
        context = reply.usage_metadata["input_tokens"] if reply.usage_metadata else 0
        requested = len(reply.tool_calls) + len(reply.invalid_tool_calls)
        return {
            "messages": [reply, *invalid_call_answers(reply)],
            "tool_calls": state.tool_calls + requested,
            "context_tokens": max(context, state.context_tokens),
        }

    def route(state: InvestigationState) -> Literal["tools", "investigate", "diagnose"]:
        if stop_reason(state, limits) is not None:
            return "diagnose"
        return "tools" if last_reply(state.messages).tool_calls else "investigate"

    async def diagnose(state: InvestigationState) -> dict[str, object]:
        reason = stop_reason(state, limits) or "answered"
        pending = unanswered_calls(state.messages)
        request = [*state.messages, *pending, HumanMessage(DIAGNOSE_PROMPT)]
        try:
            answer = await diagnoser.ainvoke(request)
        except ValidationError as exc:
            # json_schema 방식은 응답을 받는 자리에서 바로 검증해 include_raw를 거치지 않는다
            raise DiagnosisSchemaError(
                f"the model broke the diagnosis schema: {exc.error_count()} errors"
            ) from exc
        if answer["parsing_error"] is not None or answer["parsed"] is None:
            raise DiagnosisSchemaError(
                f"the model broke the diagnosis schema: {answer['parsing_error']}"
            )
        return {
            "messages": [*pending, answer["raw"]],
            "stop_reason": reason,
            "diagnosis": answer["parsed"],
        }

    graph = StateGraph(InvestigationState)
    graph.add_node("investigate", investigate)
    graph.add_node("tools", ToolNode(tools, handle_tool_errors=True))
    graph.add_node("diagnose", diagnose)
    graph.add_edge(START, "investigate")
    graph.add_conditional_edges("investigate", route)
    graph.add_edge("tools", "investigate")
    graph.add_edge("diagnose", END)
    return graph.compile()
