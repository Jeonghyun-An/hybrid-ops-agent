import argparse
import io
import sys
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path

from hoa_eval import __version__
from hoa_eval.agent import AgentNotFound, run_agent
from hoa_eval.cluster import ClusterError, DemoCluster, Kubectl
from hoa_eval.report import load_records, runs_table, summary_table
from hoa_eval.runner import Agent, Cluster, RunRecord, run_batch
from hoa_eval.scenario import REPO_ROOT, ScenarioError, load_scenarios

# hoa_agent.llm과 같은 값 — 멤버 경계라 import하지 않는다
DEFAULT_MODEL = "gemma"
MODEL_NAMES = ("gemma", "gemini")
RESULTS_DIR = REPO_ROOT / "eval" / "results"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="hoa-eval", description="장애 시나리오로 에이전트를 평가한다"
    )
    parser.add_argument("--version", action="version", version=f"hoa-eval {__version__}")
    commands = parser.add_subparsers(dest="command")
    run = commands.add_parser("run", help="장애를 넣고 에이전트를 돌려 채점한다")
    run.add_argument(
        "--model", choices=MODEL_NAMES, default=DEFAULT_MODEL, help=f"쓸 LLM(기본 {DEFAULT_MODEL})"
    )
    run.add_argument("--repeat", type=int, default=3, help="시나리오마다 돌릴 횟수")
    run.add_argument(
        "--scenario", action="append", default=[], help="돌릴 시나리오 이름(여러 번 줄 수 있다)"
    )
    run.add_argument("--pause", type=float, default=20.0, help="회차 사이 쉬는 초")
    run.add_argument("--results-dir", type=Path, default=RESULTS_DIR, help="결과 JSONL 폴더")
    report = commands.add_parser("report", help="결과 JSONL을 마크다운 표로 합친다")
    report.add_argument("files", nargs="+", type=Path, help="결과 JSONL 파일")
    return parser


def use_utf8_output() -> None:
    """Windows에서 출력을 파일·파이프로 돌리면 로캘 인코딩(cp949)이 돼 도움말·표의 문자가 깨진다."""
    for stream in (sys.stdout, sys.stderr):
        if isinstance(stream, io.TextIOWrapper):
            stream.reconfigure(encoding="utf-8")


def run_command(args: argparse.Namespace, cluster: Cluster, agent: Agent) -> int:
    try:
        scenarios = load_scenarios(args.scenario)
    except ScenarioError as exc:
        print(f"hoa-eval: {exc}", file=sys.stderr)
        return 2
    args.results_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    path = args.results_dir / f"{stamp}-{args.model}.jsonl"

    def write(record: RunRecord) -> None:
        with path.open("a", encoding="utf-8") as sink:
            sink.write(record.model_dump_json() + "\n")
        verdict = record.error or (
            "맞음" if record.score and record.score.label_correct else "틀림"
        )
        print(f"{record.scenario} #{record.attempt}: {verdict}", file=sys.stderr, flush=True)

    try:
        records = run_batch(
            scenarios, args.model, args.repeat, cluster, agent, pause_seconds=args.pause, sink=write
        )
    except (ClusterError, AgentNotFound) as exc:
        print(f"hoa-eval: {exc}", file=sys.stderr)
        return 1
    print(summary_table(records))
    print(f"\n결과: {path}")
    if records and records[-1].rate_limited:
        print("hoa-eval: LLM 요청 한도에 걸려 남은 회차를 멈췄다", file=sys.stderr)
        return 3
    return 0


def main(
    argv: Sequence[str] | None = None,
    *,
    cluster: Cluster | None = None,
    agent: Agent = run_agent,
) -> int:
    use_utf8_output()
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command == "run":
        return run_command(args, cluster or DemoCluster(Kubectl()), agent)
    if args.command == "report":
        records = load_records(args.files)
        print(summary_table(records))
        print()
        print(runs_table(records))
        return 0
    parser.print_help()
    return 0
