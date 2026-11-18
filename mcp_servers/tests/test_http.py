from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager

import httpx
import pytest
from kubernetes_asyncio.client import V1Pod
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client
from mcp.server.fastmcp import FastMCP

from hoa_mcp.k8s_read.server import build_server
from hoa_mcp.k8s_read.settings import KubeAuth, ServerSettings, Transport

pytestmark = pytest.mark.anyio

SERVICE_HOST = "hoa-mcp-k8s-read.hoa-system.svc"
TOOLS_LIST = {"jsonrpc": "2.0", "id": 1, "method": "tools/list"}
MCP_ACCEPT = {"accept": "application/json, text/event-stream"}


class NoClusterReader:
    """어느 메서드를 불러도 실패한다 — /healthz가 클러스터를 건드리지 않는지 본다."""

    def __getattr__(self, name: str) -> None:
        raise AssertionError(f"the health check must not call {name}")


class PodsReader:
    """list_pods만 답한다 — 이 테스트는 전송 계층을 본다."""

    def __init__(self, pods: list[V1Pod]) -> None:
        self.pods = pods

    async def list_pods(self, namespace: str) -> list[V1Pod]:
        return self.pods


def http_server(pods: list[V1Pod]) -> FastMCP:
    settings = ServerSettings(
        kubeconfig=None,
        kube_auth=KubeAuth.IN_CLUSTER,
        allowed_namespaces=("demo",),
        transport=Transport.HTTP,
        allowed_hosts=(SERVICE_HOST, "127.0.0.1:*"),
    )
    return build_server(PodsReader(pods), settings)


@asynccontextmanager
async def http_client(server: FastMCP, host: str) -> AsyncIterator[httpx.AsyncClient]:
    app = server.streamable_http_app()
    async with (
        server.session_manager.run(),
        httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url=f"http://{host}"
        ) as client,
    ):
        yield client


async def test_tools_answer_over_streamable_http(make_pod: Callable[..., V1Pod]) -> None:
    server = http_server([make_pod("orders-7d9f-abcde")])
    async with (
        http_client(server, SERVICE_HOST) as client,
        streamable_http_client(f"http://{SERVICE_HOST}/mcp", http_client=client) as (
            read,
            write,
            _,
        ),
        ClientSession(read, write) as session,
    ):
        await session.initialize()
        result = await session.call_tool("list_pods", {"namespace": "demo"})
    assert result.isError is False
    assert result.structuredContent["pods"][0]["name"] == "orders-7d9f-abcde"


async def test_unknown_host_header_is_refused() -> None:
    async with http_client(http_server([]), "evil.example") as client:
        response = await client.post("/mcp", json=TOOLS_LIST, headers=MCP_ACCEPT)
    assert response.status_code == 421


async def test_port_forwarded_host_is_allowed() -> None:
    async with http_client(http_server([]), "127.0.0.1:18080") as client:
        response = await client.post("/mcp", json=TOOLS_LIST, headers=MCP_ACCEPT)
    assert response.status_code == 200
    names = {tool["name"] for tool in response.json()["result"]["tools"]}
    assert names == {"list_pods", "get_events", "describe_deployment", "get_pod_logs"}


async def test_health_check_skips_the_host_check_and_the_cluster() -> None:
    settings = ServerSettings(
        kubeconfig=None,
        kube_auth=KubeAuth.IN_CLUSTER,
        allowed_namespaces=("demo",),
        transport=Transport.HTTP,
        allowed_hosts=(SERVICE_HOST,),
    )
    server = build_server(NoClusterReader(), settings)
    # kubelet 프로브의 Host는 파드 IP와 포트다
    async with http_client(server, "10.244.0.7:8080") as client:
        response = await client.get("/healthz")
    assert response.status_code == 200
    assert response.text == "ok"
