import argparse
import asyncio
import io
import logging
import math
import os
import sys
import urllib.parse
from collections.abc import Awaitable, Callable, Mapping, Sequence

import uvicorn

from hoa_agent import __version__
from hoa_agent.api import create_app
from hoa_agent.failures import EXIT_CODES, KNOWN_FAILURES, classify, operator_message
from hoa_agent.investigate import run_investigation
from hoa_agent.llm import DEFAULT_MODEL, MODEL_NAMES
from hoa_agent.result import InvestigationResult

Investigator = Callable[[str, str], Awaitable[InvestigationResult]]
DEFAULT_TIMEOUT_SECONDS = 300.0
ServerRunner = Callable[..., None]


class SkipHealthChecks(logging.Filter):
    """프로브 요청이 접근 로그를 채우지 않게 한다."""

    def filter(self, record: logging.LogRecord) -> bool:
        return "/healthz" not in record.getMessage()


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
    serve = commands.add_parser(
        "serve", help="조사 API를 연다(클러스터 안 — MCP 서버에 HTTP로 붙는다)"
    )
    serve.add_argument(
        "--host", default="127.0.0.1", help="묶을 주소(기본 127.0.0.1 — 차트가 0.0.0.0을 준다)"
    )
    serve.add_argument("--port", type=int, default=8080, help="포트(기본 8080)")
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
    except KNOWN_FAILURES as exc:
        kind = classify(exc)
        print(f"hoa: {operator_message(kind, exc)}", file=sys.stderr)
        return EXIT_CODES[kind]
    print(result.model_dump_json(indent=2))
    if not args.json:
        print(render_summary(result), file=sys.stderr)
    return 0


def serve_command(
    args: argparse.Namespace, env: Mapping[str, str], run_server: ServerRunner
) -> int:
    mcp_url = env.get("HOA_MCP_URL", "").strip()
    if not mcp_url:
        print(
            "hoa: HOA_MCP_URL is not set — hoa serve reaches the MCP server over HTTP "
            "(the agent chart sets it)",
            file=sys.stderr,
        )
        return 2
    if urllib.parse.urlsplit(mcp_url).scheme not in ("http", "https"):
        print("hoa: HOA_MCP_URL must be an http:// or https:// URL", file=sys.stderr)
        return 2
    model = env.get("HOA_MODEL", "").strip() or DEFAULT_MODEL
    if model not in MODEL_NAMES:
        print(
            f"hoa: HOA_MODEL must be one of {', '.join(MODEL_NAMES)}, got {model!r}",
            file=sys.stderr,
        )
        return 2
    raw_timeout = env.get("HOA_INVESTIGATION_TIMEOUT", "").strip() or str(DEFAULT_TIMEOUT_SECONDS)
    try:
        timeout = float(raw_timeout)
    except ValueError:
        timeout = math.nan
    if not (math.isfinite(timeout) and timeout > 0):
        print(
            "hoa: HOA_INVESTIGATION_TIMEOUT must be a positive number of seconds, "
            f"got {raw_timeout!r}",
            file=sys.stderr,
        )
        return 2

    async def investigate(alert: str) -> InvestigationResult:
        return await run_investigation(alert, model, env)

    # 루트는 WARNING — httpx가 요청마다 INFO로 LLM 주소 전체를 남기기 때문이다
    logging.basicConfig(
        level=logging.WARNING, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
    )
    logging.getLogger("hoa_agent").setLevel(logging.INFO)
    logging.getLogger("uvicorn.access").addFilter(SkipHealthChecks())
    run_server(create_app(investigate, timeout_seconds=timeout), host=args.host, port=args.port)
    return 0


def main(
    argv: Sequence[str] | None = None,
    *,
    investigator: Investigator = run_investigation,
    env: Mapping[str, str] | None = None,
    run_server: ServerRunner = uvicorn.run,
) -> int:
    use_utf8_output()
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command == "investigate":
        return investigate_command(args, investigator)
    if args.command == "serve":
        return serve_command(args, os.environ if env is None else env, run_server)
    parser.print_help()
    return 0
