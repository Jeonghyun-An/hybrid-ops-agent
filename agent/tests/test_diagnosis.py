from pathlib import Path

import pytest
import yaml
from pydantic import ValidationError

from hoa_agent.diagnosis import CauseLabel, Diagnosis
from hoa_agent.prompts import DIAGNOSE_PROMPT

VALID = {
    "cause_label": "bad_config",
    "target": "demo/inventory",
    "evidence": [{"tool": "get_pod_logs", "quote": "HOA_DEMO_PORT='eighty'"}],
    "confidence": 0.8,
    "summary_ko": "포트 설정이 숫자가 아니다.",
}


def test_valid_diagnosis_parses_the_label() -> None:
    assert Diagnosis.model_validate(VALID).cause_label is CauseLabel.BAD_CONFIG


@pytest.mark.parametrize(
    "change",
    [
        {"cause_label": "network_partition"},
        {"evidence": []},
        {"confidence": 1.5},
    ],
)
def test_diagnosis_outside_the_schema_is_rejected(change: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        Diagnosis.model_validate(VALID | change)


def test_json_schema_lists_every_label_for_the_model() -> None:
    schema = Diagnosis.model_json_schema()

    assert set(schema["$defs"]["CauseLabel"]["enum"]) == {label.value for label in CauseLabel}


def test_eval_scenarios_only_expect_labels_the_agent_can_answer() -> None:
    """평가 멤버는 라벨 목록을 import하지 않고 옮겨 두었다 — 어긋나면 정답에 영영 닿지 못한다."""
    scenarios = Path(__file__).resolve().parents[2] / "eval" / "scenarios"
    expected = {
        yaml.safe_load(path.read_text(encoding="utf-8"))["expected"]["cause_label"]
        for path in scenarios.glob("*.yaml")
    }

    assert expected
    assert expected <= {label.value for label in CauseLabel}


def test_the_diagnosis_prompt_defines_every_label() -> None:
    """라벨에 뜻이 없으면 모델이 근본 원인과 증상(프로브 실패) 사이에서 unknown으로 피한다."""
    for label in CauseLabel:
        assert f"  - {label.value}: " in DIAGNOSE_PROMPT
