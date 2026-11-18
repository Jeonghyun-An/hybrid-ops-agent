from pathlib import Path

import pytest

from hoa_mcp.k8s_read.settings import KubeAuth, SettingsError, Transport, load_settings


def write_kubeconfig(tmp_path: Path, text: str) -> Path:
    kubeconfig = tmp_path / "read.kubeconfig"
    kubeconfig.write_text(text, encoding="utf-8")
    return kubeconfig


def test_load_settings_reads_kubeconfig_and_namespaces(
    tmp_path: Path, kubeconfig_text: str
) -> None:
    kubeconfig = write_kubeconfig(tmp_path, kubeconfig_text)
    settings = load_settings(
        {"HOA_MCP_KUBECONFIG": str(kubeconfig), "HOA_MCP_ALLOWED_NAMESPACES": "demo, staging"}
    )
    assert settings.kubeconfig == kubeconfig
    assert settings.allowed_namespaces == ("demo", "staging")


def test_allowed_namespaces_default_to_demo(tmp_path: Path, kubeconfig_text: str) -> None:
    kubeconfig = write_kubeconfig(tmp_path, kubeconfig_text)
    assert load_settings({"HOA_MCP_KUBECONFIG": str(kubeconfig)}).allowed_namespaces == ("demo",)


def test_empty_namespace_list_is_an_error(tmp_path: Path, kubeconfig_text: str) -> None:
    kubeconfig = write_kubeconfig(tmp_path, kubeconfig_text)
    with pytest.raises(SettingsError, match="HOA_MCP_ALLOWED_NAMESPACES is empty"):
        load_settings({"HOA_MCP_KUBECONFIG": str(kubeconfig), "HOA_MCP_ALLOWED_NAMESPACES": " , "})


def test_missing_kubeconfig_variable_is_an_error() -> None:
    with pytest.raises(SettingsError, match="HOA_MCP_KUBECONFIG is not set"):
        load_settings({})


def test_kubeconfig_file_must_exist(tmp_path: Path) -> None:
    with pytest.raises(SettingsError, match="file not found"):
        load_settings({"HOA_MCP_KUBECONFIG": str(tmp_path / "missing.kubeconfig")})


def test_kubeconfig_with_several_contexts_is_refused(tmp_path: Path, kubeconfig_text: str) -> None:
    second = kubeconfig_text.replace(
        "contexts:\n",
        "contexts:\n  - name: admin@company\n    context:\n      cluster: x\n      user: y\n",
    )
    kubeconfig = write_kubeconfig(tmp_path, second)
    with pytest.raises(SettingsError, match="exactly one context, found 2"):
        load_settings({"HOA_MCP_KUBECONFIG": str(kubeconfig)})


def test_kubeconfig_that_is_not_yaml_is_refused(tmp_path: Path) -> None:
    kubeconfig = write_kubeconfig(tmp_path, "clusters: [unclosed\n")
    with pytest.raises(SettingsError, match="not valid YAML"):
        load_settings({"HOA_MCP_KUBECONFIG": str(kubeconfig)})


def test_defaults_are_stdio_with_a_kubeconfig(tmp_path: Path, kubeconfig_text: str) -> None:
    kubeconfig = write_kubeconfig(tmp_path, kubeconfig_text)
    settings = load_settings({"HOA_MCP_KUBECONFIG": str(kubeconfig)})
    assert settings.transport is Transport.STDIO
    assert settings.port == 8080
    assert settings.allowed_hosts == ()


def test_http_transport_reads_port_and_allowed_hosts(tmp_path: Path, kubeconfig_text: str) -> None:
    kubeconfig = write_kubeconfig(tmp_path, kubeconfig_text)
    settings = load_settings(
        {
            "HOA_MCP_KUBECONFIG": str(kubeconfig),
            "HOA_MCP_TRANSPORT": "http",
            "HOA_MCP_PORT": "9000",
            "HOA_MCP_ALLOWED_HOSTS": "hoa-mcp-k8s-read.hoa-system.svc, 127.0.0.1:*",
        }
    )
    assert settings.transport is Transport.HTTP
    assert settings.port == 9000
    assert settings.allowed_hosts == ("hoa-mcp-k8s-read.hoa-system.svc", "127.0.0.1:*")


def test_http_transport_without_allowed_hosts_is_refused(
    tmp_path: Path, kubeconfig_text: str
) -> None:
    kubeconfig = write_kubeconfig(tmp_path, kubeconfig_text)
    with pytest.raises(SettingsError, match="HOA_MCP_ALLOWED_HOSTS is required"):
        load_settings({"HOA_MCP_KUBECONFIG": str(kubeconfig), "HOA_MCP_TRANSPORT": "http"})


