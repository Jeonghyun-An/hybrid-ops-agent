import os
from collections.abc import Callable

import pytest
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, ToolMessage

from hoa_agent.graph import InvestigationState, build_graph, initial_state
from hoa_agent.mcp_tools import k8s_read_tools

pytestmark = [pytest.mark.integration, pytest.mark.anyio]


async def test_graph_runs_real_mcp_tools_against_kind(
    scripted_model: Callable[..., BaseChatModel],
    make_reply: Callable[..., AIMessage],
    make_tool_call: Callable[..., dict[str, object]],
) -> None:
    model = scripted_model(
        [
            make_reply(
                make_tool_call("list_pods", {"namespace": "demo"}, "c1"),
                make_tool_call("get_events", {"namespace": "kube-system"}, "c2"),
            ),
            make_reply(
                make_tool_call("describe_deployment", {"namespace": "demo", "name": "orders"}, "c3")
            ),
            make_reply(text="all three services look healthy"),
        ]
    )

    async with k8s_read_tools(os.environ) as tools:
        final = InvestigationState.model_validate(
            await build_graph(model, tools).ainvoke(initial_state("demo health check"))
        )

    results = {m.tool_call_id: m for m in final.messages if isinstance(m, ToolMessage)}
    assert {tool.name for tool in tools} == {
        "list_pods",
        "get_events",
        "describe_deployment",
        "get_pod_logs",
    }
    assert results["c1"].status == "success"
    assert "gateway-" in str(results["c1"].content)
    assert results["c2"].status == "error"
    assert "orders" in str(results["c3"].content)
    assert final.stop_reason == "answered"
    assert final.tool_calls == 3
