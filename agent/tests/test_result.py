from collections.abc import Callable

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from hoa_agent.diagnosis import Diagnosis
from hoa_agent.graph import NOT_RUN, SKIPPED_TOOL_CALL
from hoa_agent.result import build_result


def test_result_pairs_each_tool_output_with_its_call_and_sums_usage(
    make_reply: Callable[..., AIMessage],
    make_tool_call: Callable[..., dict[str, object]],
    diagnosis: Diagnosis,
) -> None:
    first = make_reply(make_tool_call("list_pods", {"namespace": "demo"}, "c1"))
    first.invalid_tool_calls = [
        {
            "name": "get_events",
            "args": "{bad",
            "id": "c0",
            "error": "bad json",
            "type": "invalid_tool_call",
        }
    ]
    messages = [
        HumanMessage("alert"),
        first,
        ToolMessage('{"pods": []}', tool_call_id="c1", name="list_pods"),
        make_reply(text="done", input_tokens=2_000),
    ]

    result = build_result(
        messages,
        diagnosis,
        "answered",
        model="gemma4-26b-a4b",
        alert="alert",
        elapsed_seconds=3.456,
    )

    assert [(s.tool, s.args, s.output, s.error) for s in result.steps] == [
        ("list_pods", {"namespace": "demo"}, '{"pods": []}', False)
    ]
    assert result.invalid_tool_calls == 1
    assert result.usage.model_calls == 2
    assert result.usage.input_tokens == 3_000
    assert result.usage.total_tokens == 3_100
    assert result.elapsed_seconds == 3.46


def test_mcp_content_blocks_become_plain_text(
    make_reply: Callable[..., AIMessage],
    make_tool_call: Callable[..., dict[str, object]],
    diagnosis: Diagnosis,
) -> None:
    messages = [
        make_reply(make_tool_call("get_events", {"namespace": "demo"}, "c1")),
        ToolMessage(
            [{"type": "text", "text": "line one"}, {"type": "text", "text": "line two"}],
            tool_call_id="c1",
            name="get_events",
            status="error",
        ),
    ]

    result = build_result(messages, diagnosis, "answered", model="m", alert="a", elapsed_seconds=0)

    assert result.steps[0].output == "line one\nline two"
    assert result.steps[0].error is True
    assert result.steps[0].executed is True


def test_calls_the_graph_did_not_run_are_marked(
    make_reply: Callable[..., AIMessage],
    make_tool_call: Callable[..., dict[str, object]],
    diagnosis: Diagnosis,
) -> None:
    messages = [
        make_reply(make_tool_call("list_pods", {"namespace": "demo"}, "c1")),
        ToolMessage(
            SKIPPED_TOOL_CALL, tool_call_id="c1", name="list_pods", status="error", artifact=NOT_RUN
        ),
    ]

    result = build_result(
        messages, diagnosis, "tool_budget", model="m", alert="a", elapsed_seconds=0
    )

    assert result.steps[0].executed is False
