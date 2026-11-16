from pydantic import BaseModel


class PodSummary(BaseModel):
    name: str
    phase: str
    ready: str
    restarts: int
    waiting_reason: str | None = None
    waiting_message: str | None = None
    last_terminated_reason: str | None = None
    last_exit_code: int | None = None
    age_seconds: int | None = None


class PodList(BaseModel):
    namespace: str
    pods: list[PodSummary]
    truncated: bool = False


class EventSummary(BaseModel):
    type: str
    reason: str
    object: str
    message: str
    count: int
    last_seen: str | None = None


class EventList(BaseModel):
    namespace: str
    object_name: str | None = None
    events: list[EventSummary]
    truncated: bool = False


class EnvVarView(BaseModel):
    name: str
    value: str | None = None
    value_from: str | None = None


class ContainerView(BaseModel):
    name: str
    image: str
    env: list[EnvVarView]
    requests: dict[str, str]
    limits: dict[str, str]


class ConditionView(BaseModel):
    type: str
    status: str
    reason: str | None = None
    message: str | None = None


class ReplicaSetView(BaseModel):
    name: str
    revision: int
    images: list[str]
    replicas: int
    ready_replicas: int


class DeploymentView(BaseModel):
    namespace: str
    name: str
    replicas: int
    updated_replicas: int
    ready_replicas: int
    available_replicas: int
    unavailable_replicas: int
    conditions: list[ConditionView]
    containers: list[ContainerView]
    replica_sets: list[ReplicaSetView]
    truncated: bool = False


class PodLogs(BaseModel):
    namespace: str
    pod: str
    container: str | None = None
    previous: bool
    lines: list[str]
    truncated: bool = False
