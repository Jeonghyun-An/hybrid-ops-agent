import json
import subprocess
import time
from collections.abc import Callable

from pydantic import BaseModel

from hoa_eval.scenario import REPO_ROOT, Fault, Symptom

CONTEXT = "kind-hoa"
DEMO_NAMESPACE = "demo"
DEMO_MANIFESTS = REPO_ROOT / "deploy" / "kind" / "demo"
DEMO_DEPLOYMENTS = ("inventory", "orders", "gateway")
KUBECTL_TIMEOUT_SECONDS = 240
POLL_SECONDS = 3.0
SETTLE_TIMEOUT_SECONDS = 120.0


class ClusterError(Exception):
    pass


class SymptomTimeout(Exception):
    pass


class ContainerStatus(BaseModel):
    restart_count: int
    waiting_reason: str | None


def container_statuses(pods_json: str) -> list[ContainerStatus]:
    pods = json.loads(pods_json)
    return [
        ContainerStatus(
            restart_count=status.get("restartCount", 0),
            waiting_reason=status.get("state", {}).get("waiting", {}).get("reason"),
        )
        for pod in pods.get("items", [])
        for status in pod.get("status", {}).get("containerStatuses") or []
    ]


def terminating_pods(pods_json: str) -> list[str]:
    pods = json.loads(pods_json).get("items", [])
    return [pod["metadata"]["name"] for pod in pods if pod["metadata"].get("deletionTimestamp")]


def symptom_met(statuses: list[ContainerStatus], symptom: Symptom) -> bool:
    if symptom.waiting_reasons and any(
        status.waiting_reason in symptom.waiting_reasons for status in statuses
    ):
        return True
    return symptom.min_restarts is not None and any(
        status.restart_count >= symptom.min_restarts for status in statuses
    )


class Kubectl:
    """관리자 컨텍스트를 늘 명시한다 — 개발 PC의 다른 클러스터를 건드리지 않게."""

    def __init__(self, context: str = CONTEXT) -> None:
        self.context = context

    def __call__(self, *args: str) -> str:
        result = subprocess.run(
            ["kubectl", "--context", self.context, *args],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=KUBECTL_TIMEOUT_SECONDS,
            check=False,
        )
        if result.returncode != 0:
            raise ClusterError(f"kubectl {' '.join(args)} failed: {result.stderr.strip()}")
        return result.stdout


class DemoCluster:
    def __init__(
        self,
        kubectl: Callable[..., str],
        *,
        sleep: Callable[[float], None] = time.sleep,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.kubectl = kubectl
        self.sleep = sleep
        self.clock = clock

    def inject(self, fault: Fault) -> None:
        self.kubectl(
            "-n",
            fault.namespace,
            "patch",
            f"deployment/{fault.deployment}",
            "--type",
            "strategic",
            "--patch-file",
            str(REPO_ROOT / fault.patch),
        )

    def reset(self) -> None:
        self.kubectl("apply", "-f", str(DEMO_MANIFESTS))
        # 진행 기한을 넘긴 장애도 되돌리도록 새 ReplicaSet으로 다시 시작한다(dev-cluster.sh reset)
        self.kubectl("-n", DEMO_NAMESPACE, "rollout", "restart", "deployment")
        for name in DEMO_DEPLOYMENTS:
            self.kubectl(
                "-n", DEMO_NAMESPACE, "rollout", "status", f"deployment/{name}", "--timeout=180s"
            )
        self.wait_settled()

    def wait_settled(self) -> None:
        """rollout status는 새 파드만 본다 — 종료 중인 옛 파드가 남으면 다음 회차 조사에 섞인다."""
        started = self.clock()
        while True:
            left = terminating_pods(self.kubectl("-n", DEMO_NAMESPACE, "get", "pods", "-o", "json"))
            if not left:
                return
            if self.clock() - started >= SETTLE_TIMEOUT_SECONDS:
                raise ClusterError(f"pods still terminating after reset: {', '.join(left)}")
            self.sleep(POLL_SECONDS)

    def wait_for(self, fault: Fault, symptom: Symptom) -> float:
        started = self.clock()
        while True:
            pods = self.kubectl(
                "-n", fault.namespace, "get", "pods", "-l", f"app={fault.deployment}", "-o", "json"
            )
            if symptom_met(container_statuses(pods), symptom):
                return round(self.clock() - started, 1)
            if self.clock() - started >= symptom.timeout_seconds:
                raise SymptomTimeout(
                    f"deployment/{fault.deployment} showed no symptom "
                    f"within {symptom.timeout_seconds}s"
                )
            self.sleep(POLL_SECONDS)