@pytest.mark.parametrize(
    ("name", "value", "message"),
    [
        ("HOA_MCP_TRANSPORT", "sse", "HOA_MCP_TRANSPORT must be one of stdio, http"),
        ("HOA_MCP_KUBE_AUTH", "token", "HOA_MCP_KUBE_AUTH must be one of kubeconfig, in-cluster"),
        ("HOA_MCP_PORT", "eighty", "HOA_MCP_PORT must be a port number"),
        ("HOA_MCP_PORT", "70000", "HOA_MCP_PORT must be a port number"),
        ("HOA_MCP_PORT", "0", "HOA_MCP_PORT must be a port number"),
        ("HOA_MCP_PORT", "²", "HOA_MCP_PORT must be a port number"),
        ("HOA_MCP_HOST", "  ", "HOA_MCP_HOST must not be empty"),
    ],
)
def test_bad_choices_are_refused(
    tmp_path: Path, kubeconfig_text: str, name: str, value: str, message: str
) -> None:
    kubeconfig = write_kubeconfig(tmp_path, kubeconfig_text)
    with pytest.raises(SettingsError, match=message):
        load_settings({"HOA_MCP_KUBECONFIG": str(kubeconfig), name: value})


def test_in_cluster_auth_needs_no_kubeconfig() -> None:
    settings = load_settings(
        {"HOA_MCP_KUBE_AUTH": "in-cluster", "KUBERNETES_SERVICE_HOST": "kubernetes.default.svc"}
    )
    assert settings.kubeconfig is None
    assert settings.kube_auth is KubeAuth.IN_CLUSTER


def test_in_cluster_auth_with_a_kubeconfig_is_refused(tmp_path: Path, kubeconfig_text: str) -> None:
    kubeconfig = write_kubeconfig(tmp_path, kubeconfig_text)
    with pytest.raises(SettingsError, match="must be empty with HOA_MCP_KUBE_AUTH=in-cluster"):
        load_settings(
            {
                "HOA_MCP_KUBE_AUTH": "in-cluster",
                "HOA_MCP_KUBECONFIG": str(kubeconfig),
                "KUBERNETES_SERVICE_HOST": "kubernetes.default.svc",
            }
        )


def test_in_cluster_auth_outside_a_pod_is_refused() -> None:
    with pytest.raises(SettingsError, match="only works inside a pod"):
        load_settings({"HOA_MCP_KUBE_AUTH": "in-cluster"})


def test_bind_host_defaults_to_loopback_and_can_be_overridden(
    tmp_path: Path, kubeconfig_text: str
) -> None:
    kubeconfig = write_kubeconfig(tmp_path, kubeconfig_text)
    base = {"HOA_MCP_KUBECONFIG": str(kubeconfig)}
    assert load_settings(base).host == "127.0.0.1"
    assert load_settings({**base, "HOA_MCP_HOST": " 0.0.0.0 "}).host == "0.0.0.0"


def test_production_combination_reads_every_field() -> None:
    settings = load_settings(
        {
            "HOA_MCP_TRANSPORT": "http",
            "HOA_MCP_KUBE_AUTH": "in-cluster",
            "HOA_MCP_ALLOWED_HOSTS": "hoa-mcp-k8s-read.hoa-system.svc",
            "HOA_MCP_HOST": "0.0.0.0",
            "HOA_MCP_ALLOWED_NAMESPACES": "demo",
            "KUBERNETES_SERVICE_HOST": "kubernetes.default.svc",
        }
    )
    assert settings.transport is Transport.HTTP
    assert settings.kube_auth is KubeAuth.IN_CLUSTER
    assert settings.kubeconfig is None
    assert settings.allowed_hosts == ("hoa-mcp-k8s-read.hoa-system.svc",)
    assert settings.host == "0.0.0.0"
    assert settings.port == 8080
    assert settings.allowed_namespaces == ("demo",)


def test_whitespace_only_allowed_hosts_is_refused_with_http(
    tmp_path: Path, kubeconfig_text: str
) -> None:
    kubeconfig = write_kubeconfig(tmp_path, kubeconfig_text)
    with pytest.raises(SettingsError, match="HOA_MCP_ALLOWED_HOSTS is required"):
        load_settings(
            {
                "HOA_MCP_KUBECONFIG": str(kubeconfig),
                "HOA_MCP_TRANSPORT": "http",
                "HOA_MCP_ALLOWED_HOSTS": " , ",
            }
        )


def test_in_cluster_auth_with_a_blank_service_host_is_refused() -> None:
    with pytest.raises(SettingsError, match="only works inside a pod"):
        load_settings({"HOA_MCP_KUBE_AUTH": "in-cluster", "KUBERNETES_SERVICE_HOST": "  "})


def test_in_cluster_auth_treats_a_blank_kubeconfig_as_empty() -> None:
    settings = load_settings(
        {
            "HOA_MCP_KUBE_AUTH": "in-cluster",
            "HOA_MCP_KUBECONFIG": "  ",
            "KUBERNETES_SERVICE_HOST": "kubernetes.default.svc",
        }
    )
    assert settings.kubeconfig is None
