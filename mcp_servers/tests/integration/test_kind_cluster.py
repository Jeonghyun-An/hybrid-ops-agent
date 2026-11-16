import json
import os
import subprocess
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from pathlib import Path

import pytest
import yaml
from mcp.server.fastmcp import FastMCP
from mcp.shared.memory import create_connected_server_and_client_session

from hoa_mcp.k8s_read.kube import ApiKubeReader
from hoa_mcp.k8s_read.server import build_server
from hoa_mcp.k8s_read.settings import ServerSettings

pytestmark = pytest.mark.integration

CONTEXT = "kind-hoa"
ROOT = Path(__file__).resolve().parents[3]
DEMO_DIR = ROOT / "deploy" / "kind" / "demo"
# 장애 대상의 정본은 평가 시나리오다 — 멤버 경계라 hoa_eval을 import하지 않고 YAML을 직접 읽는다
SCENARIO_DIR = ROOT / "eval" / "scenarios"
PULL_FAILURES = {"ErrImagePull", "ImagePullBackOff"}
WAIT_SECONDS = 120


def kubectl(*args: str) -> str:
    result = subprocess.run(
        ["kubectl", "--context", CONTEXT, *args],
        capture_output=True,
        text=True,
        timeout=240,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    return result.stdout


def read_only_kubectl(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["kubectl", "--kubeconfig", str(mcp_kubeconfig()), *args],
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )


def mcp_kubeconfig() -> Path:
    default = Path.home() / ".kube" / "hoa-kind-mcp-read.kubeconfig"
    path = Path(os.environ.get("HOA_MCP_KUBECONFIG", default))
    if not path.is_file():
        pytest.fail(f"{path} 가 없다 — 먼저 bash scripts/dev-cluster.sh up 을 실행한다")
    return path


def container_statuses(app: str) -> list[dict[str, object]]:
    pods = json.loads(kubectl("-n", "demo", "get", "pods", "-l", f"app={app}", "-o", "json"))
    return [s for pod in pods["items"] for s in pod["status"].get("containerStatuses", [])]


def waiting_reasons(app: str) -> set[str]:
    return {
        s["state"]["waiting"].get("reason", "")
        for s in container_statuses(app)
        if "waiting" in s.get("state", {})
    }


def max_restarts(app: str) -> int:
    return max((s.get("restartCount", 0) for s in container_statuses(app)), default=0)


def wait_for(description: str, condition: Callable[[], object]) -> None:
    deadline = time.monotonic() + WAIT_SECONDS
    while time.monotonic() < deadline:
        if condition():
            return
        time.sleep(3)
    pytest.fail(f"{WAIT_SECONDS}초 안에 {description} 상태가 되지 않았다")


@contextmanager
def injected(scenario: str) -> Iterator[None]:
    data = yaml.safe_load((SCENARIO_DIR / f"{scenario}.yaml").read_text(encoding="utf-8"))
    fault = data["fault"]
    kubectl(
        "-n",
        fault["namespace"],
        "patch",
        f"deployment/{fault['deployment']}",
        "--type",
        "strategic",
        "--patch-file",
        str(ROOT / fault["patch"]),
    )
    try:
        yield
    finally:
        kubectl("apply", "-f", str(DEMO_DIR))
        # 진행 기한(progressDeadlineSeconds)을 넘긴 장애도 되돌리도록
        # 새 ReplicaSet으로 다시 시작한다
        kubectl("-n", "demo", "rollout", "restart", "deployment")
        for name in ("inventory", "orders", "gateway"):
            kubectl("-n", "demo", "rollout", "status", f"deployment/{name}", "--timeout=180s")


@pytest.fixture
def server() -> FastMCP:
    kubeconfig = mcp_kubeconfig()
    settings = ServerSettings(kubeconfig=kubeconfig, allowed_namespaces=("demo",))
    return build_server(ApiKubeReader(kubeconfig), settings)


async def call(server: FastMCP, tool: str, arguments: dict[str, object]) -> dict[str, object]:
    async with create_connected_server_and_client_session(server) as session:
        result = await session.call_tool(tool, arguments)
    assert result.isError is False, result.content[0].text
    return result.structuredContent


def test_demo_app_answers_through_gateway_orders_and_inventory() -> None:
    body = json.loads(
        kubectl("get", "--raw", "/api/v1/namespaces/demo/services/gateway:http/proxy/api/orders/1")
    )
    assert body["order"]["sku"] == "SKU-1"
    assert body["stock"]["available"] == 10


@pytest.mark.anyio
async def test_three_demo_services_are_running_and_available(server: FastMCP) -> None:
    content = await call(server, "list_pods", {"namespace": "demo"})
    running = {p["name"].rsplit("-", 2)[0] for p in content["pods"] if p["phase"] == "Running"}
    assert running == {"gateway", "orders", "inventory"}
    for name in ("gateway", "orders", "inventory"):
        deployment = await call(server, "describe_deployment", {"namespace": "demo", "name": name})
        assert deployment["available_replicas"] == deployment["replicas"] == 1


@pytest.mark.anyio
async def test_image_pull_fault_shows_in_pods_events_and_replica_sets(server: FastMCP) -> None:
    with injected("image-pull"):
        wait_for("orders 이미지 내려받기 실패", lambda: waiting_reasons("orders") & PULL_FAILURES)
        pods = await call(server, "list_pods", {"namespace": "demo"})
        broken = [p for p in pods["pods"] if p["waiting_reason"] in PULL_FAILURES]
        assert broken[0]["name"].startswith("orders-")
        events = await call(
            server, "get_events", {"namespace": "demo", "object_name": broken[0]["name"]}
        )
        assert any("hoa-demo:0.1.0-missing" in e["message"] for e in events["events"])
        deployment = await call(
            server, "describe_deployment", {"namespace": "demo", "name": "orders"}
        )
        assert deployment["replica_sets"][0]["images"] == ["hoa-demo:0.1.0-missing"]
        assert deployment["available_replicas"] == 1


@pytest.mark.anyio
async def test_bad_config_fault_shows_in_previous_logs_and_env(server: FastMCP) -> None:
    with injected("bad-config"):
        wait_for("inventory 재시작", lambda: max_restarts("inventory") >= 1)
        pods = await call(server, "list_pods", {"namespace": "demo"})
        inventory_pods = [p for p in pods["pods"] if p["name"].startswith("inventory-")]
        crashing = max(inventory_pods, key=lambda p: p["restarts"])
        logs = await call(
            server,
            "get_pod_logs",
            {"namespace": "demo", "pod": crashing["name"], "previous": True},
        )
        assert any("HOA_DEMO_PORT='eighty'" in line for line in logs["lines"])
        deployment = await call(
            server, "describe_deployment", {"namespace": "demo", "name": "inventory"}
        )
        env = {var["name"]: var["value"] for var in deployment["containers"][0]["env"]}
        assert env["HOA_DEMO_PORT"] == "eighty"


@pytest.mark.anyio
async def test_namespace_outside_the_allowlist_is_rejected(server: FastMCP) -> None:
    async with create_connected_server_and_client_session(server) as session:
        result = await session.call_tool("list_pods", {"namespace": "kube-system"})
    assert result.isError is True


def test_read_only_account_cannot_read_secrets_or_other_namespaces() -> None:
    secrets = read_only_kubectl("-n", "demo", "get", "secrets")
    assert secrets.returncode != 0
    assert "forbidden" in secrets.stderr
    system_pods = read_only_kubectl("-n", "kube-system", "get", "pods")
    assert system_pods.returncode != 0
    assert "forbidden" in system_pods.stderr
    assert read_only_kubectl("-n", "demo", "get", "pods").returncode == 0
