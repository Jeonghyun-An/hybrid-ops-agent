import logging
from collections.abc import Callable
from pathlib import Path

import pytest
from kubernetes_asyncio.client import CoreV1Event, V1Deployment, V1EnvVar, V1Pod, V1ReplicaSet
from mcp.server.fastmcp import FastMCP
from mcp.shared.memory import create_connected_server_and_client_session
from mcp.types import CallToolResult

from hoa_mcp.k8s_read.kube import KubeError
from hoa_mcp.k8s_read.server import build_server
from hoa_mcp.k8s_read.settings import ServerSettings

pytestmark = pytest.mark.anyio

TOOL_CALLS = {
    "list_pods": {},
    "get_events": {},
    "describe_deployment": {"name": "orders"},
    "get_pod_logs": {"pod": "p"},
}


class FakeKubeReader:
    def __init__(
        self,
        *,
        pods: list[V1Pod] | None = None,
        events: list[CoreV1Event] | None = None,
        deployment: V1Deployment | None = None,
        replica_sets: list[V1ReplicaSet] | None = None,
        log: str = "",
        error: Exception | None = None,
    ) -> None:
        self.pods = pods or []
        self.events = events or []
        self.deployment = deployment
        self.replica_sets = replica_sets or []
        self.log = log
        self.error = error
        self.calls: list[tuple[object, ...]] = []

    def _record(self, *call: object) -> None:
        self.calls.append(call)
        if self.error:
            raise self.error

    async def list_pods(self, namespace: str) -> list[V1Pod]:
        self._record("list_pods", namespace)
        return self.pods

    async def list_events(self, namespace: str, object_name: str | None) -> list[CoreV1Event]:
        self._record("list_events", namespace, object_name)
        return self.events

    async def read_deployment(self, namespace: str, name: str) -> V1Deployment | None:
        self._record("read_deployment", namespace, name)
        return self.deployment

    async def list_replica_sets(self, namespace: str, label_selector: str) -> list[V1ReplicaSet]:
        self._record("list_replica_sets", namespace, label_selector)
        return self.replica_sets

    async def read_pod_log(
        self,
        namespace: str,
        pod: str,
        *,
        container: str | None,
        previous: bool,
        tail_lines: int,
    ) -> str:
        self._record("read_pod_log", namespace, pod, container, previous, tail_lines)
        return self.log


def server_for(reader: FakeKubeReader) -> FastMCP:
    settings = ServerSettings(kubeconfig=Path("unused"), allowed_namespaces=("demo",))
    return build_server(reader, settings)


async def call(reader: FakeKubeReader, tool: str, arguments: dict[str, object]) -> CallToolResult:
    async with create_connected_server_and_client_session(server_for(reader)) as session:
        return await session.call_tool(tool, arguments)


async def test_server_exposes_four_read_only_tools() -> None:
    async with create_connected_server_and_client_session(server_for(FakeKubeReader())) as session:
        tools = await session.list_tools()
    assert {tool.name for tool in tools.tools} == set(TOOL_CALLS)
    assert all(tool.annotations and tool.annotations.readOnlyHint for tool in tools.tools)


async def test_list_pods_returns_structured_summaries_with_problems_first(
    make_pod: Callable[..., V1Pod],
) -> None:
    pods = [
        make_pod("a-healthy"),
        make_pod("z-broken", ready=False, waiting=("ImagePullBackOff", "Back-off pulling image")),
    ]
    result = await call(FakeKubeReader(pods=pods), "list_pods", {"namespace": "demo"})
    assert result.isError is False
    names = [p["name"] for p in result.structuredContent["pods"]]
    assert names == ["z-broken", "a-healthy"]
    assert result.structuredContent["pods"][0]["waiting_reason"] == "ImagePullBackOff"


@pytest.mark.parametrize("tool", list(TOOL_CALLS))
async def test_every_tool_refuses_namespaces_outside_the_allowlist(tool: str) -> None:
    reader = FakeKubeReader()
    result = await call(reader, tool, {"namespace": "kube-system", **TOOL_CALLS[tool]})
    assert result.isError is True
    assert "namespace not allowed: kube-system (allowed: demo)" in result.content[0].text
    assert reader.calls == []


async def test_names_that_are_not_kubernetes_names_are_rejected() -> None:
    reader = FakeKubeReader()
    result = await call(
        reader,
        "get_events",
        {"namespace": "demo", "object_name": "orders,involvedObject.kind=Pod"},
    )
    assert result.isError is True
    assert reader.calls == []


