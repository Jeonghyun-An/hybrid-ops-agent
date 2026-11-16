from collections.abc import Sequence
from pathlib import Path
from statistics import mean

from hoa_eval.runner import RunRecord


def load_records(paths: Sequence[Path]) -> list[RunRecord]:
    return [
        RunRecord.model_validate_json(line)
        for path in paths
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def ratio(hits: int, total: int) -> str:
    return f"{hits}/{total}"


def summary_table(records: Sequence[RunRecord]) -> str:
    rows = [
        "| 시나리오 | 모델 | 회차 | 원인 정답 | 대상 정답 | 인용 확인 | 도구 호출 평균 "
        "| 형식 깨진 호출 | 시간 평균(초) | 입력 토큰 평균 | 실패 |",
        "|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    groups: dict[tuple[str, str], list[RunRecord]] = {}
    for record in records:
        groups.setdefault((record.scenario, record.model), []).append(record)
    for (scenario, profile), group in groups.items():
        model = next((r.model_id for r in group if r.model_id), profile)
        scored = [r.score for r in group if r.score is not None]
        failed = len(group) - len(scored)
        if not scored:
            rows.append(
                f"| {scenario} | {model} | {len(group)} | - | - | - | - | - | - | - | {failed} |"
            )
            continue
        rows.append(
            f"| {scenario} | {model} | {len(group)} "
            f"| {ratio(sum(s.label_correct for s in scored), len(group))} "
            f"| {ratio(sum(s.target_correct for s in scored), len(group))} "
            f"| {ratio(sum(s.quotes_found for s in scored), sum(s.quotes for s in scored))} "
            f"| {mean(s.tool_calls for s in scored):.1f} "
            f"| {sum(s.invalid_tool_calls for s in scored)} "
            f"| {mean(s.elapsed_seconds for s in scored):.1f} "
            f"| {mean(s.input_tokens for s in scored):,.0f} "
            f"| {failed} |"
        )
    return "\n".join(rows)


def runs_table(records: Sequence[RunRecord]) -> str:
    rows = [
        "| 시나리오 | 모델 | 회차 | 원인 | 인용 | 도구 | 시간(초) | 멈춘 이유 | 오류 |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for record in records:
        name = record.model_id or record.model
        if record.score is None or record.report is None:
            rows.append(
                f"| {record.scenario} | {name} | {record.attempt} | - | - | - | - | - "
                f"| {record.error or '-'} |"
            )
            continue
        s = record.score
        rows.append(
            f"| {record.scenario} | {name} | {record.attempt} "
            f"| {record.report.diagnosis.cause_label}{'' if s.label_correct else ' ✗'} "
            f"| {ratio(s.quotes_found, s.quotes)} | {s.tool_calls} | {s.elapsed_seconds:.1f} "
            f"| {s.stop_reason} | - |"
        )
    return "\n".join(rows)
