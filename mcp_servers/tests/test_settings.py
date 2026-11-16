import pytest

from hoa_mcp.k8s_read.settings import SettingsError, load_settings


def test_load_settings_reads_kubeconfig_and_namespaces(tmp_path):
    kubeconfig = tmp_path / "read.kubeconfig"
    kubeconfig.write_text("apiVersion: v1\n")
    settings = load_settings(
        {"HOA_MCP_KUBECONFIG": str(kubeconfig), "HOA_MCP_ALLOWED_NAMESPACES": "demo, staging"}
    )
    assert settings.kubeconfig == kubeconfig
    assert settings.allowed_namespaces == ("demo", "staging")


def test_allowed_namespaces_default_to_demo(tmp_path):
    kubeconfig = tmp_path / "read.kubeconfig"
    kubeconfig.write_text("apiVersion: v1\n")
    assert load_settings({"HOA_MCP_KUBECONFIG": str(kubeconfig)}).allowed_namespaces == ("demo",)


def test_missing_kubeconfig_variable_is_an_error():
    with pytest.raises(SettingsError, match="HOA_MCP_KUBECONFIG is not set"):
        load_settings({})


def test_kubeconfig_file_must_exist(tmp_path):
    with pytest.raises(SettingsError, match="file not found"):
        load_settings({"HOA_MCP_KUBECONFIG": str(tmp_path / "missing.kubeconfig")})
