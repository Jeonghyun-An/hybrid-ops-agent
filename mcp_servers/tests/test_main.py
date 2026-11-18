from pathlib import Path

import pytest
from mcp.server.fastmcp import FastMCP

from hoa_mcp.k8s_read import server


@pytest.fixture
def run_calls(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    calls: list[str] = []
    monkeypatch.setattr(FastMCP, "run", lambda self, transport: calls.append(transport))
    for name in ("HOA_MCP_TRANSPORT", "HOA_MCP_KUBE_AUTH", "HOA_MCP_KUBECONFIG"):
        monkeypatch.delenv(name, raising=False)
    return calls


def test_main_runs_stdio_by_default(
    run_calls: list[str], monkeypatch: pytest.MonkeyPatch, tmp_path: Path, kubeconfig_text: str
) -> None:
    kubeconfig = tmp_path / "read.kubeconfig"
    kubeconfig.write_text(kubeconfig_text, encoding="utf-8")
    monkeypatch.setenv("HOA_MCP_KUBECONFIG", str(kubeconfig))
    server.main()
    assert run_calls == ["stdio"]


def test_main_runs_streamable_http_for_the_http_transport(
    run_calls: list[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("HOA_MCP_TRANSPORT", "http")
    monkeypatch.setenv("HOA_MCP_KUBE_AUTH", "in-cluster")
    monkeypatch.setenv("HOA_MCP_ALLOWED_HOSTS", "hoa-mcp-k8s-read.hoa-system.svc")
    monkeypatch.setenv("KUBERNETES_SERVICE_HOST", "kubernetes.default.svc")
    checked: list[bool] = []
    monkeypatch.setattr(server, "check_in_cluster", lambda: checked.append(True))
    server.main()
    assert run_calls == ["streamable-http"]
    assert checked == [True]
