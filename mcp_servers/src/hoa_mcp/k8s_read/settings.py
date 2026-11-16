from collections.abc import Mapping
from pathlib import Path

import yaml
from pydantic import BaseModel


class SettingsError(Exception):
    pass


class ServerSettings(BaseModel):
    kubeconfig: Path
    allowed_namespaces: tuple[str, ...]


def context_count(kubeconfig: Path) -> int:
    try:
        data = yaml.safe_load(kubeconfig.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise SettingsError("HOA_MCP_KUBECONFIG is not valid YAML") from exc
    contexts = data.get("contexts") if isinstance(data, dict) else None
    return len(contexts) if isinstance(contexts, list) else 0


def load_settings(env: Mapping[str, str]) -> ServerSettings:
    raw = env.get("HOA_MCP_KUBECONFIG", "").strip()
    if not raw:
        raise SettingsError("HOA_MCP_KUBECONFIG is not set")
    kubeconfig = Path(raw).expanduser()
    if not kubeconfig.is_file():
        raise SettingsError(f"HOA_MCP_KUBECONFIG file not found: {kubeconfig}")
    # 컨텍스트가 여럿인 관리자 kubeconfig를 가리키면 엉뚱한 클러스터에 관리자 권한으로 붙는다
    contexts = context_count(kubeconfig)
    if contexts != 1:
        raise SettingsError(
            f"HOA_MCP_KUBECONFIG must hold exactly one context, found {contexts} — "
            "use the read-only kubeconfig written by scripts/dev-cluster.sh"
        )
    names = env.get("HOA_MCP_ALLOWED_NAMESPACES", "demo")
    namespaces = tuple(name.strip() for name in names.split(",") if name.strip())
    if not namespaces:
        raise SettingsError("HOA_MCP_ALLOWED_NAMESPACES is empty")
    return ServerSettings(kubeconfig=kubeconfig, allowed_namespaces=namespaces)
