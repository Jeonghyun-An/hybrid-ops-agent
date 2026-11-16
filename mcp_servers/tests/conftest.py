from collections.abc import Callable
from datetime import UTC, datetime, timedelta

import pytest
from kubernetes_asyncio.client import (
    CoreV1Event,
    CoreV1EventSeries,
    V1Container,
    V1ContainerState,
    V1ContainerStateRunning,
    V1ContainerStateTerminated,
    V1ContainerStateWaiting,
    V1ContainerStatus,
    V1Deployment,
    V1DeploymentCondition,
    V1DeploymentSpec,
    V1DeploymentStatus,
    V1EnvFromSource,
    V1EnvVar,
    V1LabelSelector,
    V1ObjectMeta,
    V1ObjectReference,
    V1OwnerReference,
    V1Pod,
    V1PodSpec,
    V1PodStatus,
    V1PodTemplateSpec,
    V1ReplicaSet,
    V1ReplicaSetSpec,
    V1ReplicaSetStatus,
    V1ResourceRequirements,
)

NOW = datetime(2026, 11, 11, 12, 0, tzinfo=UTC)
DEPLOYMENT_UID = "uid-orders"


def container_status(
    name: str,
    *,
    ready: bool,
    restarts: int,
    waiting: tuple[str, str] | None,
    terminated: tuple[str, int] | None,
    last_terminated: tuple[str, int] | None,
) -> V1ContainerStatus:
    if waiting:
        state = V1ContainerState(
            waiting=V1ContainerStateWaiting(reason=waiting[0], message=waiting[1])
        )
    elif terminated:
        state = V1ContainerState(
            terminated=V1ContainerStateTerminated(reason=terminated[0], exit_code=terminated[1])
        )
    else:
        state = V1ContainerState(running=V1ContainerStateRunning(started_at=NOW))
    last_state = None
    if last_terminated:
        last_state = V1ContainerState(
            terminated=V1ContainerStateTerminated(
                reason=last_terminated[0], exit_code=last_terminated[1]
            )
        )
    return V1ContainerStatus(
        name=name,
        image="hoa-demo:0.1.0",
        image_id="",
        ready=ready,
        restart_count=restarts,
        state=state,
        last_state=last_state,
    )


def build_pod(
    name: str = "orders-7d9f-abcde",
    *,
    phase: str = "Running",
    ready: bool = True,
    restarts: int = 0,
    waiting: tuple[str, str] | None = None,
    terminated: tuple[str, int] | None = None,
    last_terminated: tuple[str, int] | None = None,
    init_waiting: tuple[str, str] | None = None,
    init_terminated: tuple[str, int] | None = None,
    reason: str | None = None,
    deleting: bool = False,
    age_seconds: int = 90,
) -> V1Pod:
    main = container_status(
        "app",
        ready=ready,
        restarts=restarts,
        waiting=waiting,
        terminated=terminated,
        last_terminated=last_terminated,
    )
    init = []
    if init_waiting or init_terminated:
        init = [
            container_status(
                "init",
                ready=False,
                restarts=0,
                waiting=init_waiting,
                terminated=init_terminated,
                last_terminated=None,
            )
        ]
    return V1Pod(
        metadata=V1ObjectMeta(
            name=name,
            creation_timestamp=NOW - timedelta(seconds=age_seconds),
            deletion_timestamp=NOW if deleting else None,
        ),
        spec=V1PodSpec(containers=[V1Container(name="app", image="hoa-demo:0.1.0")]),
        status=V1PodStatus(
            phase=phase,
            reason=reason,
            container_statuses=[main],
            init_container_statuses=init or None,
        ),
    )


def build_event(
    reason: str = "Failed",
    message: str = "Failed to pull image",
    *,
    object_name: str = "orders-7d9f-abcde",
    seconds_ago: int = 10,
    series_count: int | None = None,
) -> CoreV1Event:
    series = None
    if series_count is not None:
        series = CoreV1EventSeries(count=series_count, last_observed_time=NOW)
    return CoreV1Event(
        metadata=V1ObjectMeta(name=f"{object_name}.{reason}.{seconds_ago}"),
        involved_object=V1ObjectReference(kind="Pod", name=object_name),
        reason=reason,
        message=message,
        type="Warning",
        count=1,
        last_timestamp=NOW - timedelta(seconds=seconds_ago),
        series=series,
    )


def build_deployment(
    env: list[V1EnvVar] | None = None,
    *,
    env_from: list[V1EnvFromSource] | None = None,
    containers: int = 1,
) -> V1Deployment:
    specs = [
        V1Container(
            name="orders" if index == 0 else f"sidecar-{index}",
            image="hoa-demo:0.1.0-missing",
            env=env or [],
            env_from=env_from,
            resources=V1ResourceRequirements(requests={"cpu": "50m"}, limits={"memory": "192Mi"}),
        )
        for index in range(containers)
    ]
    return V1Deployment(
        metadata=V1ObjectMeta(name="orders", namespace="demo", uid=DEPLOYMENT_UID),
        spec=V1DeploymentSpec(
            replicas=1,
            selector=V1LabelSelector(match_labels={"app": "orders"}),
            template=V1PodTemplateSpec(spec=V1PodSpec(containers=specs)),
        ),
        status=V1DeploymentStatus(
            replicas=2,
            updated_replicas=1,
            ready_replicas=1,
            available_replicas=1,
            unavailable_replicas=1,
            conditions=[
                V1DeploymentCondition(
                    type="Progressing",
                    status="True",
                    reason="ReplicaSetUpdated",
                    message='ReplicaSet "orders-new" is progressing.',
                )
            ],
        ),
    )


def build_replica_set(
    name: str,
    revision: int,
    image: str,
    *,
    ready: int,
    owner_uid: str = DEPLOYMENT_UID,
) -> V1ReplicaSet:
    return V1ReplicaSet(
        metadata=V1ObjectMeta(
            name=name,
            annotations={"deployment.kubernetes.io/revision": str(revision)},
            owner_references=[
                V1OwnerReference(api_version="apps/v1", kind="Deployment", name="x", uid=owner_uid)
            ],
        ),
        spec=V1ReplicaSetSpec(
            selector=V1LabelSelector(match_labels={"app": "orders"}),
            template=V1PodTemplateSpec(
                spec=V1PodSpec(containers=[V1Container(name="orders", image=image)])
            ),
        ),
        status=V1ReplicaSetStatus(replicas=1, ready_replicas=ready),
    )


READ_ONLY_KUBECONFIG = """apiVersion: v1
kind: Config
clusters:
  - name: kind-hoa
    cluster:
      server: https://127.0.0.1:6443
users:
  - name: hoa-mcp-read
    user:
      token: not-a-real-token
contexts:
  - name: hoa-mcp-read@kind-hoa
    context:
      cluster: kind-hoa
      user: hoa-mcp-read
current-context: hoa-mcp-read@kind-hoa
"""


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture
def now() -> datetime:
    return NOW


@pytest.fixture
def kubeconfig_text() -> str:
    return READ_ONLY_KUBECONFIG


@pytest.fixture
def make_pod() -> Callable[..., V1Pod]:
    return build_pod


@pytest.fixture
def make_event() -> Callable[..., CoreV1Event]:
    return build_event


@pytest.fixture
def make_deployment() -> Callable[..., V1Deployment]:
    return build_deployment


@pytest.fixture
def make_replica_set() -> Callable[..., V1ReplicaSet]:
    return build_replica_set
