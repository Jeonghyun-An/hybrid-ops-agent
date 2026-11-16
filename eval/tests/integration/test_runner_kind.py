import json
import subprocess

import pytest

from hoa_eval.agent import AgentOutcome, AgentReport
from hoa_eval.cluster import CONTEXT, DemoCluster, Kubectl
from hoa_eval.runner import run_once
from hoa_eval.scenario import load_scenarios

pytestmark = pytest.mark.integration


def deployment_status(deployment: str) -> dict[str, int]:
    result = subprocess.run(
        [
            "kubectl",
            "--context",
            CONTEXT,
            "-n",
            "demo",
            "get",
            "deployment",
            deployment,
            "-o",
            "json",
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=60,
        check=True,
    )
    return json.loads(result.stdout)["status"]


def test_runner_injects_waits_scores_and_resets_on_kind() -> None:
    [scenario] = load_scenarios(["image-pull"])
    seen: list[str] = []

    def agent(alert: str, model: str) -> AgentOutcome:
        seen.append(alert)
        return AgentOutcome(
            report=AgentReport.model_validate(
                {
                    "model": "scripted",
                    "alert": alert,
                    "diagnosis": {
                        "cause_label": "image_pull_error",
                        "target": "demo/orders",
                        "evidence": [{"tool": "list_pods", "quote": "ImagePullBackOff"}],
                        "confidence": 0.9,
                        "summary_ko": "이미지를 내려받지 못한다.",
                    },
                    "stop_reason": "answered",
                    "steps": [
                        {
                            "tool": "list_pods",
                            "args": {"namespace": "demo"},
                            "output": '{"waiting_reason": "ImagePullBackOff"}',
                            "error": False,
                        }
                    ],
                    "invalid_tool_calls": 0,
                    "usage": {
                        "model_calls": 2,
                        "input_tokens": 100,
                        "output_tokens": 10,
                        "total_tokens": 110,
                    },
                    "elapsed_seconds": 0.1,
                }
            )
        )

    record = run_once(scenario, "scripted", 1, DemoCluster(Kubectl()), agent)

    assert seen == [scenario.alert]
    assert record.symptom_seconds is not None
    assert record.score is not None
    assert record.score.label_correct is True
    assert record.score.quotes_found == 1
    status = deployment_status("orders")
    assert status["updatedReplicas"] == status["readyReplicas"] == 1
