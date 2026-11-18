import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
from mcp import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client


def entrypoint() -> str:
    path = shutil.which("hoa-mcp-k8s-read", path=str(Path(sys.executable).parent))
    assert path, "hoa-mcp-k8s-read 콘솔 스크립트가 없다 — uv sync --locked 뒤에 실행한다"
    return path


@pytest.mark.anyio
async def test_stdio_entrypoint_serves_the_four_tools(tmp_path: Path, kubeconfig_text: str) -> None:
    kubeconfig = tmp_path / "read.kubeconfig"
    kubeconfig.write_text(kubeconfig_text, encoding="utf-8")
    params = StdioServerParameters(
        command=entrypoint(), env={**os.environ, "HOA_MCP_KUBECONFIG": str(kubeconfig)}
    )
    async with stdio_client(params) as (read, write), ClientSession(read, write) as session:
        await session.initialize()
        tools = await session.list_tools()
    assert len(tools.tools) == 4


def test_entrypoint_without_kubeconfig_exits_2() -> None:
    env = {k: v for k, v in os.environ.items() if k != "HOA_MCP_KUBECONFIG"}
    result = subprocess.run([entrypoint()], env=env, capture_output=True, text=True, timeout=60)
    assert result.returncode == 2
    assert "HOA_MCP_KUBECONFIG is not set" in result.stderr


def test_http_entrypoint_without_allowed_hosts_exits_2(
    tmp_path: Path, kubeconfig_text: str
) -> None:
    kubeconfig = tmp_path / "read.kubeconfig"
    kubeconfig.write_text(kubeconfig_text, encoding="utf-8")
    env = {
        **{k: v for k, v in os.environ.items() if k != "HOA_MCP_ALLOWED_HOSTS"},
        "HOA_MCP_KUBECONFIG": str(kubeconfig),
        "HOA_MCP_TRANSPORT": "http",
    }
    result = subprocess.run([entrypoint()], env=env, capture_output=True, text=True, timeout=60)
    assert result.returncode == 2
    assert "HOA_MCP_ALLOWED_HOSTS is required" in result.stderr
