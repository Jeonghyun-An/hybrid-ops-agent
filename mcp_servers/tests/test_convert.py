from collections.abc import Callable
from datetime import datetime

import pytest
from kubernetes_asyncio.client import (
    CoreV1Event,
    V1ConfigMapEnvSource,
    V1ConfigMapKeySelector,
    V1Deployment,
    V1EnvFromSource,
    V1EnvVar,
    V1EnvVarSource,
    V1ObjectFieldSelector,
    V1ObjectMeta,
    V1ObjectReference,
    V1Pod,
    V1ReplicaSet,
    V1ResourceFieldSelector,
    V1SecretEnvSource,
    V1SecretKeySelector,
)

from hoa_mcp.k8s_read.budget import MAX_ENV_VARS
from hoa_mcp.k8s_read.convert import (
    deployment_view,
    env_view,
    event_summary,
    log_lines,
    needs_attention,
    pod_summary,
    redact,
)

MakePod = Callable[..., V1Pod]


def test_pod_summary_reports_image_pull_waiting_reason(make_pod: MakePod, now: datetime) -> None:
    pod = make_pod(
        phase="Pending",
        ready=False,
        waiting=("ImagePullBackOff", 'Back-off pulling image "hoa-demo:0.1.0-missing"'),
    )
    summary = pod_summary(pod, now)
    assert summary.phase == "Pending"
    assert summary.ready == "0/1"
    assert summary.waiting_reason == "ImagePullBackOff"
    assert "hoa-demo:0.1.0-missing" in summary.waiting_message


def test_pod_summary_reports_restarts_and_last_termination(
    make_pod: MakePod, now: datetime
) -> None:
    pod = make_pod(
        ready=False,
        restarts=3,
        waiting=("CrashLoopBackOff", "back-off 40s restarting failed container"),
        last_terminated=("Error", 1),
    )
    summary = pod_summary(pod, now)
    assert summary.restarts == 3
    assert summary.last_terminated_reason == "Error"
    assert summary.last_exit_code == 1


def test_first_crash_shows_before_any_restart(make_pod: MakePod, now: datetime) -> None:
    summary = pod_summary(make_pod(ready=False, terminated=("Error", 1)), now)
    assert summary.restarts == 0
    assert summary.last_terminated_reason == "Error"
    assert summary.last_exit_code == 1


def test_waiting_init_container_is_reported(make_pod: MakePod, now: datetime) -> None:
    pod = make_pod(phase="Pending", ready=False, init_waiting=("ErrImagePull", "init image"))
    assert pod_summary(pod, now).waiting_reason == "ErrImagePull"


def test_evicted_and_terminating_pods_are_marked(make_pod: MakePod, now: datetime) -> None:
    evicted = pod_summary(make_pod(phase="Failed", ready=False, reason="Evicted"), now)
    deleting = pod_summary(make_pod(deleting=True), now)
    assert evicted.reason == "Evicted"
    assert deleting.terminating is True
    assert needs_attention(evicted) and needs_attention(deleting)
    assert not needs_attention(pod_summary(make_pod(), now))


def test_pod_age_is_counted_from_creation(make_pod: MakePod, now: datetime) -> None:
    assert pod_summary(make_pod(age_seconds=90), now).age_seconds == 90


def test_long_waiting_message_is_clipped(make_pod: MakePod, now: datetime) -> None:
    summary = pod_summary(make_pod(waiting=("ErrImagePull", "x" * 1000)), now)
    assert len(summary.waiting_message) == 300
    assert summary.waiting_message.endswith("…")


def test_event_summary_names_the_involved_object(make_event: Callable[..., CoreV1Event]) -> None:
    summary = event_summary(make_event(message='Failed to pull image "hoa-demo:0.1.0-missing"'))
    assert summary.object == "Pod/orders-7d9f-abcde"
    assert summary.reason == "Failed"
    assert summary.last_seen == "2026-11-11T11:59:50+00:00"


def test_event_series_supplies_count_and_latest_time(
    make_event: Callable[..., CoreV1Event],
) -> None:
    summary = event_summary(make_event(seconds_ago=600, series_count=7))
    assert summary.count == 7
    assert summary.last_seen == "2026-11-11T12:00:00+00:00"


def test_event_without_any_timestamp_has_no_last_seen() -> None:
    event = CoreV1Event(
        metadata=V1ObjectMeta(name="e"),
        involved_object=V1ObjectReference(kind="Pod", name="p"),
        reason="Scheduled",
        message="ok",
    )
    assert event_summary(event).last_seen is None


