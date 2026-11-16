from pathlib import Path

import pytest
from kubernetes_asyncio.client import V1EnvVar
from mcp.shared.memory import create_connected_server_and_client_session
from mcp.types import CallToolResult

from hoa_mcp.k8s_read.kube import KubeError
from hoa_mcp.k8s_read.server import build_server
from hoa_mcp.k8s_read.settings import ServerSettings

pytestmark = pytest.mark.anyio


class FakeKubeReader:
    def __init__(
        self,
        *,
        pods=(),
        events=(),
        deployment=None,
        replica_sets=(),
        log="",
        error: KubeError | None = None,
    ) -> None:
        self.pods = list(pods)
        self.events = list(events)
        self.deployment = deployment
        self.replica_sets = list(replica_sets)
        self.log = log
        self.error = error
        self.calls: list[tuple] = []

    def _record(self, *call) -> None:
        self.calls.append(call)
        if self.error:
            raise self.error

    async def list_pods(self, namespace):
        self._record("list_pods", namespace)
        return self.pods

    async def list_events(self, namespace, object_name):
        self._record("list_events", namespace, object_name)
        return self.events

    async def read_deployment(self, namespace, name):
        self._record("read_deployment", namespace, name)
        return self.deployment

    async def list_replica_sets(self, namespace, label_selector):
        self._record("list_replica_sets", namespace, label_selector)
        return self.replica_sets

    async def read_pod_log(self, namespace, pod, *, container, previous, tail_lines):
        self._record("read_pod_log", namespace, pod, container, previous, tail_lines)
        return self.log


async def call(reader: FakeKubeReader, tool: str, arguments: dict) -> CallToolResult:
    settings = ServerSettings(kubeconfig=Path("unused"), allowed_namespaces=("demo",))
    async with create_connected_server_and_client_session(
        build_server(reader, settings)
    ) as session:
        return await session.call_tool(tool, arguments)


async def test_server_exposes_the_four_read_tools():
    settings = ServerSettings(kubeconfig=Path("unused"), allowed_namespaces=("demo",))
    async with create_connected_server_and_client_session(
        build_server(FakeKubeReader(), settings)
    ) as session:
        tools = await session.list_tools()
    assert {tool.name for tool in tools.tools} == {
        "list_pods",
        "get_events",
        "describe_deployment",
        "get_pod_logs",
    }


async def test_list_pods_returns_structured_summaries(make_pod):
    pod = make_pod(ready=False, waiting=("ImagePullBackOff", "Back-off pulling image"))
    result = await call(FakeKubeReader(pods=[pod]), "list_pods", {"namespace": "demo"})
    assert result.isError is False
    assert result.structuredContent["pods"][0]["waiting_reason"] == "ImagePullBackOff"


async def test_namespace_outside_the_allowlist_never_reaches_kubernetes():
    reader = FakeKubeReader()
    result = await call(reader, "list_pods", {"namespace": "kube-system"})
    assert result.isError is True
    assert "namespace not allowed: kube-system (allowed: demo)" in result.content[0].text
    assert reader.calls == []


async def test_kubernetes_errors_become_tool_errors():
    reader = FakeKubeReader(error=KubeError(403, "pods is forbidden"))
    result = await call(reader, "list_pods", {"namespace": "demo"})
    assert result.isError is True
    assert "kubernetes API 403: pods is forbidden" in result.content[0].text


async def test_get_events_returns_the_newest_events_up_to_the_limit(make_event):
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
    assert reader.calls == [("list_events", "demo", "orders-x")]


async def test_describe_deployment_selects_replica_sets_by_labels_and_masks_env(
    make_deployment, make_replica_set
):
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


async def test_get_pod_logs_passes_previous_and_tail_lines():
    reader = FakeKubeReader(log="booting\nHOA_DEMO_PORT='eighty': invalid\n")
    result = await call(
        reader,
        "get_pod_logs",
        {"namespace": "demo", "pod": "inventory-x", "previous": True, "tail_lines": 50},
    )
    assert result.structuredContent["lines"] == ["booting", "HOA_DEMO_PORT='eighty': invalid"]
    assert reader.calls == [("read_pod_log", "demo", "inventory-x", None, True, 50)]


async def test_tail_lines_above_200_is_rejected():
    result = await call(
        FakeKubeReader(), "get_pod_logs", {"namespace": "demo", "pod": "p", "tail_lines": 500}
    )
    assert result.isError is True


async def test_large_logs_keep_the_newest_lines_and_report_truncation():
    log = "\n".join(f"{i:03d} " + "z" * 300 for i in range(200))
    result = await call(FakeKubeReader(log=log), "get_pod_logs", {"namespace": "demo", "pod": "p"})
    content = result.structuredContent
    assert content["truncated"] is True
    assert content["lines"][-1].startswith("199 ")
