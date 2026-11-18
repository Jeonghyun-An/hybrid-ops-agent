from collections.abc import Mapping
from enum import StrEnum
from pathlib import Path

import yaml
from pydantic import BaseModel

DEFAULT_PORT = 8080


class SettingsError(Exception):
    pass


class Transport(StrEnum):
    STDIO = "stdio"
    HTTP = "http"


class KubeAuth(StrEnum):
    KUBECONFIG = "kubeconfig"
    IN_CLUSTER = "in-cluster"


class ServerSettings(BaseModel):
    # None이면 파드의 ServiceAccount 토큰으로 붙는다(in-cluster)
    kubeconfig: Path | None
    allowed_namespaces: tuple[str, ...]
    transport: Transport = Transport.STDIO
    port: int = DEFAULT_PORT
    allowed_hosts: tuple[str, ...] = ()


def context_count(kubeconfig: Path) -> int:
    try:
        data = yaml.safe_load(kubeconfig.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise SettingsError("HOA_MCP_KUBECONFIG is not valid YAML") from exc
    contexts = data.get("contexts") if isinstance(data, dict) else None
    return len(contexts) if isinstance(contexts, list) else 0


def choice[E: StrEnum](env: Mapping[str, str], name: str, kind: type[E], default: E) -> E:
    raw = env.get(name, "").strip() or default.value
    try:
        return kind(raw)
    except ValueError as exc:
        choices = ", ".join(member.value for member in kind)
        raise SettingsError(f"{name} must be one of {choices}, got {raw!r}") from exc


def split_list(raw: str) -> tuple[str, ...]:
    return tuple(item.strip() for item in raw.split(",") if item.strip())


def kubeconfig_path(env: Mapping[str, str], auth: KubeAuth) -> Path | None:
    raw = env.get("HOA_MCP_KUBECONFIG", "").strip()
    if auth is KubeAuth.IN_CLUSTER:
        if raw:
            raise SettingsError(
                "HOA_MCP_KUBECONFIG must be empty with HOA_MCP_KUBE_AUTH=in-cluster — "
                "pick one way to reach the cluster"
            )
        if not env.get("KUBERNETES_SERVICE_HOST", "").strip():
            raise SettingsError(
                "HOA_MCP_KUBE_AUTH=in-cluster only works inside a pod "
                "(KUBERNETES_SERVICE_HOST is not set)"
            )
        return None
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
    return kubeconfig


def port_number(env: Mapping[str, str]) -> int:
    raw = env.get("HOA_MCP_PORT", "").strip() or str(DEFAULT_PORT)
    if not raw.isdigit() or not 1 <= int(raw) <= 65535:
        raise SettingsError(f"HOA_MCP_PORT must be a port number, got {raw!r}")
    return int(raw)


def load_settings(env: Mapping[str, str]) -> ServerSettings:
    auth = choice(env, "HOA_MCP_KUBE_AUTH", KubeAuth, KubeAuth.KUBECONFIG)
    transport = choice(env, "HOA_MCP_TRANSPORT", Transport, Transport.STDIO)
    kubeconfig = kubeconfig_path(env, auth)
    namespaces = split_list(env.get("HOA_MCP_ALLOWED_NAMESPACES", "demo"))
    if not namespaces:
        raise SettingsError("HOA_MCP_ALLOWED_NAMESPACES is empty")
    hosts = split_list(env.get("HOA_MCP_ALLOWED_HOSTS", ""))
    # 허용 Host가 비면 HTTP 요청이 모두 421로 거절된다 — 시작할 때 알린다
    if transport is Transport.HTTP and not hosts:
        raise SettingsError("HOA_MCP_ALLOWED_HOSTS is required with HOA_MCP_TRANSPORT=http")
    return ServerSettings(
        kubeconfig=kubeconfig,
        allowed_namespaces=namespaces,
        transport=transport,
        port=port_number(env),
        allowed_hosts=hosts,
    )
