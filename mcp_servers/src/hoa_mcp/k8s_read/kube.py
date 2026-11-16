import asyncio
import json
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Protocol

import aiohttp
from kubernetes_asyncio import client, config
from kubernetes_asyncio.client import ApiClient
from kubernetes_asyncio.client.exceptions import ApiException
from kubernetes_asyncio.config import ConfigException

KUBE_TIMEOUT_SECONDS = 20
# 로그는 tail_lines로 줄인 뒤에도 줄 하나가 거대할 수 있어 바이트로 한 번 더 막는다
MAX_LOG_BYTES = 256_000
EXPIRED_TOKEN_HINT = (
    "the read-only token may have expired — run: bash scripts/dev-cluster.sh mcp-kubeconfig"
)


class KubeError(Exception):
    def __init__(self, status: int, message: str) -> None:
        super().__init__(f"kubernetes API {status}: {message}" if status else message)
        self.status = status
        self.message = message

    @classmethod
    def from_api(cls, exc: ApiException) -> "KubeError":
        message = exc.reason or "error"
        if exc.body:
            try:
                message = json.loads(exc.body).get("message", message)
            except (ValueError, AttributeError):
                pass
        if exc.status == 401:
            message = f"{message} ({EXPIRED_TOKEN_HINT})"
        return cls(exc.status or 0, message)


def decode_log(raw: bytes) -> str:
    return raw.decode("utf-8", errors="replace")


class KubeReader(Protocol):
    async def list_pods(self, namespace: str) -> list[client.V1Pod]: ...

    async def list_events(
        self, namespace: str, object_name: str | None
    ) -> list[client.CoreV1Event]: ...

    async def read_deployment(self, namespace: str, name: str) -> client.V1Deployment: ...

    async def list_replica_sets(
        self, namespace: str, label_selector: str
    ) -> list[client.V1ReplicaSet]: ...

    async def read_pod_log(
        self,
        namespace: str,
        pod: str,
        *,
        container: str | None,
        previous: bool,
        tail_lines: int,
    ) -> str: ...


class ApiKubeReader:
    def __init__(self, kubeconfig: Path) -> None:
        self._kubeconfig = kubeconfig

    async def _call[T](self, request: Callable[[ApiClient], Awaitable[T]]) -> T:
        try:
            api = await config.new_client_from_config(
                config_file=str(self._kubeconfig), persist_config=False
            )
        except (ConfigException, OSError) as exc:
            raise KubeError(0, "kubeconfig could not be loaded") from exc
        try:
            async with asyncio.timeout(KUBE_TIMEOUT_SECONDS):
                return await request(api)
        except ApiException as exc:
            raise KubeError.from_api(exc) from exc
        except TimeoutError as exc:
            raise KubeError(0, f"cluster did not answer within {KUBE_TIMEOUT_SECONDS}s") from exc
        except aiohttp.ClientError as exc:
            # 연결 오류 메시지에는 API 서버 주소가 들어 있다 — 외부 LLM으로 내보내지 않는다
            raise KubeError(0, "cluster unreachable") from exc
        finally:
            await api.close()

    async def list_pods(self, namespace: str) -> list[client.V1Pod]:
        result = await self._call(lambda api: client.CoreV1Api(api).list_namespaced_pod(namespace))
        return result.items

    async def list_events(
        self, namespace: str, object_name: str | None
    ) -> list[client.CoreV1Event]:
        selector = f"involvedObject.name={object_name}" if object_name else None
        result = await self._call(
            lambda api: client.CoreV1Api(api).list_namespaced_event(
                namespace, field_selector=selector
            )
        )
        return result.items

    async def read_deployment(self, namespace: str, name: str) -> client.V1Deployment:
        return await self._call(
            lambda api: client.AppsV1Api(api).read_namespaced_deployment(name, namespace)
        )

    async def list_replica_sets(
        self, namespace: str, label_selector: str
    ) -> list[client.V1ReplicaSet]:
        result = await self._call(
            lambda api: client.AppsV1Api(api).list_namespaced_replica_set(
                namespace, label_selector=label_selector
            )
        )
        return result.items

    async def read_pod_log(
        self,
        namespace: str,
        pod: str,
        *,
        container: str | None,
        previous: bool,
        tail_lines: int,
    ) -> str:
        # 생성된 클라이언트는 본문을 JSON으로 풀었다가 str()로 바꿔
        # JSON 한 덩어리 로그를 망가뜨린다 — 원문 바이트를 그대로 받는다
        async def request(api: ApiClient) -> str:
            response = await client.CoreV1Api(api).read_namespaced_pod_log(
                pod,
                namespace,
                container=container,
                previous=previous,
                tail_lines=tail_lines,
                limit_bytes=MAX_LOG_BYTES,
                _preload_content=False,
            )
            return decode_log(await response.read())

        return await self._call(request)
