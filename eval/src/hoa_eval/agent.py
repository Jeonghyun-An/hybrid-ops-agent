import shutil
import subprocess
import sys
from collections.abc import Sequence
from pathlib import Path

from pydantic import BaseModel, ValidationError

AGENT_COMMAND = "hoa"
AGENT_TIMEOUT_SECONDS = 900
# hoa investigate의 종료 코드 — 3은 LLM 요청 한도에 걸렸다는 뜻이다
RATE_LIMITED_EXIT = 3


class AgentNotFound(Exception):
    pass


class ReportedEvidence(BaseModel):
    tool: str
    quote: str


class ReportedDiagnosis(BaseModel):
    cause_label: str
    target: str
    evidence: list[ReportedEvidence]
    confidence: float
    summary_ko: str


class ReportedStep(BaseModel):
    tool: str
    args: dict[str, object]
    output: str
    error: bool


class ReportedUsage(BaseModel):
    model_calls: int
    input_tokens: int
    output_tokens: int
    total_tokens: int


class AgentReport(BaseModel):
    """hoa investigate --json 출력 — 멤버 경계라 hoa_agent 모델을 import하지 않고 따로 둔다."""

    model: str
    alert: str
    diagnosis: ReportedDiagnosis
    stop_reason: str
    steps: list[ReportedStep]
    invalid_tool_calls: int
    usage: ReportedUsage
    elapsed_seconds: float


class AgentOutcome(BaseModel):
    report: AgentReport | None = None
    error: str | None = None
    rate_limited: bool = False


def agent_command() -> list[str]:
    found = shutil.which(AGENT_COMMAND, path=str(Path(sys.executable).parent)) or shutil.which(
        AGENT_COMMAND
    )
    if found is None:
        raise AgentNotFound(f"{AGENT_COMMAND} not found — run uv sync --locked")
    return [found]


def last_line(text: str) -> str:
    lines = [line for line in text.strip().splitlines() if line.strip()]
    return lines[-1] if lines else "no output"


def run_agent(alert: str, model: str, *, command: Sequence[str] | None = None) -> AgentOutcome:
    """에이전트를 별도 프로세스로 돌린다 — 평가가 에이전트 코드를 import하지 않는다."""
    argv = [*(command or agent_command()), "investigate", "--json", "--model", model, alert]
    try:
        result = subprocess.run(
            argv,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=AGENT_TIMEOUT_SECONDS,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return AgentOutcome(error=f"agent timed out after {AGENT_TIMEOUT_SECONDS}s")
    if result.returncode != 0:
        return AgentOutcome(
            error=last_line(result.stderr), rate_limited=result.returncode == RATE_LIMITED_EXIT
        )
    try:
        return AgentOutcome(report=AgentReport.model_validate_json(result.stdout))
    except ValidationError as exc:
        return AgentOutcome(
            error=f"agent output broke the report schema: {exc.error_count()} errors"
        )
