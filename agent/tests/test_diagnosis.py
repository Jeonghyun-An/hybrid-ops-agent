import pytest
from pydantic import ValidationError

from hoa_agent.diagnosis import CauseLabel, Diagnosis

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
