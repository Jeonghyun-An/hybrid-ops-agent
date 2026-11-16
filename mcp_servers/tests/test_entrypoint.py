import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
from mcp import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client

ENTRYPOINT = shutil.which("hoa-mcp-k8s-read", path=str(Path(sys.executable).parent))


@pytest.mark.anyio
async def test_stdio_entrypoint_serves_the_four_tools(tmp_path):
    kubeconfig = tmp_path / "read.kubeconfig"
    kubeconfig.write_text("apiVersion: v1\n")
    params = StdioServerParameters(
        command=ENTRYPOINT, env={**os.environ, "HOA_MCP_KUBECONFIG": str(kubeconfig)}
    )
    async with stdio_client(params) as (read, write), ClientSession(read, write) as session:
        await session.initialize()
        tools = await session.list_tools()
    assert len(tools.tools) == 4


def test_entrypoint_without_kubeconfig_exits_2():
    env = {k: v for k, v in os.environ.items() if k != "HOA_MCP_KUBECONFIG"}
    result = subprocess.run([ENTRYPOINT], env=env, capture_output=True, text=True, timeout=60)
    assert result.returncode == 2
    assert "HOA_MCP_KUBECONFIG is not set" in result.stderr
