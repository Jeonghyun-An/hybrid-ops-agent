import json
from collections.abc import Callable

import httpx
import pytest
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langchain_core.tools import BaseTool, ToolException, tool
from pydantic import SecretStr

from hoa_agent.diagnosis import Diagnosis
from hoa_agent.graph import (
    NOT_RUN,
    SKIPPED_TOOL_CALL,
    Budget,
    DiagnosisSchemaError,
    InvestigationState,
    build_graph,
    initial_state,
)
from hoa_agent.llm import ChatOpenAICompat
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
    skipped = model.diagnose_requests[0][-2]
    assert isinstance(skipped, ToolMessage)
    assert (skipped.tool_call_id, skipped.artifact) == ("c1", NOT_RUN)


async def test_context_is_the_last_request_not_the_sum_of_requests(
    scripted_model: Callable[..., BaseChatModel],
    make_reply: Callable[..., AIMessage],
    make_tool_call: Callable[..., dict[str, object]],
) -> None:
    model = scripted_model(
        [
            make_reply(
                make_tool_call("list_pods", {"namespace": "demo"}, "c1"), input_tokens=15_000
            ),
            make_reply(
                make_tool_call("list_pods", {"namespace": "demo"}, "c2"), input_tokens=15_000
            ),
            make_reply(text="done", input_tokens=15_500),
        ]
    )
    calls: list[str] = []

    final = await investigate(model, calls)

    assert calls == ["list_pods:demo", "list_pods:demo"]
    assert final.stop_reason == "answered"


async def test_tool_calls_with_broken_arguments_get_an_error_answer_and_a_retry(
    scripted_model: Callable[..., BaseChatModel],
    make_reply: Callable[..., AIMessage],
    make_tool_call: Callable[..., dict[str, object]],
) -> None:
    broken = make_reply()
    broken.invalid_tool_calls = [
        {
            "name": "list_pods",
            "args": "{namesp",
            "id": "bad1",
            "error": "bad json",
            "type": "invalid_tool_call",
        }
    ]
    model = scripted_model(
        [
            broken,
            make_reply(make_tool_call("list_pods", {"namespace": "demo"}, "c2")),
            make_reply(text="done"),
        ]
    )
    calls: list[str] = []

    final = await investigate(model, calls)

    answer = next(m for m in final.messages if isinstance(m, ToolMessage))
    assert answer.tool_call_id == "bad1"
    assert answer.status == "error"
    assert answer.content.startswith("Not run: the arguments were not valid JSON")
    assert isinstance(model.investigate_requests[1][-1], ToolMessage)
    assert calls == ["list_pods:demo"]
    assert final.tool_calls == 2
    assert final.stop_reason == "answered"


async def test_a_diagnosis_that_breaks_the_schema_fails_loudly(
    scripted_model: Callable[..., BaseChatModel],
    make_reply: Callable[..., AIMessage],
) -> None:
    model = scripted_model([make_reply(text="done")], diagnosis=None)

    with pytest.raises(DiagnosisSchemaError):
        await investigate(model, [])


async def test_an_empty_diagnosis_without_a_parsing_error_also_fails(
    scripted_model: Callable[..., BaseChatModel],
    make_reply: Callable[..., AIMessage],
) -> None:
    model = scripted_model([make_reply(text="done")], diagnosis=None, silent_failure=True)

    with pytest.raises(DiagnosisSchemaError):
        await investigate(model, [])


async def test_diagnosis_asks_for_json_schema_output_with_the_raw_reply(
    scripted_model: Callable[..., BaseChatModel],
    make_reply: Callable[..., AIMessage],
) -> None:
    model = scripted_model([make_reply(text="done")])

    await investigate(model, [])

    assert model.structured_kwargs == {"method": "json_schema", "include_raw": True}


def completion(content: str) -> dict[str, object]:
    message = {"role": "assistant", "content": content}
    return {
        "id": "r",
        "object": "chat.completion",
        "created": 0,
        "model": "m",
        "choices": [{"index": 0, "finish_reason": "stop", "message": message}],
        "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
    }


async def test_a_real_endpoint_answer_outside_the_schema_is_a_schema_error() -> None:
    outside = {
        "cause_label": "network_partition",
        "target": "demo/orders",
        "evidence": [{"tool": "list_pods", "quote": "x"}],
        "confidence": 0.5,
        "summary_ko": "x",
    }
    replies = [completion("orders cannot pull its image"), completion(json.dumps(outside))]

    def endpoint(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=replies.pop(0))

    model = ChatOpenAICompat(
        model="m",
        base_url="https://llm.test/v1",
        api_key=SecretStr("test-key"),
        max_retries=0,
        http_async_client=httpx.AsyncClient(transport=httpx.MockTransport(endpoint)),
    )

    with pytest.raises(DiagnosisSchemaError):
        await investigate(model, [])