@pytest.mark.parametrize(
    "name",
    [
        "DB_PASSWORD",
        "api_token",
        "MYSQL_PWD",
        "SMTP_PASSWD",
        "GPG_PASSPHRASE",
        "BASIC_AUTH",
        "SENTRY_DSN",
        "TLS_PRIVATE_PEM",
        "APP_CONNECTION_STRING",
    ],
)
def test_env_values_with_secret_like_names_are_masked(name: str) -> None:
    assert env_view(V1EnvVar(name=name, value="hunter2")).value == "***"


def test_ordinary_env_value_is_kept() -> None:
    assert env_view(V1EnvVar(name="HOA_DEMO_PORT", value="eighty")).value == "eighty"


def test_secrets_inside_values_are_redacted() -> None:
    value = "postgresql://app:pw123@db:5432/orders"
    assert env_view(V1EnvVar(name="DATABASE_URL", value=value)).value == (
        "postgresql://app:***@db:5432/orders"
    )
    assert redact("Bearer eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxIn0.c2lnbmF0dXJl") == "Bearer ***"
    assert redact("key -----BEGIN PRIVATE KEY-----\nMIIE\n-----END PRIVATE KEY----- ok") == (
        "key *** ok"
    )


def test_long_env_value_is_clipped() -> None:
    view = env_view(V1EnvVar(name="APP_CONFIG", value="{" + "x" * 5000 + "}"))
    assert len(view.value) == 300


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        (
            V1EnvVarSource(secret_key_ref=V1SecretKeySelector(name="db", key="password")),
            "secret:db/password",
        ),
        (
            V1EnvVarSource(config_map_key_ref=V1ConfigMapKeySelector(name="app", key="mode")),
            "configmap:app/mode",
        ),
        (
            V1EnvVarSource(field_ref=V1ObjectFieldSelector(field_path="metadata.name")),
            "field:metadata.name",
        ),
        (
            V1EnvVarSource(resource_field_ref=V1ResourceFieldSelector(resource="limits.cpu")),
            "resource:limits.cpu",
        ),
    ],
)
def test_env_from_a_reference_shows_only_the_reference(
    source: V1EnvVarSource, expected: str
) -> None:
    view = env_view(V1EnvVar(name="FROM_REF", value_from=source))
    assert view.value is None
    assert view.value_from == expected


def test_deployment_view_lists_owned_replica_sets_newest_first(
    make_deployment: Callable[..., V1Deployment], make_replica_set: Callable[..., V1ReplicaSet]
) -> None:
    replica_sets = [
        make_replica_set("orders-old", 1, "hoa-demo:0.1.0", ready=1),
        make_replica_set("orders-new", 2, "hoa-demo:0.1.0-missing", ready=0),
        make_replica_set("other", 9, "x", ready=1, owner_uid="someone-else"),
    ]
    view = deployment_view(make_deployment(), replica_sets)
    assert [rs.name for rs in view.replica_sets] == ["orders-new", "orders-old"]
    assert view.replica_sets[0].images == ["hoa-demo:0.1.0-missing"]
    assert view.unavailable_replicas == 1
    assert view.conditions[0].reason == "ReplicaSetUpdated"
    assert view.containers[0].limits == {"memory": "192Mi"}
    assert view.truncated is False


def test_deployment_view_caps_env_and_reports_truncation(
    make_deployment: Callable[..., V1Deployment],
) -> None:
    env = [V1EnvVar(name=f"VAR_{i}", value="v") for i in range(MAX_ENV_VARS + 5)]
    view = deployment_view(make_deployment(env), [])
    assert len(view.containers[0].env) == MAX_ENV_VARS
    assert view.truncated is True


def test_env_from_sources_show_their_names(make_deployment: Callable[..., V1Deployment]) -> None:
    sources = [
        V1EnvFromSource(config_map_ref=V1ConfigMapEnvSource(name="app-config")),
        V1EnvFromSource(secret_ref=V1SecretEnvSource(name="db"), prefix="DB_"),
    ]
    view = deployment_view(make_deployment(env_from=sources), [])
    assert view.containers[0].env_from == ["configmap:app-config", "secret:db (prefix DB_)"]


def test_log_lines_split_clip_and_redact() -> None:
    lines = log_lines("first\n" + "y" * 900 + "\nconnect to postgres://u:secret@db\n")
    assert lines[0] == "first"
    assert len(lines[1]) == 500
    assert lines[2] == "connect to postgres://u:***@db"
