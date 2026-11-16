import argparse
import asyncio
import io
import sys
from collections.abc import Awaitable, Callable, Sequence

import openai

from hoa_agent import __version__
from hoa_agent.graph import DiagnosisSchemaError
from hoa_agent.investigate import run_investigation
from hoa_agent.llm import DEFAULT_MODEL, MODEL_NAMES, LLMConfigError
from hoa_agent.mcp_tools import MCPSetupError
from hoa_agent.result import InvestigationResult

Investigator = Callable[[str, str], Awaitable[InvestigationResult]]
# 평가 러너(hoa_eval.agent.RATE_LIMITED_EXIT)가 이 값으로 남은 회차를 멈춘다
RATE_LIMITED_EXIT = 3


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="hoa", description="hybrid-ops-agent 명령줄 도구")
    parser.add_argument("--version", action="version", version=f"hoa {__version__}")
    commands = parser.add_subparsers(dest="command")
    investigate = commands.add_parser("investigate", help="경보 하나를 조사해 진단을 낸다")
    investigate.add_argument(
        "--model", choices=MODEL_NAMES, default=DEFAULT_MODEL, help=f"쓸 LLM(기본 {DEFAULT_MODEL})"
    )
    investigate.add_argument(
        "--json", action="store_true", help="표준오류의 사람용 요약 없이 JSON만 낸다"
    )
    investigate.add_argument("alert", help="경보 문장")
    return parser


def render_summary(result: InvestigationResult) -> str:
    diagnosis = result.diagnosis
    lines = [
        f"원인: {diagnosis.cause_label.value} (확신도 {diagnosis.confidence:.2f})",
        f"대상: {diagnosis.target}",
        f"요약: {diagnosis.summary_ko}",
        "근거:",
        *(f"  - [{item.tool}] {item.quote}" for item in diagnosis.evidence),
        (
            f"조사: 도구 {sum(s.executed for s in result.steps)}번 · "
            f"모델 호출 {result.usage.model_calls}번 · "
            f"토큰 {result.usage.total_tokens:,} · {result.elapsed_seconds:.1f}초 · "
            f"멈춘 이유 {result.stop_reason}"
        ),
    ]
    return "\n".join(lines)


def use_utf8_output() -> None:
    """Windows에서 출력을 파일·파이프로 돌리면 로캘 인코딩(cp949)이 돼 `—` 같은 문자에서 깨진다."""
    for stream in (sys.stdout, sys.stderr):
        if isinstance(stream, io.TextIOWrapper):
            stream.reconfigure(encoding="utf-8")


def investigate_command(args: argparse.Namespace, investigator: Investigator) -> int:
    try:
        result = asyncio.run(investigator(args.alert, args.model))
    except (LLMConfigError, MCPSetupError) as exc:
        print(f"hoa: {exc}", file=sys.stderr)
        return 2
    except openai.RateLimitError as exc:
        print(f"hoa: the LLM rate limit was hit — {exc}", file=sys.stderr)
        return RATE_LIMITED_EXIT
    except (DiagnosisSchemaError, openai.OpenAIError) as exc:
        print(f"hoa: investigation failed — {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1
    print(result.model_dump_json(indent=2))
    if not args.json:
        print(render_summary(result), file=sys.stderr)
    return 0


def main(
    argv: Sequence[str] | None = None, *, investigator: Investigator = run_investigation
) -> int:
    use_utf8_output()
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command == "investigate":
        return investigate_command(args, investigator)
    parser.print_help()
    return 0
