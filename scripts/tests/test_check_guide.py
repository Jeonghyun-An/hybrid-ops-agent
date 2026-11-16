import importlib.util
from pathlib import Path
from types import ModuleType

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "check_guide.py"


def load_script() -> ModuleType:
    spec = importlib.util.spec_from_file_location("check_guide", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def check_guide(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> ModuleType:
    module = load_script()
    monkeypatch.setattr(module, "ROOT", tmp_path)
    (tmp_path / "a.txt").write_text("alpha\n", encoding="utf-8")
    (tmp_path / "doc.md").write_text("# t\n```bash\necho hi\n```\n", encoding="utf-8")
    return module


def guide(tmp_path: Path, name: str, body: str) -> Path:
    path = tmp_path / "guides" / name
    path.parent.mkdir(exist_ok=True)
    path.write_text(body, encoding="utf-8")
    return path


def test_matching_blocks_pass(check_guide: ModuleType, tmp_path: Path) -> None:
    body = (
        "**파일**: `a.txt`\n\n```text\nalpha\n```\n\n"
        "**파일**: `doc.md`\n\n````markdown\n# t\n```bash\necho hi\n```\n````\n"
    )
    assert check_guide.main([str(guide(tmp_path, "g.md", body))]) == 0


def test_a_different_block_fails_with_a_diff(
    check_guide: ModuleType, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    body = "**파일**: `a.txt`\n\n```text\nbeta\n```\n"
    assert check_guide.main([str(guide(tmp_path, "g.md", body))]) == 1
    output = capsys.readouterr().out
    assert "다름: a.txt" in output
    assert "-alpha" in output and "+beta" in output


def test_a_missing_file_fails(check_guide: ModuleType, tmp_path: Path) -> None:
    body = "**파일**: `nope.txt`\n\n```text\nx\n```\n"
    assert check_guide.main([str(guide(tmp_path, "g.md", body))]) == 1


def test_no_blocks_at_all_fails(check_guide: ModuleType, tmp_path: Path) -> None:
    assert check_guide.main([str(guide(tmp_path, "g.md", "# 제목만\n"))]) == 1


def test_a_malformed_file_line_fails_instead_of_being_skipped(
    check_guide: ModuleType, tmp_path: Path
) -> None:
    body = "**파일:** `a.txt`\n\n```text\nalpha\n```\n"
    assert check_guide.main([str(guide(tmp_path, "g.md", body))]) == 1


def test_an_unclosed_block_is_reported_and_other_guides_are_still_checked(
    check_guide: ModuleType, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    guide(tmp_path, "1-bad.md", "**파일**: `a.txt`\n\n```text\nalpha\n")
    guide(tmp_path, "2-good.md", "**파일**: `a.txt`\n\n```text\nalpha\n```\n")
    assert check_guide.main([str(tmp_path / "guides")]) == 1
    output = capsys.readouterr().out
    assert "닫히지 않았다" in output
    assert "대조 1개, 불일치 1개" in output


def test_an_unknown_revision_exits_2(check_guide: ModuleType, tmp_path: Path) -> None:
    body = "**파일**: `a.txt`\n\n```text\nalpha\n```\n"
    assert check_guide.main([str(guide(tmp_path, "g.md", body)), "--rev", "no-such-rev"]) == 2
