from kubernetes_asyncio.client import (
    CoreV1Event,
    V1EnvVar,
    V1EnvVarSource,
    V1ObjectMeta,
    V1ObjectReference,
    V1SecretKeySelector,
)

from hoa_mcp.k8s_read.convert import (
    deployment_view,
    env_view,
    event_summary,
    log_lines,
    pod_summary,
)


def test_pod_summary_reports_image_pull_waiting_reason(make_pod, now):
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


def test_pod_summary_reports_restarts_and_last_termination(make_pod, now):
    pod = make_pod(
        ready=False,
        restarts=3,
        waiting=("CrashLoopBackOff", "back-off 40s restarting failed container"),
        terminated=("Error", 1),
    )
    summary = pod_summary(pod, now)
    assert summary.restarts == 3
    assert summary.last_terminated_reason == "Error"
    assert summary.last_exit_code == 1


def test_pod_age_is_counted_from_creation(make_pod, now):
    assert pod_summary(make_pod(age_seconds=90), now).age_seconds == 90


def test_long_waiting_message_is_clipped(make_pod, now):
    summary = pod_summary(make_pod(waiting=("ErrImagePull", "x" * 1000)), now)
    assert len(summary.waiting_message) == 300
    assert summary.waiting_message.endswith("…")


def test_event_summary_names_the_involved_object(make_event):
    summary = event_summary(make_event(message='Failed to pull image "hoa-demo:0.1.0-missing"'))
    assert summary.object == "Pod/orders-7d9f-abcde"
    assert summary.reason == "Failed"
    assert summary.last_seen == "2026-11-11T11:59:50+00:00"


def test_event_without_any_timestamp_has_no_last_seen():
    event = CoreV1Event(
        metadata=V1ObjectMeta(name="e"),
        involved_object=V1ObjectReference(kind="Pod", name="p"),
        reason="Scheduled",
        message="ok",
    )
    assert event_summary(event).last_seen is None


def test_env_values_with_secret_like_names_are_masked():
    assert env_view(V1EnvVar(name="DB_PASSWORD", value="hunter2")).value == "***"
    assert env_view(V1EnvVar(name="api_token", value="abc")).value == "***"
    assert env_view(V1EnvVar(name="HOA_DEMO_PORT", value="eighty")).value == "eighty"


def test_env_from_a_secret_shows_only_the_reference():
    source = V1EnvVarSource(secret_key_ref=V1SecretKeySelector(name="db", key="password"))
    view = env_view(V1EnvVar(name="DB_PASSWORD", value_from=source))
    assert view.value is None
    assert view.value_from == "secret:db/password"


def test_deployment_view_lists_owned_replica_sets_newest_first(make_deployment, make_replica_set):
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


def test_log_lines_split_and_clip_long_lines():
    lines = log_lines("first\n" + "y" * 900 + "\nlast\n")
    assert lines[0] == "first"
    assert len(lines[1]) == 500
    assert lines[2] == "last"
