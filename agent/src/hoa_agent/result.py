from collections.abc import Sequence

from langchain_core.messages import AIMessage, BaseMessage, ToolMessage
from pydantic import BaseModel

from hoa_agent.diagnosis import Diagnosis
from hoa_agent.graph import NOT_RUN, StopReason


class ToolStep(BaseModel):
    tool: str
    args: dict[str, object]
    output: str
    error: bool
    executed: bool


class Usage(BaseModel):
    model_calls: int
    input_tokens: int
    output_tokens: int
    total_tokens: int


class InvestigationResult(BaseModel):
    model: str
    alert: str
    diagnosis: Diagnosis
    stop_reason: StopReason
    steps: list[ToolStep]
    invalid_tool_calls: int
    usage: Usage
    elapsed_seconds: float


def text_of(message: ToolMessage) -> str:
    if isinstance(message.content, str):
        return message.content
    parts = [
        block.get("text", "") if isinstance(block, dict) else str(block)
        for block in message.content
    ]
    return "\n".join(part for part in parts if part)


def tool_steps(messages: Sequence[BaseMessage]) -> list[ToolStep]:
    requested = {
        call["id"]: call
        for message in messages
        if isinstance(message, AIMessage)
        for call in message.tool_calls
    }
    steps = []
    for message in messages:
        if isinstance(message, ToolMessage):
            call = requested.get(message.tool_call_id, {})
            steps.append(
                ToolStep(
                    tool=message.name or str(call.get("name", "")),
                    args=dict(call.get("args", {})),
                    output=text_of(message),
                    error=message.status == "error",
                    executed=message.artifact != NOT_RUN,
                )
            )
    return steps


def usage_of(messages: Sequence[BaseMessage]) -> Usage:
    replies = [m for m in messages if isinstance(m, AIMessage)]
    metered = [m.usage_metadata for m in replies if m.usage_metadata]
    return Usage(
        model_calls=len(replies),
        input_tokens=sum(u["input_tokens"] for u in metered),
        output_tokens=sum(u["output_tokens"] for u in metered),
        total_tokens=sum(u["total_tokens"] for u in metered),
    )


def build_result(
    messages: Sequence[BaseMessage],
    diagnosis: Diagnosis,
    stop_reason: StopReason,
    *,
    model: str,
    alert: str,
    elapsed_seconds: float,
) -> InvestigationResult:
    return InvestigationResult(
        model=model,
        alert=alert,
        diagnosis=diagnosis,
        stop_reason=stop_reason,
        steps=tool_steps(messages),
        invalid_tool_calls=sum(
            len(m.invalid_tool_calls) for m in messages if isinstance(m, AIMessage)
        ),
        usage=usage_of(messages),
        elapsed_seconds=round(elapsed_seconds, 2),
    )
