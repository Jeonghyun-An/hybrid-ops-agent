from collections import Counter
from collections.abc import Sequence
from pathlib import Path
from statistics import mean

from hoa_eval.runner import RunRecord

# 모델이 답할 기회가 없었던 회차 — 정답률의 분모에서 빼고 「제외」로 따로 센다
EXCLUDED = {"rate_limit": "한도", "setup": "설정", "no_symptom": "증상 없음"}
MAX_ERROR_CHARS = 120


def load_records(paths: Sequence[Path]) -> list[RunRecord]:
    return [
        RunRecord.model_validate_json(line)
        for path in paths
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def ratio(hits: int, total: int) -> str:
    return f"{hits}/{total}"


def short_error(text: str) -> str:
    """완료노트(공개 저장소)에 옮길 표다 — 홈 경로를 가리고, 표를 깨는 `|`와 긴 원문을 줄인다."""
    home = str(Path.home())
    for form in (home, home.replace("\\", "/")):
        text = text.replace(form, "~")
    text = " ".join(text.split()).replace("|", "\\|")
    return text if len(text) <= MAX_ERROR_CHARS else text[: MAX_ERROR_CHARS - 1] + "…"


def model_names(group: Sequence[RunRecord], profile: str) -> str:
    names = list(dict.fromkeys(r.model_id for r in group if r.model_id))
    return ", ".join(names) or profile


def excluded_note(group: Sequence[RunRecord]) -> str:
    counts = Counter(EXCLUDED[r.failure] for r in group if r.failure in EXCLUDED)
    return ", ".join(f"{label} {count}" for label, count in counts.items()) or "0"


def summary_table(records: Sequence[RunRecord]) -> str:
    rows = [
        "| 시나리오 | 모델 | 채점 회차 | 원인 정답 | 대상 정답 | 인용 확인 | 도구 호출 평균 "
        "| 도구 오류 | 형식 깨진 호출 | 시간 평균(초) | 입력 토큰 평균 | 에이전트 실패 | 제외 |",
        "|---|---|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    groups: dict[tuple[str, str], list[RunRecord]] = {}
    for record in records:
        groups.setdefault((record.scenario, record.model), []).append(record)
    for (scenario, profile), group in groups.items():
        judged = [r for r in group if r.failure not in EXCLUDED]
        scored = [r.score for r in judged if r.score is not None]
        head = f"| {scenario} | {model_names(group, profile)} | {len(judged)} "
        tail = f"| {len(judged) - len(scored)} | {excluded_note(group)} |"
        if not scored:
            rows.append(f"{head}| 0/{len(judged)} | 0/{len(judged)} | - | - | - | - | - | - {tail}")
            continue
        rows.append(
            f"{head}"
            f"| {ratio(sum(s.label_correct for s in scored), len(judged))} "
            f"| {ratio(sum(s.target_correct for s in scored), len(judged))} "
            f"| {ratio(sum(s.quotes_found for s in scored), sum(s.quotes for s in scored))} "
            f"| {mean(s.tool_calls for s in scored):.1f} "
            f"| {sum(s.tool_errors for s in scored)} "
            f"| {sum(s.invalid_tool_calls for s in scored)} "
            f"| {mean(s.elapsed_seconds for s in scored):.1f} "
            f"| {mean(s.input_tokens for s in scored):,.0f} "
            f"{tail}"
        )
    return "\n".join(rows)


def runs_table(records: Sequence[RunRecord]) -> str:
    rows = [
        "| 시나리오 | 모델 | 회차 | 원인 | 인용 | 도구 | 도구 오류 | 시간(초) | 멈춘 이유 | 오류 |",
        "|---|---|---|---|---|---|---|---|---|---|",
    ]
    for record in records:
        name = record.model_id or record.model
        if record.score is None or record.report is None:
            rows.append(
                f"| {record.scenario} | {name} | {record.attempt} | - | - | - | - | - | - "
                f"| {short_error(record.error or '-')} |"
            )
            continue
        s = record.score
        rows.append(
            f"| {record.scenario} | {name} | {record.attempt} "
            f"| {record.report.diagnosis.cause_label}{'' if s.label_correct else ' ✗'} "
            f"| {ratio(s.quotes_found, s.quotes)} | {s.tool_calls} | {s.tool_errors} "
            f"| {s.elapsed_seconds:.1f} | {s.stop_reason} | - |"
        )
    return "\n".join(rows)
