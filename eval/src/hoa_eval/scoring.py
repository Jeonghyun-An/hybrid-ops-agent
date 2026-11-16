from collections.abc import Iterable

from pydantic import BaseModel

from hoa_eval.agent import AgentReport
from hoa_eval.scenario import Expected

# JSON 출력의 이스케이프(\")와 `키: "값"` 꼴 인용을 같은 문장으로 본다
IGNORED_CHARS = str.maketrans("", "", "\\\"'`")


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
    return bool(needle) and any(needle in normalize(output) for output in outputs)


def score(expected: Expected, report: AgentReport) -> Score:
    outputs = [step.output for step in report.steps if not step.error]
    quotes = [item.quote for item in report.diagnosis.evidence]
    return Score(
        label_correct=report.diagnosis.cause_label == expected.cause_label,
        target_correct=report.diagnosis.target.strip().lower() == expected.target,
        quotes=len(quotes),
        quotes_found=sum(quote_found(quote, outputs) for quote in quotes),
        tool_calls=len(report.steps),
        tool_errors=sum(step.error for step in report.steps),
        invalid_tool_calls=report.invalid_tool_calls,
        model_calls=report.usage.model_calls,
        input_tokens=report.usage.input_tokens,
        output_tokens=report.usage.output_tokens,
        elapsed_seconds=report.elapsed_seconds,
        stop_reason=report.stop_reason,
    )
