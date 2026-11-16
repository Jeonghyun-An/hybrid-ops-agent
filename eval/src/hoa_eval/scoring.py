import re
from collections.abc import Iterable

from pydantic import BaseModel

from hoa_eval.agent import AgentReport
from hoa_eval.scenario import Expected

# JSON 출력의 이스케이프(\")와 `키: "값"` 꼴 인용을 같은 문장으로 본다
IGNORED_CHARS = str.maketrans("", "", "\\\"'`")
# 이보다 짧은 인용(`Failed`·`Running`·숫자 하나)은 어디에나 있어 근거로 치지 않는다
MIN_QUOTE_CHARS = 8


class Score(BaseModel):
    label_correct: bool
    target_correct: bool
    quotes: int
    quotes_found: int
    tool_calls: int
    tool_errors: int
    invalid_tool_calls: int
    model_calls: int
    input_tokens: int
    output_tokens: int
    elapsed_seconds: float
    stop_reason: str


def normalize(text: str) -> str:
    return " ".join(text.translate(IGNORED_CHARS).split())


def quote_found(quote: str, outputs: Iterable[str]) -> bool:
    needle = normalize(quote).rstrip(".")
    if len(needle) < MIN_QUOTE_CHARS:
        return False
    # 단어 중간에서 시작하거나 끝나는 일치(`restarts: 1` ⊂ `restarts: 12`)는 인용으로 치지 않는다
    pattern = re.compile(rf"(?<![0-9A-Za-z]){re.escape(needle)}(?![0-9A-Za-z]|[.\-][0-9A-Za-z])")
    return any(pattern.search(normalize(output)) for output in outputs)


def score(expected: Expected, report: AgentReport) -> Score:
    executed = [step for step in report.steps if step.executed]
    outputs = [step.output for step in executed if not step.error]
    quotes = [item.quote for item in report.diagnosis.evidence]
    return Score(
        label_correct=report.diagnosis.cause_label == expected.cause_label,
        target_correct=report.diagnosis.target.strip().lower() == expected.target,
        quotes=len(quotes),
        quotes_found=sum(quote_found(quote, outputs) for quote in quotes),
        tool_calls=len(executed),
        tool_errors=sum(step.error for step in executed),
        invalid_tool_calls=report.invalid_tool_calls,
        model_calls=report.usage.model_calls,
        input_tokens=report.usage.input_tokens,
        output_tokens=report.usage.output_tokens,
        elapsed_seconds=report.elapsed_seconds,
        stop_reason=report.stop_reason,
    )