async def test_kubernetes_errors_become_tool_errors() -> None:
    reader = FakeKubeReader(error=KubeError(403, "pods is forbidden"))
    result = await call(reader, "list_pods", {"namespace": "demo"})
    assert result.isError is True
    assert "kubernetes API 403: pods is forbidden" in result.content[0].text


async def test_unexpected_failures_are_logged_and_reported_by_type_only(
    caplog: pytest.LogCaptureFixture,
) -> None:
    reader = FakeKubeReader(error=RuntimeError("connect to 10.1.2.3 failed"))
    with caplog.at_level(logging.ERROR, logger="hoa_mcp.k8s_read.server"):
        result = await call(reader, "list_pods", {"namespace": "demo"})
    assert result.isError is True
    assert "internal error in list_pods: RuntimeError" in result.content[0].text
    assert "10.1.2.3" not in result.content[0].text
    assert "tool list_pods failed" in caplog.text


async def test_get_events_returns_the_newest_events_and_marks_the_rest(
    make_event: Callable[..., CoreV1Event],
) -> None:
    events = [
        make_event("Old", seconds_ago=30),
        make_event("Newest", seconds_ago=5),
        make_event("Middle", seconds_ago=20),
    ]
    reader = FakeKubeReader(events=events)
    result = await call(
        reader, "get_events", {"namespace": "demo", "object_name": "orders-x", "limit": 2}
    )
    assert [e["reason"] for e in result.structuredContent["events"]] == ["Newest", "Middle"]
    assert result.structuredContent["truncated"] is True
    assert reader.calls == [("list_events", "demo", "orders-x")]


async def test_event_limit_above_50_is_rejected() -> None:
    result = await call(FakeKubeReader(), "get_events", {"namespace": "demo", "limit": 51})
    assert result.isError is True


async def test_describe_deployment_selects_replica_sets_by_labels_and_masks_env(
    make_deployment: Callable[..., V1Deployment], make_replica_set: Callable[..., V1ReplicaSet]
) -> None:
    deployment = make_deployment(env=[V1EnvVar(name="DB_PASSWORD", value="hunter2")])
    reader = FakeKubeReader(
        deployment=deployment,
        replica_sets=[make_replica_set("orders-new", 2, "hoa-demo:0.1.0-missing", ready=0)],
    )
    result = await call(reader, "describe_deployment", {"namespace": "demo", "name": "orders"})
    content = result.structuredContent
    assert content["containers"][0]["env"] == [
        {"name": "DB_PASSWORD", "value": "***", "value_from": None}
    ]
    assert content["replica_sets"][0]["images"] == ["hoa-demo:0.1.0-missing"]
    assert ("list_replica_sets", "demo", "app=orders") in reader.calls


async def test_describe_deployment_that_cannot_fit_is_a_tool_error(
    make_deployment: Callable[..., V1Deployment],
) -> None:
    env = [V1EnvVar(name=f"VAR_{i}", value="v" * 300) for i in range(40)]
    reader = FakeKubeReader(deployment=make_deployment(env, containers=3))
    result = await call(reader, "describe_deployment", {"namespace": "demo", "name": "orders"})
    assert result.isError is True
    assert "output stays above 12000 characters" in result.content[0].text


async def test_get_pod_logs_passes_previous_and_tail_lines() -> None:
    reader = FakeKubeReader(log="booting\nHOA_DEMO_PORT='eighty': invalid\n")
    result = await call(
        reader,
        "get_pod_logs",
        {"namespace": "demo", "pod": "inventory-x", "previous": True, "tail_lines": 50},
    )
    assert result.structuredContent["lines"] == ["booting", "HOA_DEMO_PORT='eighty': invalid"]
    assert reader.calls == [("read_pod_log", "demo", "inventory-x", None, True, 50)]


async def test_tail_lines_above_200_is_rejected() -> None:
    result = await call(
        FakeKubeReader(), "get_pod_logs", {"namespace": "demo", "pod": "p", "tail_lines": 500}
    )
    assert result.isError is True


async def test_large_logs_keep_the_newest_lines_and_report_truncation() -> None:
    log = "\n".join(f"{i:03d} " + "z" * 300 for i in range(200))
    result = await call(FakeKubeReader(log=log), "get_pod_logs", {"namespace": "demo", "pod": "p"})
    content = result.structuredContent
    assert content["truncated"] is True
    assert content["lines"][-1].startswith("199 ")
