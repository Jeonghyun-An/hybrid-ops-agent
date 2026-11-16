from pathlib import Path

import pytest

from hoa_mcp.k8s_read.settings import SettingsError, load_settings


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
