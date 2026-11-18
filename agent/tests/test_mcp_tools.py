from pathlib import Path

import pytest

from hoa_agent.mcp_tools import MCPSetupError, k8s_read_connection


def test_server_gets_only_its_own_settings_not_the_llm_key(tmp_path: Path) -> None:
    kubeconfig = tmp_path / "read.kubeconfig"
    kubeconfig.write_text("contexts: []", encoding="utf-8")
    env = {"HOA_MCP_KUBECONFIG": str(kubeconfig), "GEMINI_API_KEY": "secret"}

    connection = k8s_read_connection(env)

    assert connection["transport"] == "stdio"
    assert Path(connection["command"]).stem == "hoa-mcp-k8s-read"
    assert connection["env"] == {
        "HOA_MCP_KUBECONFIG": str(kubeconfig),
        "HOA_MCP_ALLOWED_NAMESPACES": "demo",
    }


def test_missing_kubeconfig_is_reported_before_starting_the_server(tmp_path: Path) -> None:
    with pytest.raises(MCPSetupError, match="dev-cluster.sh up"):
        k8s_read_connection({"HOA_MCP_KUBECONFIG": str(tmp_path / "missing")})


def test_mcp_url_selects_streamable_http_and_needs_no_kubeconfig(tmp_path: Path) -> None:
    connection = k8s_read_connection(
        {
            "HOA_MCP_URL": " http://hoa-mcp-k8s-read.hoa-system.svc/mcp ",
            "HOA_MCP_KUBECONFIG": str(tmp_path / "missing"),
        }
    )

    assert connection == {
        "transport": "streamable_http",
        "url": "http://hoa-mcp-k8s-read.hoa-system.svc/mcp",
    }
