from collections.abc import Mapping
from pathlib import Path

from pydantic import BaseModel


class SettingsError(Exception):
    pass


class ServerSettings(BaseModel):
    kubeconfig: Path
    allowed_namespaces: tuple[str, ...]


def load_settings(env: Mapping[str, str]) -> ServerSettings:
    raw = env.get("HOA_MCP_KUBECONFIG", "").strip()
    if not raw:
        raise SettingsError("HOA_MCP_KUBECONFIG is not set")
    kubeconfig = Path(raw).expanduser()
    if not kubeconfig.is_file():
        raise SettingsError(f"HOA_MCP_KUBECONFIG file not found: {kubeconfig}")
    names = env.get("HOA_MCP_ALLOWED_NAMESPACES", "demo")
    namespaces = tuple(name.strip() for name in names.split(",") if name.strip())
    if not namespaces:
        raise SettingsError("HOA_MCP_ALLOWED_NAMESPACES is empty")
    return ServerSettings(kubeconfig=kubeconfig, allowed_namespaces=namespaces)
