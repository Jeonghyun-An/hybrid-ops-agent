import json
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Protocol

from kubernetes_asyncio import client, config
from kubernetes_asyncio.client import ApiClient
from kubernetes_asyncio.client.exceptions import ApiException


class KubeError(Exception):
    def __init__(self, status: int, message: str) -> None:
        super().__init__(f"kubernetes API {status}: {message}")
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
        return cls(exc.status or 0, message)


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
        api = await config.new_client_from_config(
            config_file=str(self._kubeconfig), persist_config=False
        )
        try:
            return await request(api)
        except ApiException as exc:
            raise KubeError.from_api(exc) from exc
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
        return await self._call(
            lambda api: client.CoreV1Api(api).read_namespaced_pod_log(
                pod, namespace, container=container, previous=previous, tail_lines=tail_lines
            )
        )
