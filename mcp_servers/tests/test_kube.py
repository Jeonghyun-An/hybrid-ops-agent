import asyncio
import json
from pathlib import Path

import aiohttp
import pytest
from kubernetes_asyncio.client import ApiClient
from kubernetes_asyncio.client.exceptions import ApiException
from kubernetes_asyncio.config import ConfigException

from hoa_mcp.k8s_read import kube
from hoa_mcp.k8s_read.kube import ApiKubeReader, KubeError, decode_log


class FakeApiClient:
    def __init__(self) -> None:
        self.closed = False

    async def close(self) -> None:
        self.closed = True


def test_kube_error_takes_the_message_from_the_api_body() -> None:
    exc = ApiException(status=403, reason="Forbidden")
    exc.body = json.dumps({"message": 'secrets is forbidden: User "x" cannot list secrets'})
    error = KubeError.from_api(exc)
    assert error.status == 403
    assert str(error) == 'kubernetes API 403: secrets is forbidden: User "x" cannot list secrets'


def test_kube_error_falls_back_to_the_reason_without_a_body() -> None:
    error = KubeError.from_api(ApiException(status=404, reason="Not Found"))
    assert str(error) == "kubernetes API 404: Not Found"


def test_unauthorized_error_points_at_the_token_refresh_command() -> None:
    error = KubeError.from_api(ApiException(status=401, reason="Unauthorized"))
    assert "dev-cluster.sh mcp-kubeconfig" in str(error)


def test_log_bytes_that_are_not_utf8_are_replaced_not_fatal() -> None:
    assert decode_log(b"ok \xff end") == "ok � end"


@pytest.fixture
def fake_api(monkeypatch: pytest.MonkeyPatch) -> FakeApiClient:
    api = FakeApiClient()

    async def new_client(**_: object) -> FakeApiClient:
        return api

    monkeypatch.setattr(kube.config, "new_client_from_config", new_client)
    return api


@pytest.mark.anyio
async def test_connection_errors_hide_the_api_server_address(fake_api: FakeApiClient) -> None:
    async def refuse(api: ApiClient) -> None:
        raise aiohttp.ClientConnectionError("Cannot connect to host 10.1.2.3:6443")

    with pytest.raises(KubeError) as raised:
        await ApiKubeReader(Path("unused"))._call(refuse)
    assert str(raised.value) == "cluster unreachable"
    assert fake_api.closed is True


@pytest.mark.anyio
async def test_a_silent_cluster_times_out(
    fake_api: FakeApiClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(kube, "KUBE_TIMEOUT_SECONDS", 0.01)

    async def hang(api: ApiClient) -> None:
        await asyncio.sleep(1)

    with pytest.raises(KubeError, match="did not answer"):
        await ApiKubeReader(Path("unused"))._call(hang)
    assert fake_api.closed is True


@pytest.mark.anyio
async def test_unloadable_kubeconfig_is_a_kube_error(monkeypatch: pytest.MonkeyPatch) -> None:
    async def broken(**_: object) -> None:
        raise ConfigException("Invalid kube-config file.")

    monkeypatch.setattr(kube.config, "new_client_from_config", broken)

    async def never(api: ApiClient) -> None:
        raise AssertionError("must not be called")

    with pytest.raises(KubeError, match="kubeconfig could not be loaded"):
        await ApiKubeReader(Path("unused"))._call(never)
