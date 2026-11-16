from collections.abc import Callable

import pytest

from hoa_eval.agent import AgentReport
from hoa_eval.scenario import SCENARIO_DIR, Scenario, load_scenario

EVENTS_OUTPUT = (
    '{"events": [{"reason": "Failed", "message": "Failed to pull image '
    '\\"hoa-demo:0.1.0-missing\\": not found"}]}'
)


def build_report(
    *,
    cause_label: str = "image_pull_error",
    target: str = "demo/orders",
    quotes: tuple[str, ...] = ('Failed to pull image "hoa-demo:0.1.0-missing"',),
    model: str = "gemma4-26b-a4b",
) -> AgentReport:
    return AgentReport.model_validate(
        {
            "model": model,
            "alert": "orders rollout stuck",
            "diagnosis": {
                "cause_label": cause_label,
                "target": target,
                "evidence": [{"tool": "get_events", "quote": quote} for quote in quotes],
                "confidence": 0.9,
                "summary_ko": "이미지를 내려받지 못한다.",
            },
            "stop_reason": "answered",
            "steps": [
                {
                    "tool": "get_events",
                    "args": {"namespace": "demo"},
                    "output": EVENTS_OUTPUT,
                    "error": False,
                },
                {
                    "tool": "get_pod_logs",
                    "args": {"namespace": "demo", "pod": "x"},
                    "output": "Error: pod x not found",
                    "error": True,
                },
            ],
            "invalid_tool_calls": 1,
            "usage": {
                "model_calls": 3,
                "input_tokens": 4_000,
                "output_tokens": 300,
                "total_tokens": 4_300,
            },
            "elapsed_seconds": 6.5,
        }
    )


@pytest.fixture
def make_report() -> Callable[..., AgentReport]:
    return build_report


@pytest.fixture
def image_pull() -> Scenario:
    return load_scenario(SCENARIO_DIR / "image-pull.yaml")


@pytest.fixture
def bad_config() -> Scenario:
    return load_scenario(SCENARIO_DIR / "bad-config.yaml")
