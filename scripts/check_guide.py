"""교본의 「**파일**: `경로`」 코드블록을 실제 파일과 대조한다.

사용: uv run python scripts/check_guide.py <교본 파일 또는 폴더> [--rev <커밋>]
--rev를 주면 작업 사본 대신 그 커밋의 파일과 비교한다.
지난 라운드 교본은 그 라운드의 커밋과 비교한다.
종료 코드: 0 모두 일치, 1 불일치·누락·형식 오류, 2 잘못된 --rev.
"""

import argparse
import difflib
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FILE_LINE = re.compile(r"^\*\*파일\*\*: `([^`]+)`$")
NEAR_FILE_LINE = re.compile(r"^\*\*파일")
FENCE = re.compile(r"^(`{3,}|~{3,})")


class GuideError(Exception):
    pass


def extract_blocks(guide: Path) -> list[tuple[str, str]]:
    lines = guide.read_text(encoding="utf-8").splitlines(keepends=True)
    blocks: list[tuple[str, str]] = []
    i = 0
    while i < len(lines):
        line = lines[i].rstrip("\r\n")
        match = FILE_LINE.match(line)
        if match is None:
            if NEAR_FILE_LINE.match(line):
                raise GuideError(f"{guide}:{i + 1}: 「**파일**: `경로`」 형식이 아니다 — {line}")
            i += 1
            continue
        path = match.group(1)
        j = i + 1
        while j < len(lines) and not lines[j].strip():
            j += 1
        opener = FENCE.match(lines[j]) if j < len(lines) else None
        if opener is None:
            raise GuideError(f"{guide}:{i + 1}: `{path}` 다음에 코드블록이 없다")
        fence = opener.group(1)
        k = j + 1
        while k < len(lines) and lines[k].rstrip("\r\n") != fence:
            k += 1
        if k == len(lines):
            raise GuideError(f"{guide}:{j + 1}: `{path}` 코드블록이 닫히지 않았다")
        blocks.append((path, "".join(lines[j + 1 : k])))
        i = k + 1
    return blocks


def rev_exists(rev: str) -> bool:
    result = subprocess.run(
        ["git", "rev-parse", "--verify", "--quiet", f"{rev}^{{commit}}"],
        cwd=ROOT,
        capture_output=True,
        check=False,
    )
    return result.returncode == 0


def read_actual(path: str, rev: str | None) -> str | None:
    if rev is None:
        target = ROOT / path
        return target.read_text(encoding="utf-8") if target.is_file() else None
    result = subprocess.run(
        ["git", "show", f"{rev}:{path}"], cwd=ROOT, capture_output=True, check=False
    )
    return result.stdout.decode("utf-8") if result.returncode == 0 else None


def guide_files(target: Path) -> list[Path]:
    return sorted(target.glob("*.md")) if target.is_dir() else [target]


def main(argv: list[str] | None = None) -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description="교본 코드블록을 실제 파일과 대조한다")
    parser.add_argument("target", type=Path, help="교본 파일 또는 교본 폴더")
    parser.add_argument("--rev", help="작업 사본 대신 비교할 git 커밋")
    args = parser.parse_args(argv)
    if args.rev is not None and not rev_exists(args.rev):
        print(f"커밋을 찾을 수 없다: {args.rev}")
        return 2
    checked = 0
    mismatched = 0
    for guide in guide_files(args.target):
        try:
            blocks = extract_blocks(guide)
        except GuideError as exc:
            print(f"형식 오류: {exc}")
            mismatched += 1
            continue
        for path, block in blocks:
            checked += 1
            expected = read_actual(path, args.rev)
            if expected is None:
                print(f"없음: {path} ({guide.name})")
                mismatched += 1
            elif expected != block:
                print(f"다름: {path} ({guide.name})")
                sys.stdout.writelines(
                    difflib.unified_diff(
                        expected.splitlines(keepends=True),
                        block.splitlines(keepends=True),
                        f"{path} (실제)",
                        f"{path} (교본)",
                    )
                )
                mismatched += 1
    if checked == 0:
        print("대조할 코드블록이 없다 — 교본 경로를 확인한다")
        return 1
    print(f"대조 {checked}개, 불일치 {mismatched}개")
    return 1 if mismatched else 0


if __name__ == "__main__":
    sys.exit(main())
