import shutil
import sys
from collections.abc import AsyncIterator, Mapping
from contextlib import asynccontextmanager
from pathlib import Path

from langchain_core.tools import BaseTool
from langchain_mcp_adapters.client import MultiServerMCPClient
from langchain_mcp_adapters.sessions import StdioConnection, StreamableHttpConnection
from langchain_mcp_adapters.tools import load_mcp_tools

SERVER_NAME = "k8s-read"
SERVER_COMMAND = "hoa-mcp-k8s-read"
DEFAULT_KUBECONFIG = Path.home() / ".kube" / "hoa-kind-mcp-read.kubeconfig"


class MCPSetupError(Exception):
    pass


def server_command() -> str:
    found = shutil.which(SERVER_COMMAND, path=str(Path(sys.executable).parent)) or shutil.which(
        SERVER_COMMAND
    )
    if found is None:
        raise MCPSetupError(f"{SERVER_COMMAND} not found — run uv sync --locked")
    return found


def k8s_read_connection(env: Mapping[str, str]) -> StdioConnection | StreamableHttpConnection:
    """HOA_MCP_URL이 있으면 클러스터 안 MCP 서버에 HTTP로 붙고(hoa serve, 포트포워드),
    없으면 서버를 stdio 자식 프로세스로 띄운다. 자식 프로세스에는 자기 설정만 넘긴다 —
    LLM API 키 같은 다른 환경변수는 물려주지 않는다."""
    url = env.get("HOA_MCP_URL", "").strip()
    if url:
        return {"transport": "streamable_http", "url": url}
    kubeconfig = Path(env.get("HOA_MCP_KUBECONFIG", "").strip() or DEFAULT_KUBECONFIG)
    if not kubeconfig.expanduser().is_file():
        raise MCPSetupError(
            f"MCP kubeconfig not found: {kubeconfig} — run bash scripts/dev-cluster.sh up"
        )
    return {
        "transport": "stdio",
        "command": server_command(),
        "args": [],
        "env": {
            "HOA_MCP_KUBECONFIG": str(kubeconfig),
            "HOA_MCP_ALLOWED_NAMESPACES": env.get("HOA_MCP_ALLOWED_NAMESPACES", "demo"),
        },
    }


@asynccontextmanager
async def k8s_read_tools(env: Mapping[str, str]) -> AsyncIterator[list[BaseTool]]:
    """조사 한 번 동안 MCP 세션 하나를 열어 두고 그 도구를 쓴다 — stdio면 서버 프로세스를 띄우고,
    HTTP면 이미 떠 있는 서버에 붙는다."""
    client = MultiServerMCPClient({SERVER_NAME: k8s_read_connection(env)})
    async with client.session(SERVER_NAME) as session:
        yield await load_mcp_tools(session)
