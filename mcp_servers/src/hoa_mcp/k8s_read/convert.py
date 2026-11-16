import re
from datetime import UTC, datetime

from kubernetes_asyncio.client import (
    CoreV1Event,
    V1Container,
    V1Deployment,
    V1EnvVar,
    V1EnvVarSource,
    V1Pod,
    V1ReplicaSet,
)

from hoa_mcp.k8s_read.budget import MAX_LINE_CHARS, MAX_MESSAGE_CHARS, clip
from hoa_mcp.k8s_read.models import (
    ConditionView,
    ContainerView,
    DeploymentView,
    EnvVarView,
    EventSummary,
    PodSummary,
    ReplicaSetView,
)

SECRET_LIKE = re.compile(r"PASSWORD|SECRET|TOKEN|KEY|CREDENTIAL", re.IGNORECASE)
MASK = "***"
REVISION_ANNOTATION = "deployment.kubernetes.io/revision"
NEVER = datetime.min.replace(tzinfo=UTC)


def pod_summary(pod: V1Pod, now: datetime) -> PodSummary:
    statuses = pod.status.container_statuses or []
    waiting = next((s.state.waiting for s in statuses if s.state and s.state.waiting), None)
    last = next(
        (s.last_state.terminated for s in statuses if s.last_state and s.last_state.terminated),
        None,
    )
    created = pod.metadata.creation_timestamp
    return PodSummary(
        name=pod.metadata.name,
        phase=pod.status.phase or "Unknown",
        ready=f"{sum(1 for s in statuses if s.ready)}/{len(pod.spec.containers)}",
        restarts=sum(s.restart_count or 0 for s in statuses),
        waiting_reason=waiting.reason if waiting else None,
        waiting_message=clip(waiting.message, MAX_MESSAGE_CHARS)
        if waiting and waiting.message
        else None,
        last_terminated_reason=last.reason if last else None,
        last_exit_code=last.exit_code if last else None,
        age_seconds=int((now - created).total_seconds()) if created else None,
    )


def event_time(event: CoreV1Event) -> datetime:
    return event.last_timestamp or event.event_time or event.metadata.creation_timestamp or NEVER


def event_summary(event: CoreV1Event) -> EventSummary:
    involved = event.involved_object
    seen = event_time(event)
    return EventSummary(
        type=event.type or "",
        reason=event.reason or "",
        object=f"{involved.kind}/{involved.name}",
        message=clip(event.message or "", MAX_MESSAGE_CHARS),
        count=event.count or 1,
        last_seen=None if seen == NEVER else seen.isoformat(),
    )


def source_ref(source: V1EnvVarSource) -> str:
    if source.secret_key_ref is not None:
        return f"secret:{source.secret_key_ref.name}/{source.secret_key_ref.key}"
    if source.config_map_key_ref is not None:
        return f"configmap:{source.config_map_key_ref.name}/{source.config_map_key_ref.key}"
    if source.field_ref is not None:
        return f"field:{source.field_ref.field_path}"
    if source.resource_field_ref is not None:
        return f"resource:{source.resource_field_ref.resource}"
    return "other"


def env_view(var: V1EnvVar) -> EnvVarView:
    if var.value_from is not None:
        return EnvVarView(name=var.name, value_from=source_ref(var.value_from))
    if var.value is not None and SECRET_LIKE.search(var.name):
        return EnvVarView(name=var.name, value=MASK)
    return EnvVarView(name=var.name, value=var.value)


def container_view(container: V1Container) -> ContainerView:
    resources = container.resources
    return ContainerView(
        name=container.name,
        image=container.image or "",
        env=[env_view(var) for var in container.env or []],
        requests=dict(resources.requests or {}) if resources else {},
        limits=dict(resources.limits or {}) if resources else {},
    )


def revision(replica_set: V1ReplicaSet) -> int:
    value = (replica_set.metadata.annotations or {}).get(REVISION_ANNOTATION, "0")
    return int(value) if value.isdigit() else 0


def replica_set_view(replica_set: V1ReplicaSet) -> ReplicaSetView:
    return ReplicaSetView(
        name=replica_set.metadata.name,
        revision=revision(replica_set),
        images=[c.image or "" for c in replica_set.spec.template.spec.containers],
        replicas=replica_set.status.replicas or 0,
        ready_replicas=replica_set.status.ready_replicas or 0,
    )


def deployment_view(deployment: V1Deployment, replica_sets: list[V1ReplicaSet]) -> DeploymentView:
    uid = deployment.metadata.uid
    owned = [
        rs
        for rs in replica_sets
        if any(ref.uid == uid for ref in rs.metadata.owner_references or [])
    ]
    status = deployment.status
    return DeploymentView(
        namespace=deployment.metadata.namespace,
        name=deployment.metadata.name,
        replicas=deployment.spec.replicas or 0,
        updated_replicas=status.updated_replicas or 0,
        ready_replicas=status.ready_replicas or 0,
        available_replicas=status.available_replicas or 0,
        unavailable_replicas=status.unavailable_replicas or 0,
        conditions=[
            ConditionView(
                type=c.type,
                status=c.status,
                reason=c.reason,
                message=clip(c.message, MAX_MESSAGE_CHARS) if c.message else None,
            )
            for c in status.conditions or []
        ],
        containers=[container_view(c) for c in deployment.spec.template.spec.containers],
        replica_sets=[replica_set_view(rs) for rs in sorted(owned, key=revision, reverse=True)],
    )


def log_lines(text: str) -> list[str]:
    return [clip(line, MAX_LINE_CHARS) for line in text.splitlines()]
