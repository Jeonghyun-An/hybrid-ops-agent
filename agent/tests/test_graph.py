from collections.abc import Callable

import pytest
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langchain_core.tools import BaseTool, ToolException, tool

from hoa_agent.diagnosis import Diagnosis
from hoa_agent.graph import (
    SKIPPED_TOOL_CALL,
    Budget,
    DiagnosisSchemaError,
    InvestigationState,
    build_graph,
    initial_state,
)
from hoa_agent.prompts import DIAGNOSE_PROMPT

pytestmark = pytest.mark.anyio

ALERT = "KubeDeploymentRolloutStuck — namespace=demo deployment=orders"


def demo_tools(calls: list[str]) -> list[BaseTool]:
    @tool
    def list_pods(namespace: str) -> str:
        """List the pods of a namespace."""
        calls.append(f"list_pods:{namespace}")
        return '{"pods": [{"name": "orders-1", "waiting_reason": "ImagePullBackOff"}]}'

    @tool
    def get_events(namespace: str) -> str:
        """List the recent events of a namespace."""
        calls.append(f"get_events:{namespace}")
        raise ToolException(f"namespace {namespace} is not allowed")

    return [list_pods, get_events]


async def investigate(model: BaseChatModel, calls: list[str], **budget: int) -> InvestigationState:
    graph = build_graph(model, demo_tools(calls), budget=Budget(**budget))
    return InvestigationState.model_validate(await graph.ainvoke(initial_state(ALERT)))


async def test_agent_runs_tools_until_the_model_answers_then_diagnoses(
    scripted_model: Callable[..., BaseChatModel],
    make_reply: Callable[..., AIMessage],
    make_tool_call: Callable[..., dict[str, object]],
    diagnosis: Diagnosis,
) -> None:
    model = scripted_model(
        [
            make_reply(make_tool_call("list_pods", {"namespace": "demo"}, "c1")),
            make_reply(text="orders cannot pull its image"),
        ]
    )
    calls: list[str] = []

    final = await investigate(model, calls)

    assert calls == ["list_pods:demo"]
    assert final.stop_reason == "answered"
    assert final.tool_calls == 1
    assert final.diagnosis == diagnosis
    tool_messages = [m for m in final.messages if isinstance(m, ToolMessage)]
    assert "ImagePullBackOff" in tool_messages[0].content
    second_request = model.investigate_requests[1]
    assert isinstance(second_request[-1], ToolMessage)


async def test_tool_errors_go_back_to_the_model_instead_of_stopping_the_graph(
    scripted_model: Callable[..., BaseChatModel],
    make_reply: Callable[..., AIMessage],
    make_tool_call: Callable[..., dict[str, object]],
) -> None:
    model = scripted_model(
        [
            make_reply(make_tool_call("get_events", {"namespace": "kube-system"}, "c1")),
            make_reply(text="I could not read the events"),
        ]
    )

    final = await investigate(model, [])

    error = next(m for m in final.messages if isinstance(m, ToolMessage))
    assert error.status == "error"
    assert "kube-system is not allowed" in error.content
    assert final.stop_reason == "answered"


async def test_tool_budget_stops_the_loop_and_answers_the_calls_it_skipped(
    scripted_model: Callable[..., BaseChatModel],
    make_reply: Callable[..., AIMessage],
    make_tool_call: Callable[..., dict[str, object]],
) -> None:
    model = scripted_model(
        [
            make_reply(make_tool_call("list_pods", {"namespace": "demo"}, f"c{i}"))
            for i in range(1, 4)
        ]
    )
    calls: list[str] = []

    final = await investigate(model, calls, max_tool_calls=2)

    assert calls == ["list_pods:demo", "list_pods:demo"]
    assert final.stop_reason == "tool_budget"
    request = model.diagnose_requests[0]
    skipped = request[-2]
    assert isinstance(skipped, ToolMessage)
    assert skipped.tool_call_id == "c3"
    assert skipped.content == SKIPPED_TOOL_CALL
    assert request[-1] == HumanMessage(DIAGNOSE_PROMPT)


async def test_token_budget_stops_the_loop_before_running_more_tools(
    scripted_model: Callable[..., BaseChatModel],
    make_reply: Callable[..., AIMessage],
    make_tool_call: Callable[..., dict[str, object]],
) -> None:
    model = scripted_model(
        [make_reply(make_tool_call("list_pods", {"namespace": "demo"}, "c1"), input_tokens=27_000)]
    )
    calls: list[str] = []

    final = await investigate(model, calls)

    assert calls == []
    assert final.stop_reason == "token_budget"
    assert final.context_tokens == 27_000


async def test_a_diagnosis_that_breaks_the_schema_fails_loudly(
    scripted_model: Callable[..., BaseChatModel],
    make_reply: Callable[..., AIMessage],
) -> None:
    model = scripted_model([make_reply(text="done")], diagnosis=None)

    with pytest.raises(DiagnosisSchemaError):
        await investigate(model, [])
