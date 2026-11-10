# round00 — 저장소 골격 + 라운드 방식 이식 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 빈 저장소에 uv 워크스페이스(`agent` 멤버 + `hoa` CLI)·pre-commit(ruff·gitleaks)·GitHub Actions CI·devcontainer를 세우고, NL-Lib의 라운드 개발 방식(CLAUDE.md·GIT_WORKFLOW.md·완료노트/교본 템플릿·code-reviewer 에이전트·round-finish 스킬)을 이 프로젝트에 맞게 옮긴다.

**Architecture:** 설정·문서 Task는 고전적 red-green TDD 대상이 아니므로 "파일 없음 확인 → 전문 작성 → 구조 검증 → 커밋"으로 간다. 코드는 `hoa` CLI 하나뿐이고 이것만 TDD로 간다. 품질 게이트는 대상 파일이 있는 것(ruff·pytest·gitleaks)만 이번 라운드에 넣고, helm·terraform 게이트는 그 파일이 생기는 라운드로 미룬다(spec §8).

**Tech Stack:** uv 0.11 워크스페이스, Python 3.12, hatchling, pytest 9, ruff 0.17.4, pre-commit 4.7, gitleaks 8.30.1, GitHub Actions(checkout v7·setup-uv v10.3.3), devcontainer.

**spec:** `docs/superpowers/specs/2026-11-09-hybrid-ops-agent-design.md` (§7 round00 행, §8 라운드 방식 이식)

**선행 완료 사항 (재실행 불필요):**
- 저장소 `C:\Users\LANDSOFT\mygit\hybrid-ops-agent` 클론, 커밋 신원 `Hyonii <131145818+Jeonghyun-An@users.noreply.github.com>`.
- `main`(빈 시작 커밋 `5fd3223`) → `dev` → `feat/round00-scaffold`(spec 커밋 `5f873fd`). 원격은 아직 비어 있다(push 전).

모든 Task는 `feat/round00-scaffold` 브랜치에서 진행한다. 명령은 Git Bash 기준이며 작업 디렉터리는 저장소 루트다.

**커밋 규칙:** `[Type] 한국어 설명` 한 줄. `Co-Authored-By` 트레일러와 "Generated with" 문구는 넣지 않는다(단독 저자).

---

### Task 1: 줄바꿈 고정과 무시 목록 — `.gitattributes` · `.gitignore`

**Files:**
- Create: `.gitattributes`
- Create: `.gitignore`

- [x] **Step 1: 파일 없음 확인**

Run: `ls .gitattributes .gitignore 2>&1`
Expected: 두 파일 모두 `No such file or directory`

- [x] **Step 2: `.gitattributes` 작성**

```gitattributes
# 저장소 안 텍스트 파일은 작업 사본에서도 LF로 고정한다 — Windows 전역 core.autocrlf=true 를 이긴다(recurring-gotchas 1번)
* text=auto eol=lf
*.ps1 text eol=crlf
*.png binary
*.jpg binary
*.gif binary
```

- [x] **Step 3: `.gitignore` 작성**

```gitignore
# 비밀값 — 커밋하지 않는다(SOPS로 암호화한 파일의 예외 규칙은 round02에서 파일 이름 규칙과 함께 더한다)
.env
.env.*
!.env.example
*.agekey
keys.txt
kubeconfig
!kubeconfig/
kubeconfig*.yaml
kubeconfig*.yml
*.kubeconfig
k3s.yaml

# Python
__pycache__/
*.py[cod]
.venv/
.pytest_cache/
.ruff_cache/

# Node (web/, round06)
node_modules/
.nuxt/
.output/
dist/

# Terraform (round03) — .terraform.lock.hcl 은 커밋한다
.terraform/
*.tfstate
*.tfstate.*
*.tfvars
*.tfvars.json

# IDE·로컬 설정
.vscode/settings.json
.idea/
.claude/settings.local.json

# 로그·디버그 출력
*.log
*_debug_out*.txt

# 브레인스토밍 비주얼 컴패니언 임시 목업
.superpowers/
```

- [x] **Step 4: 기존 파일 재정규화와 줄바꿈 확인**

Run:
```bash
git add .gitattributes .gitignore
git add --renormalize .
git ls-files --eol
```
Expected: 모든 줄이 `i/lf    w/lf` (spec 파일 포함). `w/crlf`가 보이면 그 파일을 `rm <파일> && git checkout -- <파일>`로 인덱스에서 다시 꺼낸 뒤 재확인(`git rm --cached`를 먼저 하면 인덱스에서 빠져 `git checkout --`이 실패한다).

- [x] **Step 5: 커밋**

```bash
git commit -m "[Chore] round00 — 줄바꿈을 LF로 고정하고(.gitattributes) 비밀값·kubeconfig·Terraform state·빌드 산출물을 무시 목록에 넣는다"
```

---

### Task 2: uv 워크스페이스와 `hoa` CLI (TDD)

**Files:**
- Create: `.python-version`
- Create: `pyproject.toml` (워크스페이스 루트 — 패키지 아님)
- Create: `agent/pyproject.toml`
- Create: `agent/src/hoa_agent/__init__.py`
- Create: `agent/src/hoa_agent/cli.py`
- Create: `agent/tests/test_cli.py`
- Create(생성됨): `uv.lock`

- [x] **Step 1: `.python-version` 작성**

```text
3.12
```

- [x] **Step 2: 루트 `pyproject.toml` 작성**

루트에는 `[build-system]`이 없다 — uv는 이 프로젝트 자체를 설치하지 않고 워크스페이스 멤버와 개발 도구만 맞춘다. ruff `src`는 import 정렬에서 `hoa_agent`를 우리 코드(first-party)로 보게 한다 — 멤버를 더할 때마다 그 멤버의 `src`도 더한다.

```toml
[project]
name = "hybrid-ops-agent"
version = "0.0.0"
description = "온프레미스(k3s)와 Azure(AKS)를 함께 쓰는 쿠버네티스 운영 에이전트 — uv 워크스페이스 루트"
requires-python = ">=3.12"
dependencies = ["hoa-agent"]

[tool.uv]
required-version = ">=0.11.31,<0.12"

[tool.uv.workspace]
members = ["agent"]

[tool.uv.sources]
hoa-agent = { workspace = true }

[dependency-groups]
dev = [
    "pre-commit>=4.7",
    "pytest>=9.2",
    "ruff==0.17.4",
]

[tool.ruff]
line-length = 100
target-version = "py312"
src = ["agent/src"]

[tool.ruff.lint]
select = ["E", "F", "I", "UP", "B"]

[tool.pytest.ini_options]
addopts = "--import-mode=importlib"
testpaths = ["agent/tests"]
```

- [x] **Step 3: `agent/pyproject.toml` 작성**

```toml
[project]
name = "hoa-agent"
version = "0.0.0"
description = "운영 에이전트(LangGraph)와 hoa 명령줄 도구"
requires-python = ">=3.12"
dependencies = []

[project.scripts]
hoa = "hoa_agent.cli:main"

[build-system]
requires = ["hatchling>=1.27,<2"]
build-backend = "hatchling.build"
```

- [x] **Step 4: `agent/src/hoa_agent/__init__.py` 작성**

버전은 `agent/pyproject.toml` 한 곳에만 적고 설치 메타데이터에서 읽는다.

```python
from importlib.metadata import version

__version__ = version("hoa-agent")
```

- [x] **Step 5: 의존성 설치**

Run: `uv sync`
Expected: Python 3.12가 없으면 uv가 내려받고, `.venv` 생성 후 `hoa-agent`(editable)·pre-commit·pytest·ruff 설치. `uv.lock` 생성.

- [x] **Step 6: 실패하는 테스트 작성 — `agent/tests/test_cli.py`**

```python
import pytest

from hoa_agent import __version__
from hoa_agent.cli import main


def test_version_flag_prints_name_and_version(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exc_info:
        main(["--version"])

    assert exc_info.value.code == 0
    assert capsys.readouterr().out.strip() == f"hoa {__version__}"


def test_no_arguments_prints_help_and_succeeds(capsys: pytest.CaptureFixture[str]) -> None:
    assert main([]) == 0
    assert "usage: hoa" in capsys.readouterr().out
```

- [x] **Step 7: 테스트가 실패하는지 확인**

Run: `uv run pytest -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'hoa_agent.cli'`

- [x] **Step 8: 최소 구현 — `agent/src/hoa_agent/cli.py`**

```python
import argparse
from collections.abc import Sequence

from hoa_agent import __version__


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="hoa", description="hybrid-ops-agent 명령줄 도구")
    parser.add_argument("--version", action="version", version=f"hoa {__version__}")
    parser.parse_args(argv)
    parser.print_help()
    return 0
```

- [x] **Step 9: 테스트 통과 확인**

Run: `uv run pytest -v`
Expected: `2 passed`

- [x] **Step 10: 콘솔 스크립트 확인**

Run: `uv run hoa --version`
Expected: `hoa 0.0.0`

- [x] **Step 11: 린트·포맷 확인**

Run: `uv run ruff check . && uv run ruff format --check .`
Expected: `All checks passed!` 와 `5 files already formatted` — ruff 0.17은 Markdown 안의 Python 코드 블록도 포맷 검사하므로 `.py` 3개(`__init__.py`·`cli.py`·`test_cli.py`)에 spec·plan `.md` 2개가 더해진다(뒤 Task에서 문서가 늘면 이 수도 는다). 포맷 차이가 있으면 `uv run ruff format .` 후 다시 확인.

- [x] **Step 12: 커밋**

```bash
git add .python-version pyproject.toml uv.lock agent/
git commit -m "[Feat] round00 — uv 워크스페이스(루트=개발 도구, 멤버 agent)와 hoa CLI(--version)를 세운다. 버전은 agent/pyproject.toml 한 곳에서 설치 메타데이터로 읽는다"
```

---

### Task 3: pre-commit — ruff · gitleaks · 기본 위생 검사

**Files:**
- Create: `.pre-commit-config.yaml`

- [x] **Step 1: 파일 없음 확인**

Run: `ls .pre-commit-config.yaml 2>&1`
Expected: `No such file or directory`

- [x] **Step 2: 작성**

ruff `rev`는 루트 `pyproject.toml` dev 그룹의 `ruff==0.17.4`와 같아야 한다(로컬 훅과 CI가 같은 판정을 내리게).

```yaml
# 커밋 직전 검사. ruff rev 는 pyproject.toml dev 그룹의 ruff 버전과, gitleaks rev 는 .github/workflows/ci.yml 의 gitleaks 다운로드 버전과 맞춘다.
repos:
  - repo: https://github.com/pre-commit/pre-commit-hooks
    rev: v6.0.0
    hooks:
      - id: check-yaml
        args: [--allow-multiple-documents]
      - id: check-toml
      - id: end-of-file-fixer
      - id: trailing-whitespace
      - id: check-merge-conflict
      - id: check-added-large-files
  - repo: https://github.com/astral-sh/ruff-pre-commit
    rev: v0.17.4
    hooks:
      - id: ruff-check
        args: [--fix]
      - id: ruff-format
  - repo: https://github.com/gitleaks/gitleaks
    rev: v8.30.1
    hooks:
      - id: gitleaks
```

- [x] **Step 3: 훅 설치와 전체 실행**

Run:
```bash
uv run pre-commit install
uv run pre-commit run --all-files
```
Expected: 첫 실행은 훅 환경을 만들며 오래 걸린다. 모든 훅 `Passed`. `end-of-file-fixer`·`trailing-whitespace`가 `Failed`(파일 수정함)로 나오면 수정된 파일을 확인하고 한 번 더 실행해 전부 `Passed`인지 본다.

gitleaks 훅(`language: golang`)이 Go 툴체인을 못 구해 실패하면, 그 훅의 id를 `gitleaks-docker`(Docker Desktop 사용)로 바꾸고 다시 실행한다. 바꿨다면 그 사실을 `docs/ops/recurring-gotchas.md`(Task 9)에 2번 항목으로 기록한다.

- [x] **Step 4: 비밀값 차단이 실제로 도는지 확인**

가짜 GitHub 토큰을 실행할 때 무작위로 만든다 — 토큰 모양 문자열을 문서에 그대로 적으면 그 문서가 gitleaks에 걸린다.

Run:
```bash
printf 'token = "ghp_%s"\n' "$(head -c 64 /dev/urandom | base64 | tr -dc 'A-Za-z0-9' | head -c 36)" > leak-test.txt
git add leak-test.txt
uv run pre-commit run gitleaks
```
Expected: `gitleaks...Failed` 와 `leaks found: 1`(규칙 `github-pat`). 확인 뒤 정리:
```bash
git rm --cached -q leak-test.txt && rm leak-test.txt
```

- [x] **Step 5: 커밋**

```bash
git add .pre-commit-config.yaml
git add -u
git commit -m "[Chore] round00 — pre-commit 에 ruff(린트·포맷)·gitleaks(스테이징 변경의 비밀값)·기본 위생 검사를 건다. ruff 버전은 dev 그룹과 같은 0.17.4"
```

---

### Task 4: GitHub Actions CI

**Files:**
- Create: `.github/workflows/ci.yml`

- [x] **Step 1: 파일 없음 확인**

Run: `ls .github 2>&1`
Expected: `No such file or directory`

- [x] **Step 2: 작성**

`secrets` 잡은 pre-commit의 gitleaks와 달리 **전체 이력**을 본다(`fetch-depth: 0`). pre-commit은 `--no-verify`나 미설치로 건너뛸 수 있어서다.

`astral-sh/setup-uv`는 v8부터 떠다니는 메이저 태그(`v10`)를 내지 않는다(있는 것은 `v10.0.0`~`v10.3.3` 같은 정확한 버전 태그뿐) — `@v10`으로 쓰면 CI가 액션을 못 찾아 실패하므로 정확한 버전으로 고정한다. `actions/checkout`은 `v7` 메이저 태그가 있다.

```yaml
name: ci

on:
  push:
  pull_request:

permissions:
  contents: read

jobs:
  python:
    name: 린트·테스트
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v7
      - uses: astral-sh/setup-uv@v10.3.3
        with:
          enable-cache: true
      - name: 의존성 설치(잠금 파일 그대로)
        run: uv sync --locked
      - name: ruff 린트
        run: uv run ruff check .
      - name: ruff 포맷 검사
        run: uv run ruff format --check .
      - name: pytest
        run: uv run pytest

  secrets:
    name: 비밀값 검사(gitleaks, 전체 이력)
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v7
        with:
          fetch-depth: 0
      - name: gitleaks 설치
        run: curl -sSfL https://github.com/gitleaks/gitleaks/releases/download/v8.30.1/gitleaks_8.30.1_linux_x64.tar.gz | tar -xz gitleaks
      - name: gitleaks 검사
        run: ./gitleaks git --redact --verbose .
```

- [x] **Step 3: 로컬 검증 — YAML 문법과 잠금 파일 일치**

Run:
```bash
uv run pre-commit run check-yaml --files .github/workflows/ci.yml
uv sync --locked
```
Expected: `check yaml...Passed`, `uv sync --locked`가 오류 없이 끝난다(잠금 파일이 pyproject와 맞음). 실제 CI 실행은 Task 15에서 push 후 확인한다.

- [x] **Step 4: 커밋**

```bash
git add .github/workflows/ci.yml
git commit -m "[Chore] round00 — GitHub Actions CI: 잠금 파일 그대로 설치 후 ruff·pytest, gitleaks 로 전체 이력의 비밀값 검사"
```

---

### Task 5: devcontainer

**Files:**
- Create: `.devcontainer/devcontainer.json`
- Create(생성됨): `.devcontainer/devcontainer-lock.json` — Step 4의 `devcontainer up`이 만든다. 기능(feature) 버전·digest를 고정하므로 `uv.lock`처럼 커밋한다.

- [x] **Step 1: 파일 없음 확인**

Run: `ls .devcontainer 2>&1`
Expected: `No such file or directory`

- [x] **Step 2: 작성**

kind는 round01에서 더한다. Docker는 호스트(Docker Desktop)의 것을 쓴다(`docker-outside-of-docker`) — kind 클러스터가 호스트 Docker 위에 떠야 개발 PC 어디서든 같은 클러스터를 본다.

devcontainer는 작업 폴더와 `.git`을 호스트와 공유(bind mount)한다. 그래서 두 가지를 막는다.
- 컨테이너의 venv는 `UV_PROJECT_ENVIRONMENT`로 작업 폴더 밖(`/home/vscode/.venv`)에 둔다 — 안 그러면 컨테이너의 `uv sync`가 호스트(Windows)의 `.venv`를 Linux용으로 갈아엎는다.
- `pre-commit install`은 컨테이너에서 하지 않는다 — 공유된 `.git/hooks/pre-commit`이 컨테이너 Python 경로를 가리키게 되어 호스트 커밋이 깨진다.

그 밖에: `remoteEnv`로 컨테이너 venv의 `bin`을 PATH 앞에 둬 컨테이너 셸에서 `uv run` 없이도 `hoa`·`pytest`·`pre-commit`을 부른다. Windows 호스트의 작업 폴더는 컨테이너 안에서 소유자가 달라 git이 `dubious ownership`으로 멈추므로 `postCreateCommand` 맨 앞에서 `safe.directory`에 작업 폴더를 등록한다(`git status`·`pre-commit run` 같은 git 기반 도구가 컨테이너에서 돈다). 사용자 설정(`--global`)이 아니라 시스템 설정(`--system`, `/etc/gitconfig`)에 쓰는 것은 VS Code가 호스트 `~/.gitconfig`를 컨테이너로 복사해 넣어도 덮이지 않게 하기 위해서고, 맨 앞에 두는 것은 뒤 단계(`uv sync`)가 실패해도 git은 쓸 수 있게 하기 위해서다. VS Code Python 확장은 작업 폴더 밖의 venv를 스스로 찾지 못할 수 있어 `python.defaultInterpreterPath`로 알려 준다. 그래도 Windows 호스트에서는 **커밋은 호스트에서** 한다 — 호스트에서 설치한 훅 스크립트가 CRLF라 컨테이너에서 실행되지 않는다(recurring-gotchas 3번).

이미지는 현재 메이저(`3-`) 태그를 쓴다. `1-3.12-bookworm`은 1번대에서 멈춘 태그라 서명 키가 만료된 Yarn apt 저장소가 남아 있어, 기능(feature) 설치의 `apt-get update`가 실패한다(recurring-gotchas 2번). uv는 `pipx`로 설치한다 — 이 이미지의 `pipx` 설치 경로(`/usr/local/py-utils/bin`)는 PATH에 있지만 `pip install --user`의 `~/.local/bin`은 `postCreateCommand` 시점 PATH에 없다. 버전 범위는 루트 `pyproject.toml`의 `[tool.uv] required-version`과 맞추고, `uv sync --locked`로 잠금 파일을 그대로 쓴다(컨테이너가 공유된 `uv.lock`을 고쳐 쓰지 않게).

```json
{
  "name": "hybrid-ops-agent",
  "image": "mcr.microsoft.com/devcontainers/python:3-3.12-bookworm",
  "features": {
    "ghcr.io/devcontainers/features/docker-outside-of-docker:1": {},
    "ghcr.io/devcontainers/features/kubectl-helm-minikube:1": { "minikube": "none" },
    "ghcr.io/devcontainers/features/terraform:1": {},
    "ghcr.io/devcontainers/features/azure-cli:1": {}
  },
  "containerEnv": {
    "UV_PROJECT_ENVIRONMENT": "/home/vscode/.venv"
  },
  "remoteEnv": {
    "PATH": "/home/vscode/.venv/bin:${containerEnv:PATH}"
  },
  "postCreateCommand": "sudo git config --system --replace-all safe.directory ${containerWorkspaceFolder} && pipx install 'uv>=0.11.31,<0.12' && uv sync --locked",
  "customizations": {
    "vscode": {
      "settings": {
        "python.defaultInterpreterPath": "/home/vscode/.venv/bin/python"
      },
      "extensions": [
        "charliermarsh.ruff",
        "ms-python.python",
        "ms-kubernetes-tools.vscode-kubernetes-tools",
        "hashicorp.terraform"
      ]
    }
  }
}
```

- [x] **Step 3: JSON 문법 확인**

Run: `uv run python -c "import json; json.load(open('.devcontainer/devcontainer.json', encoding='utf-8')); print('devcontainer.json OK')"`
Expected: `devcontainer.json OK`

- [x] **Step 4: 수동 스모크 — 컨테이너가 실제로 뜨는지**

Docker Desktop이 켜져 있을 때:

먼저 호스트 상태를 적어 둔다: `cat .venv/pyvenv.cfg; grep -n INSTALL_PYTHON .git/hooks/pre-commit`.

Run: `npx -y @devcontainers/cli up --workspace-folder .`
Expected: 마지막 줄 JSON에 `"outcome":"success"`. 이어서
`npx -y @devcontainers/cli exec --workspace-folder . uv run hoa --version` → `hoa 0.0.0`.
`npx -y @devcontainers/cli exec --workspace-folder . sh -c 'git status --short && pre-commit run check-yaml --all-files'` → git이 소유자 문제 없이 돌고(`.devcontainer/devcontainer-lock.json` 외 변경 없음 — 특히 `uv.lock`이 바뀌지 않는다), `check yaml...Passed`.

확인 뒤 `up` 출력 JSON의 `containerId` 값으로 이 컨테이너만 지운다: `docker rm -f <containerId>`.
호스트의 `.venv/pyvenv.cfg`와 `.git/hooks/pre-commit`의 `INSTALL_PYTHON`이 기동 전과 같고 `uv run pytest`가 통과하는지 다시 본다.
Docker Desktop이 꺼져 있어 못 했다면 완료노트 「이월」에 "devcontainer 실제 기동 미확인"으로 적는다.

- [x] **Step 5: 커밋**

```bash
git add .devcontainer/devcontainer.json .devcontainer/devcontainer-lock.json
git commit -m "[Chore] round00 — devcontainer: Python 3.12 + uv + kubectl·helm·terraform·az, Docker 는 호스트 것을 쓴다. venv 는 작업 폴더 밖에 두고 훅은 호스트에서만 설치해 호스트 .venv·git 훅을 덮어쓰지 않는다"
```

---

### Task 6: `CLAUDE.md`

**Files:**
- Create: `CLAUDE.md`

- [x] **Step 1: 파일 없음 확인**

Run: `ls CLAUDE.md 2>&1`
Expected: `No such file or directory`

- [x] **Step 2: 작성**

```markdown
# CLAUDE.md — 개발 운영 진입점

> Claude가 이 프로젝트에서 어떻게 작동하고 어떤 작업에 어디를 보는지의 단일 진입점.
> 상세는 각 문서로 링크(중복 금지). 충돌 시 이 파일이 우선.

## 0. 프로젝트 한 줄
온프레미스(집 RTX 3060 PC의 k3s)와 Azure(AKS·Azure OpenAI)를 함께 쓰는 쿠버네티스 운영 에이전트. 학습 목적의 개인 프로젝트라 각 기술을 "왜 이렇게 썼나"까지 설명할 수 있게 만드는 것이 우선이다. 전체 설계: `docs/superpowers/specs/2026-11-09-hybrid-ops-agent-design.md`.

## 1. 병렬 작업 원칙
- 독립적인 작업(에이전트 ↔ MCP 서버 ↔ 인프라 ↔ 평가)은 가능하면 서브에이전트로 병행한다. 순차 진행은 의존성이 있을 때만.

## 2. 산출물 위치 규칙 (불변)
- 루트에는 운영 파일(`CLAUDE.md`·`GIT_WORKFLOW.md`·`README.md`·`.gitignore`·`.gitattributes`·`pyproject.toml`·`uv.lock`·`.python-version`·`.pre-commit-config.yaml`)과 도구 설정 폴더(`.github/`·`.devcontainer/`·`.claude/`)만 둔다.
- 코드 정본: `agent/`·`mcp_servers/`·`graphrag/`·`demo_app/`·`eval/`·`web/`. Python 컴포넌트는 uv 워크스페이스 멤버다. 배포 정의는 `deploy/`(Helm·Argo CD), 인프라는 `infra/`(Terraform·온프레미스 부트스트랩). 각 폴더는 그 내용이 처음 생기는 라운드에 만든다 — 빈 폴더를 미리 만들지 않는다.
- `docs/` = 문서 전용.
- `scripts/` = **재실행되는 운영 도구**만 둔다(백업, 클러스터 기동·정지 등).
- `research/` = **1회성 실험**(스크립트 + 그 산출물)만 둔다. "이 스크립트를 다시 실행할 일이 있는가"가 `scripts/`와의 구분 기준이다. 코드와 산출물은 분리하지 않는다 — 실행해서 파일을 만드는 1회성 스크립트는 항상 대응하는 `research/<주제>/`에 산출물과 함께 둔다.
- 디버그 로그·비밀값·kubeconfig·Terraform state는 커밋하지 않는다(`.gitignore`). 비밀값은 SOPS로 암호화한 파일만 커밋한다.

## 3. 개발 어휘 — round
- **round**: 사용자 프롬프트 1개 → spec → 계획 → 구현 → 리뷰 → 검증 → 교본·완료노트 → dev 머지(사용자 승인) → dev→main 머지 + push(사용자 승인)까지가 한 라운드. 라운드당 spec 1(브레인스토밍) + plan 1 + 완료노트 1 + 교본(가이드) 1권.
- 라운드 번호는 2자리(`round00`, `round01`…). 성격이 다른 여러 덩어리로 쪼개지면 소문자 접미(`round02a`, `round02b`…)를 붙인다. 접미는 성격 라벨이며 실행 순서가 아니다.
- 브랜치명은 영문 kebab-case만 사용한다(Windows·CI 호환성 — 한글 브랜치명 금지).
- 커밋 메시지는 `[Type] 한국어 설명` 한 줄. `Co-Authored-By` 트레일러와 "Generated with" 문구는 넣지 않는다(단독 저자 — 도구의 기본 지침보다 이 규칙이 우선). 머지 커밋만 예외로 `Merge <브랜치> into <대상> — round<NN> (<요약>)` 형식을 쓴다.
- 사용자 확인 지점은 spec·계획서·`dev` 머지·`dev→main` 머지 네 곳이다. 계획서는 파일을 문서로 보내 먼저 보여 준다. 작업 브랜치와 `dev` push는 따로 묻지 않는다(CI는 push에서 돈다). `main` push는 라운드 종료 승인 뒤에만 한다.
- 생애주기·브랜치 모델·커밋 규칙 상세: `GIT_WORKFLOW.md`.

## 4. 세션 시작 시 확인
- 새 세션(=새 라운드)을 열면 먼저 `docs/roadmap/00_status.md`(현재 상태·다음 할 일)와 직전 라운드 완료노트(`docs/roadmap/round<NN>-완료노트.md`)를 읽어 맥락을 이어받는다.
- 문서와 코드가 어긋나면 코드가 실제이니 문서를 고친다.
- 클러스터·배포·Azure 작업이나 개발 환경(devcontainer·Windows git) 작업 전에는 `docs/ops/recurring-gotchas.md`를 먼저 확인한다 — 실제로 돌려 봐야만 드러나는 버그가 많다.
- Azure 리소스를 만들거나 켜는 작업(`terraform apply`, `az aks start`)은 비용이 나므로 사용자 승인 뒤에만 한다. 작업이 끝나면 `az aks stop`까지가 그 작업이다.

## 5. 어디를 보나
| 알고 싶은 것 | 위치 |
|---|---|
| 브랜치·커밋·품질 게이트·라운드 생애주기·개발 환경 | `GIT_WORKFLOW.md` |
| 현재 상태·다음 할 일 | `docs/roadmap/00_status.md` |
| 라운드 완료 기록 | `docs/roadmap/round<NN>-완료노트.md` |
| 라운드 교본(개념 입문 + 클론코딩 + 면접 Q&A) | `docs/guides/round<NN>/` |
| 전체 설계·라운드 로드맵 | `docs/superpowers/specs/2026-11-09-hybrid-ops-agent-design.md` |
| 기능 설계(브레인스토밍 spec) | `docs/superpowers/specs/` |
| 구현 계획(writing-plans) | `docs/superpowers/plans/` |
| 코딩 표준 | `docs/standards/coding-standard.md` |
| 반복 함정(실제로 돌려 봐야만 드러나는 버그) | `docs/ops/recurring-gotchas.md` |
| 라운드 종료 절차 자동화 | `.claude/skills/round-finish/SKILL.md` |
| 정적 코드 리뷰 서브에이전트 | `.claude/agents/code-reviewer.md` |
| 프로젝트 소개·시작하기 | `README.md` |
```

- [x] **Step 3: 구조 확인**

Run: `grep -c '^## ' CLAUDE.md && grep -o '`[^`]*\.md`' CLAUDE.md | sort -u`
Expected: 섹션 수 `6`. 나열된 `.md` 경로 중 `docs/roadmap/round<NN>-완료노트.md` 같은 패턴 경로를 뺀 나머지는 이 plan의 Task 6~14에서 만드는 파일이거나 이미 있는 spec이다.

- [x] **Step 4: 커밋**

```bash
git add CLAUDE.md
git commit -m "[Docs] round00 — CLAUDE.md: NL-Lib 진입점 구조를 옮기고 코드 폴더·Azure 비용 승인 규칙을 이 프로젝트에 맞춘다"
```

---

### Task 7: `GIT_WORKFLOW.md`

**Files:**
- Create: `GIT_WORKFLOW.md`

- [x] **Step 1: 파일 없음 확인**

Run: `ls GIT_WORKFLOW.md 2>&1`
Expected: `No such file or directory`

- [x] **Step 2: 작성**

````markdown
# Git Workflow

> 이 프로젝트(hybrid-ops-agent)의 브랜치·커밋·머지 규칙과 품질 게이트·개발 환경. 모든 작업은 이 문서를 따른다.

## 브랜치 모델

| 브랜치 | 역할 | 규칙 |
|---|---|---|
| `main` | 배포 기준 — round02부터 Argo CD가 이 브랜치를 클러스터에 동기화한다 | 평소 직접 작업 금지. 라운드 종료 시 사용자 승인 하에 `dev → main` 머지 후 `origin` push. |
| `dev` | 통합 브랜치 | 완성된 작업 브랜치가 모이는 곳. 클러스터에 배포하지 않고 CI로만 검증한다. 직접 커밋은 완료노트 「상태」 체크만 한다(§라운드 생애주기 7·8). |
| `<type>/round<NN>-<설명>` | 작업 브랜치 | `dev`에서 분기. 한 작업 단위 = 한 브랜치. |

- 타입(Conventional): `feat`·`fix`·`docs`·`chore`·`refactor`·`test`
- 설명은 영문 kebab-case(예: `feat/round01-end-to-end`) — 한글 브랜치명은 Windows·CI 호환성 문제로 쓰지 않는다.
- 서브라운드: 한 라운드가 성격이 다른 여러 덩어리로 쪼개지면 소문자 접미를 붙인다(`round02a`, `round02b`…). 접미는 성격 라벨이며 실행 순서가 아니다.

## 흐름

```
dev ─분기→ <type>/round<NN>-<설명> ─개발·커밋·push(CI)─→ 리뷰 ─[사용자 승인]→ merge→ dev ─[라운드 종료 승인]→ main ─push→ origin (round02부터 = 배포)
```

1. `dev`에서 작업 브랜치 분기
2. 개발 → 커밋 → 원격 push. 솔로 작업이라도 작업 브랜치를 push한다 — CI는 push에서 돈다. push는 따로 승인받지 않는다(§머지 승인 규칙).
3. 완성되면 리뷰(서브에이전트 정적 리뷰 + 자가 점검) → 사용자 승인을 받은 뒤 `dev`로 `--no-ff` 머지 (승인 전 머지 금지)
4. `dev` push
5. 라운드 종료(사용자 승인): `dev → main` 머지 + `origin` push

## 머지 승인 규칙

- 작업 브랜치 → `dev`: 매번 사용자 채팅 승인 필수. 리뷰 게이트는 (1) `.claude/agents/code-reviewer.md` 서브에이전트의 정적 리뷰와 (2) 자가 점검 체크리스트(CI green + 관련 기능 수동 스모크 + 문서 갱신 여부)를 순서대로 통과하는 것이다.
- 리뷰 발견 처리: high·medium은 모두 고친다. low는 고치거나, 고치지 않는 이유를 완료노트 「결정」에 한 줄로 적는다. 고친 뒤에는 CI를 다시 확인한다.
- `dev` → `main`: 라운드 종료 판단·승인은 사용자. round02부터는 `main` push가 곧 배포다.
- push는 승인 대상이 아니다 — 작업 브랜치와 `dev`는 Claude가 push한다. `main` push는 위 라운드 종료 승인에 포함된다. 사용자가 확인하는 지점은 spec·계획서(§라운드 생애주기 1·2)와 위 두 머지다.

## 커밋 메시지

- `[Type] 설명` (한국어, 대괄호 태그 + 한 줄 요약)
- Type: `Feat`·`Fix`·`Docs`·`Chore`·`Refactor`·`Test`
- 예) `[Feat] MCP k8s-read 서버에 events 도구 추가`, `[Fix] 평가 러너가 경보 대기 시간을 넘기면 멈추던 문제`, `[Docs] round01 교본 추가`
- 본문은 꼭 필요할 때만 몇 줄.
- 머지 커밋만 예외로 `Merge <브랜치> into <대상> — round<NN> (<요약>)` 형식을 쓴다(`git merge --no-ff -m`).
- `Co-Authored-By` 트레일러와 "Generated with" 문구는 넣지 않는다(단독 저자).

## 품질 게이트 (pre-commit · CI)

| 검사 | 어디서 | 들어오는 라운드 |
|---|---|---|
| 기본 위생(check-yaml·check-toml·파일 끝 줄바꿈·줄 끝 공백·충돌 표시·큰 파일) | pre-commit | round00 |
| ruff check · ruff format --check | pre-commit + CI | round00 |
| pytest | CI | round00 |
| gitleaks | pre-commit(스테이징 변경) + CI(전체 이력) | round00 |
| helm lint · kubeconform | CI | round02 |
| terraform fmt -check · terraform validate | pre-commit + CI | round03 |

- 검사는 그 파일 종류가 처음 생기는 라운드에 더한다 — 대상 없는 검사는 아무것도 증명하지 못한다.
- `terraform apply`는 CI에서 돌리지 않는다. 로컬에서 사용자 승인 뒤 손으로만 한다.
- 클론한 뒤 한 번(호스트에서): `uv run pre-commit install`. devcontainer 안에서는 하지 않는다(§개발 환경).
- 두 곳에 적힌 도구 버전은 같이 올린다: ruff는 `pyproject.toml` dev 그룹과 `.pre-commit-config.yaml` rev, gitleaks는 `.pre-commit-config.yaml` rev와 `.github/workflows/ci.yml` 다운로드 URL. uv는 `pyproject.toml`의 `[tool.uv] required-version`이 정본이다 — CI(setup-uv)는 이 값을 읽고, devcontainer `postCreateCommand`의 `pipx install` 버전 범위는 손으로 맞춘다.

## 개발 환경

| 환경 | 용도 | 들어오는 라운드 |
|---|---|---|
| 개발 PC: uv + Docker Desktop | 코드·단위 테스트 | round00 |
| devcontainer (`.devcontainer/`) | 개발 PC가 바뀌어도 같은 도구 세트(uv·kubectl·helm·terraform·az) | round00 |
| 개발 PC: kind | 끝-끝 경로, MCP 통합 테스트 | round01 |
| 집 PC: Ubuntu + k3s + GPU Operator | 상시 클러스터(데이터·모델·관측·Argo CD) | round02 |
| Azure AKS | 작업할 때만 켜는 클라우드 클러스터 | round03 |

- Python: `uv sync` → `uv run pytest`. Python 버전은 `.python-version`(3.12)에 맞춰 uv가 준비한다.
- GitHub CLI(`gh`)는 호스트에 설치하고 `gh auth login`한다 — CI 결과 확인과 `/round-finish`가 쓴다.
- devcontainer는 작업 폴더와 `.git`을 호스트와 공유한다. 그래서 컨테이너의 venv는 작업 폴더 밖(`/home/vscode/.venv`, `UV_PROJECT_ENVIRONMENT`)에 두고, `pre-commit install`은 호스트에서만 한다 — 컨테이너에서 하면 공유된 훅이 컨테이너 Python을 가리켜 호스트 커밋이 깨진다. Windows 호스트에서는 커밋도 호스트에서 한다 — 호스트에서 설치한 훅 스크립트가 CRLF라 컨테이너에서 실행되지 않는다(`docs/ops/recurring-gotchas.md` 3번).
- 각 환경의 세부 절차(설치·접속·기동/정지)는 그 환경이 들어오는 라운드에 이 절에 더한다.

## 개발 가이드 문서 (필수)

- 1 라운드 = 1 교본(가이드). `docs/guides/round<NN>/`에 저장(템플릿: `docs/guides/_TEMPLATE.md`).
- 구성: paraphrase된 라운드 프롬프트 → 설계 요약 → 개념 입문(이 라운드에 처음 나온 개념을 기초부터) → 전 코드/문서 클론코딩 가능하게 수록(발췌·플레이스홀더 금지) → 검증 → 면접식 Q&A.
- 리뷰 흐름: 작업 브랜치 push → 교본↔실제 파일 대조(교본의 코드블록을 뽑아 실제 파일과 diff한다 — 제목 수만 세지 않는다. 그다음 `.claude/agents/code-reviewer.md`로 한 번 더 본다. 리뷰어는 git을 실행하지 않으므로 대조할 파일 목록은 호출하는 쪽이 넘긴다) → 승인 → `dev` 머지.

## 라운드 생애주기

1. 프롬프트→spec: `docs/superpowers/specs/`에 브레인스토밍 설계 작성(브레인스토밍 스킬) → 사용자 확인 뒤 계획으로 넘어간다.
2. 계획: `docs/superpowers/plans/`에 구현 계획 작성(writing-plans 스킬) → 계획서 파일을 사용자에게 문서로 보여 주고 확인받은 뒤 구현한다.
3. 구현: TDD(`docs/standards/coding-standard.md`).
4. 리뷰: `.claude/agents/code-reviewer.md` 서브에이전트로 정적 리뷰 → 발견 처리(§머지 승인 규칙).
5. 검증: CI green + 관련 기능 수동 스모크(round01부터 평가 러너 시나리오 포함).
6. 문서: 작업 브랜치에서 교본(`docs/guides/round<NN>/`)·완료노트(`docs/roadmap/round<NN>-완료노트.md`, 템플릿 `docs/roadmap/_ROUND_COMPLETE_TEMPLATE.md`)를 쓰고 `docs/roadmap/00_status.md`를 갱신 → 교본 대조 리뷰(§개발 가이드 문서).
7. 머지: 사용자 승인 → 작업 브랜치를 `dev`에 `--no-ff` 머지·push → `dev`에서 완료노트 「상태」의 `dev` 머지 승인 줄을 체크·커밋·push(`dev` CI).
8. 라운드 종료: 사용자 승인 → `/round-finish` 스킬로 `dev→main` 머지 + `origin` push → `dev`에서 완료노트 마지막 줄을 체크·커밋해 `dev`에만 push(다음 라운드 머지 때 `main`에 함께 올라간다).

## 비고

- 비밀정보·kubeconfig·Terraform state는 커밋하지 않는다(`.gitignore`). public 저장소다 — 한 번 push된 비밀값은 이력에서 지워도 이미 노출된 것으로 보고 키를 폐기한다.
- 실행해서 파일을 만들어내는 1회성 스크립트는 대응하는 `research/<주제>/`에 산출물과 함께 둔다(`CLAUDE.md` §2).
````

- [x] **Step 3: 구조 확인**

Run: `grep '^## ' GIT_WORKFLOW.md`
Expected: `브랜치 모델`·`흐름`·`머지 승인 규칙`·`커밋 메시지`·`품질 게이트 (pre-commit · CI)`·`개발 환경`·`개발 가이드 문서 (필수)`·`라운드 생애주기`·`비고` 9개.

- [x] **Step 4: 커밋**

```bash
git add GIT_WORKFLOW.md
git commit -m "[Docs] round00 — GIT_WORKFLOW.md: 브랜치·승인·커밋 규칙은 NL-Lib 그대로, 품질 게이트(라운드별 도입)·개발 환경(kind/k3s/AKS)은 새로 쓴다"
```

---

### Task 8: `docs/standards/coding-standard.md`

**Files:**
- Create: `docs/standards/coding-standard.md`

- [x] **Step 1: 파일 없음 확인**

Run: `ls docs/standards 2>&1`
Expected: `No such file or directory`

- [x] **Step 2: 작성**

```markdown
# 코딩 표준

새 프로젝트라 기존 반례 없이 시작한다. 규칙을 어긴 코드를 일부러 남겨야 하면 맨 아래 「백로그」에 파일 단위로 적는다 — code-reviewer는 백로그에 적힌 반례를 새 결함으로 다시 보고하지 않는다.

## 패키지 경계

- Python 컴포넌트는 uv 워크스페이스 멤버 하나씩이다(`agent`·`mcp_servers`·`graphrag`·`demo_app`·`eval`). 멤버마다 컨테이너 이미지가 따로 나가므로 의존성을 섞지 않는다 — 예: MCP 서버 이미지에 LangGraph가 들어가지 않는다.
- 멤버끼리 다른 멤버의 내부 모듈을 import하지 않는다. 공용 타입이 필요해지면 공용 멤버를 새로 만든다.
- 레이아웃: `<멤버>/src/<import 이름>/`, 테스트는 `<멤버>/tests/`. import 이름은 `hoa_` 접두(`hoa_agent`).
- 새 멤버를 더할 때는 루트 `pyproject.toml`의 다섯 곳을 같이 고친다 — `[tool.uv.workspace] members`·`[tool.uv.sources]`·`dependencies`·ruff `src`·pytest `testpaths`. `testpaths`를 빠뜨리면 새 멤버의 테스트가 CI에서 조용히 빠진다.

## 외부 호출 격리

- LLM 호출은 멤버마다 한 모듈(`llm.py`)을 거친다. 로컬 vLLM과 Azure OpenAI가 모두 OpenAI 호환 API라 클라이언트 하나를 설정으로 바꿔 쓰고, 역할(triage·diagnose·extract 등)마다 어느 모델을 쓸지도 `llm.py`가 정한다. 그래프 노드·도구 코드가 HTTP 클라이언트를 직접 만들지 않는다.
- LLM을 쓰는 멤버(`agent`·`graphrag`·`eval`)가 각자 `llm.py`를 두는 중복은 허용한다(멤버 경계를 지키는 값). 공용 멤버로 뺄지는 두 번째 멤버가 LLM을 쓰기 시작하는 라운드에 정한다.
- LLM 클라이언트는 주입받는다(모듈 전역에서 생성하지 않는다) — 테스트에서 가짜 LLM으로 바꿔 끼우기 위해서다.
- 에이전트(`agent`)는 클러스터를 MCP 도구로만 만진다. 쿠버네티스 API 클라이언트는 MCP 서버(`mcp_servers`) 안에 두고, 예외는 에이전트가 아닌 두 곳뿐이다 — `graphrag` 구조 층 동기화 잡(읽기 전용 ServiceAccount)과 `eval` 러너의 장애 주입·복구(데모 네임스페이스 한정).

## 타입·데이터

- 모든 함수 인자·반환에 타입힌트를 단다. `list[str]`·`X | None` 같은 최신 문법을 쓴다.
- 경계 데이터(LangGraph 상태, MCP 도구 입출력, API 요청·응답, 평가 시나리오)는 Pydantic v2 모델로 정의한다. 경계를 넘는 bare `dict`는 쓰지 않는다.
- 네트워크 I/O(LLM·MCP·DB·HTTP·k8s API)는 `async def`로 쓴다. CLI 진입점(`main`)은 동기로 두고 필요하면 `asyncio.run`으로 감싼다.

## 주석·docstring

- 기본은 주석 없음. 왜(why)가 코드만으로 드러나지 않을 때만 한 줄 docstring이나 주석을 단다.
- 무엇을 하는지 설명하는 주석, 현재 작업·이슈 번호를 참조하는 주석은 쓰지 않는다.

## 에러 처리

- 시스템 경계(API 입력, LLM 응답, MCP 도구 결과, k8s API 응답)에서만 검증한다. 내부 계층 간 호출은 서로를 신뢰한다.
- 구체적 예외를 잡는다. 넓은 `except Exception`으로 여러 실패를 삼키지 않는다.
- LLM 구조화 출력이 스키마를 어기면 기본값으로 조용히 메우지 않는다 — 재시도하거나 실패로 드러낸다.

## 테스트

- 새 기능은 실패하는 테스트 → 최소 구현 → 통과 순서(TDD)로 진행한다.
- LLM은 결정적 응답을 내는 가짜 구현으로 바꿔 끼운다. mock 범위는 외부 호출로만 한정한다.
- 쿠버네티스가 필요한 테스트는 kind에 붙는 통합 테스트로 분리하고 `integration` 마커를 단다(마커 등록은 round01).
- 테스트 이름은 동작을 문장으로 쓴다(`test_version_flag_prints_name_and_version`).

## 쿠버네티스·인프라

- 이미지 태그는 고정한다(`latest` 금지).
- 모든 컨테이너에 resources requests/limits를 둔다(집 PC 한 대에 많은 것이 같이 뜬다).
- ServiceAccount·RBAC는 최소 권한. 쓰기 권한은 데모 네임스페이스로 한정한다.
- 비밀값은 매니페스트에 평문으로 두지 않는다(온프레미스는 SOPS, AKS는 Key Vault + Workload Identity).
- 배포 리소스 이름은 kebab-case(`hoa-agent`).

## 네이밍

- 파일·함수: `snake_case`. 클래스: `PascalCase`.
- 1회성 실험 스크립트와 운영 스크립트를 구분해 위치시킨다(`CLAUDE.md` §2 — `scripts/` vs `research/`).

## 백로그

- 없음.
```

- [x] **Step 3: 구조 확인**

Run: `grep '^## ' docs/standards/coding-standard.md`
Expected: `패키지 경계`·`외부 호출 격리`·`타입·데이터`·`주석·docstring`·`에러 처리`·`테스트`·`쿠버네티스·인프라`·`네이밍`·`백로그` 9개.

- [x] **Step 4: 커밋**

```bash
git add docs/standards/coding-standard.md
git commit -m "[Docs] round00 — 코딩 표준: 워크스페이스 멤버 경계·LLM/k8s 호출 격리·Pydantic 경계 타입·가짜 LLM TDD·k8s 매니페스트 규칙"
```

---

### Task 9: `docs/ops/recurring-gotchas.md`

**Files:**
- Create: `docs/ops/recurring-gotchas.md`

- [x] **Step 1: 파일 없음 확인**

Run: `ls docs/ops 2>&1`
Expected: `No such file or directory`

- [x] **Step 2: 작성**

Task 3에서 gitleaks 훅은 Go가 없어도 pre-commit이 툴체인을 직접 받아 그대로 돌았으므로 gitleaks 항목은 없다. Task 5 Step 4 스모크에서 실제로 겪은 devcontainer 이미지 빌드 실패를 2번, Windows 호스트와 작업 폴더를 공유해서 생긴 컨테이너 git 문제를 3번으로 싣는다.

```markdown
# 반복 함정 (Recurring Gotchas)

개발 환경·클러스터·클라우드·실데이터처럼 실제로 돌려 봐야만 드러나는 패턴을 기록한다. 겪을 때마다 아래에 `## N. 제목` 섹션을 추가한다 — 라운드 문서가 아니라 상시 갱신 문서다. 표가 아니라 산문 섹션인 이유: 항목 하나가 원인 여러 개·하위 절차·쉘 명령(`|` 포함)을 가지는 경우가 흔한데, 표 셀에는 이게 안 들어간다.

각 섹션 구성: 날짜 · 증상 · 원인 · 해결 · 재발 방지.

## 1. Windows에서 커밋할 때 "LF will be replaced by CRLF" 경고

- **날짜**: 2026-11-09 (round00)
- **증상**: Windows 개발 PC에서 `git commit` 때 `warning: in the working copy of '<파일>', LF will be replaced by CRLF the next time Git touches it`가 뜬다.
- **원인**: 전역 설정 `core.autocrlf=true`가 작업 사본을 CRLF로 바꾸려 한다. 같은 파일을 Linux(집 PC·CI·컨테이너)에서 쓰면 줄바꿈이 섞이고, 셸 스크립트는 줄 끝의 `\r` 때문에 `bad interpreter`로 죽는다.
- **해결**: 저장소 `.gitattributes`에 `* text=auto eol=lf`를 둔다. `eol` 속성은 개인 설정 `core.autocrlf`보다 우선하므로 작업 사본도 LF로 고정된다(PowerShell 스크립트만 CRLF). 이미 들어간 파일은 `git add --renormalize .`로 다시 정규화한다.
- **재발 방지**: 확인은 `git ls-files --eol`에서 텍스트 파일이 모두 `i/lf w/lf`인지 본다(`.ps1`은 `w/crlf`, 이미지는 `-text`). Windows 전용 파일 종류가 새로 생기면 `.gitattributes`에 규칙을 더한다.

## 2. devcontainer 이미지 빌드가 Yarn 저장소 서명 오류로 실패

- **날짜**: 2026-11-09 (round00)
- **증상**: `devcontainer up`이 기능(feature) 설치 중 `E: The repository 'https://dl.yarnpkg.com/debian stable InRelease' is not signed.`(`NO_PUBKEY 62D54FD4003F6525`)를 내고 `Feature "Docker (docker-outside-of-docker)" ... failed to install!`로 멈춘다.
- **원인**: 이미지 태그 `mcr.microsoft.com/devcontainers/python:1-3.12-bookworm`은 이미지 1번대에서 갱신이 멈춘 태그라, 서명 키가 만료된 Yarn apt 저장소(`/etc/apt/sources.list.d/yarn.list`)가 남아 있다. 기능 설치 스크립트의 `apt-get update`가 이 저장소에서 실패한다.
- **해결**: 현재 메이저 태그 `3-3.12-bookworm`을 쓴다(Yarn 저장소가 없다).
- **재발 방지**: devcontainer 이미지는 현재 메이저 태그를 쓴다. 태그를 바꿀 때는 `docker run --rm --entrypoint sh <이미지> -c 'ls /etc/apt/sources.list.d/'`로 남아 있는 서드파티 저장소를 먼저 보고, `npx -y @devcontainers/cli up --workspace-folder .`로 실제 기동까지 확인한다.

## 3. Windows 호스트와 공유한 작업 폴더에서 컨테이너 git이 멈추고 훅이 안 돎

- **날짜**: 2026-11-09 (round00)
- **증상**: devcontainer 안에서 `git status`가 `fatal: detected dubious ownership in repository at '/workspaces/hybrid-ops-agent'`로 멈춘다. `safe.directory`로 넘겨도 `git commit`이 `cannot exec '.git/hooks/pre-commit': No such file or directory`로 실패한다(훅을 직접 실행하면 `not found`, 종료 코드 127).
- **원인**: (1) Windows 호스트의 작업 폴더는 bind mount 안에서 컨테이너 사용자(`vscode`)와 소유자가 달라, git의 소유자 검사가 저장소를 거부한다. (2) `.git/hooks`는 추적되지 않는 파일이라 `.gitattributes`가 적용되지 않는데, 호스트(Windows)의 pre-commit이 훅 스크립트를 CRLF로 쓴다. 첫 줄 `#!/bin/sh\r`의 `\r` 때문에 Linux가 인터프리터를 찾지 못한다(Git Bash는 이를 견딘다).
- **해결**: `postCreateCommand` 맨 앞에서 `sudo git config --system --replace-all safe.directory ${containerWorkspaceFolder}`로 작업 폴더를 등록한다(시스템 설정이라 VS Code가 복사해 넣는 `~/.gitconfig`에 덮이지 않는다). 커밋은 호스트에서 한다 — 컨테이너에서 `pre-commit install`로 훅을 다시 쓰면 이번엔 호스트 커밋이 깨진다(훅이 컨테이너 Python 경로를 가리킨다).
- **재발 방지**: 컨테이너는 도구(uv·kubectl·helm·terraform·az)와 테스트·`pre-commit run`용으로 쓰고, `git commit`은 호스트에서 한다(`GIT_WORKFLOW.md` §개발 환경). 컨테이너의 venv는 `UV_PROJECT_ENVIRONMENT`로 작업 폴더 밖에 둬서 호스트 `.venv`를 건드리지 않는다.
```

- [x] **Step 3: 구조 확인**

Run: `grep -c '^## [0-9]' docs/ops/recurring-gotchas.md`
Expected: `3`

- [x] **Step 4: 커밋**

```bash
git add docs/ops/recurring-gotchas.md
git commit -m "[Docs] round00 — 반복 함정 문서를 열고 1번(Windows autocrlf 로 LF→CRLF 경고, .gitattributes eol=lf 로 해결)·2번(devcontainer 1번대 이미지의 만료된 Yarn 키로 빌드 실패, 3번대 태그로 해결)·3번(Windows 호스트 공유 폴더에서 컨테이너 git 소유자 거부·CRLF 훅, safe.directory 와 호스트 커밋으로 해결)을 기록한다"
```

---

### Task 10: 라운드 문서 템플릿 — 완료노트 · 교본

**Files:**
- Create: `docs/roadmap/_ROUND_COMPLETE_TEMPLATE.md`
- Create: `docs/guides/_TEMPLATE.md`

NL-Lib 템플릿에서 「디자인 참조」(이 프로젝트엔 디자인 트랙이 없다)를 빼고, 「수치」와 「Azure 비용」을 더한다.

- [x] **Step 1: 파일 없음 확인**

Run: `ls docs/roadmap docs/guides 2>&1`
Expected: 두 폴더 모두 `No such file or directory`

- [x] **Step 2: `docs/roadmap/_ROUND_COMPLETE_TEMPLATE.md` 작성**

```markdown
# round<NN> 완료노트

날짜: <YYYY-MM-DD>
브랜치: `<type>/round<NN>-<설명>`
spec: `docs/superpowers/specs/<파일>`
plan: `docs/superpowers/plans/<파일>`
교본: `docs/guides/round<NN>/<파일>`

## 한 일
-

## 결정
-

## 수치
(평가 러너·RAGAS·지연·비용처럼 이 라운드에서 잰 값. 잰 것이 없으면 "없음". 사람 검증 없이 LLM 채점만 거친 수치는 그렇다고 적는다.)
-

## Azure 비용
(이 라운드에서 만들거나 켠 Azure 리소스와 끈 시각. 쓰지 않았으면 "사용 안 함".)
-

## 이월
-

## 다음 라운드 진입점
-

## 상태
- [ ] code-reviewer 정적 리뷰 통과(high·medium 수정, low는 수정하거나 「결정」에 이유)
- [ ] CI green(작업 브랜치 마지막 커밋)
- [ ] 수동 스모크 확인
- [ ] 문서 갱신(교본·00_status·실제로 돌려 보며 새로 겪은 함정(개발 환경 포함)을 `docs/ops/recurring-gotchas.md`에 추가)
- [ ] Azure 리소스 정지 확인(AKS를 켠 라운드만 — `az aks show -g <그룹> -n <클러스터> --query powerState.code -o tsv`가 `Stopped`. 켜지 않은 라운드는 「해당 없음」을 덧붙이고 체크)
- [ ] `dev` 머지 승인
- [ ] `dev→main` 머지 + push 완료
```

- [x] **Step 3: `docs/guides/_TEMPLATE.md` 작성**

````markdown
# round<NN> 교본 — <제목>

> 이 문서 하나만 보고 그대로 클론코딩할 수 있어야 한다. 전체 코드 수록, 발췌·플레이스홀더 금지(`GIT_WORKFLOW.md` §개발 가이드 문서).

## 0. 사용자 프롬프트 (paraphrase)
> <사용자가 이 라운드에서 실제로 요청한 내용을 의도가 드러나게 재서술>

## 1. 설계 요약
(spec 링크: `docs/superpowers/specs/<파일>` — 이 라운드에서 내린 결정과 그 이유를 적는다)

## 2. 개념 입문
(이 라운드에 처음 나온 개념을 기초부터 적는다 — 개념마다 쉬운 정의 한두 문장과, 이 저장소에서 실제로 쓴 곳)
### 2.1 <개념>
<쉬운 정의>

**여기서는**: <이 저장소에서 쓴 곳>

## 3. 구현 (클론코딩)
### 3.1 <파일/컴포넌트명>
**파일**: `<경로>`

```<언어>
<전체 코드 — 발췌 금지>
```

*(필요한 만큼 3.2, 3.3 … 반복. 담을 파일 내용에 코드펜스(```)가 이미 들어있으면 바깥 펜스를 4개 백틱(````)이나 `~~~~`로 써서 조기 종료를 막는다.)*

## 4. 검증
- 실행 명령과 기대 출력을 그대로 적는다.

## 5. 면접식 Q&A
**Q1. <질문>**

A. <답변>
````

- [x] **Step 4: 구조 확인**

Run: `grep '^## ' docs/roadmap/_ROUND_COMPLETE_TEMPLATE.md docs/guides/_TEMPLATE.md`
Expected: 완료노트 7개(`한 일`·`결정`·`수치`·`Azure 비용`·`이월`·`다음 라운드 진입점`·`상태`), 교본 6개(`0.`~`5.`).

- [x] **Step 5: 커밋**

```bash
git add docs/roadmap/_ROUND_COMPLETE_TEMPLATE.md docs/guides/_TEMPLATE.md
git commit -m "[Docs] round00 — 완료노트·교본 템플릿: NL-Lib 구성에서 디자인 참조를 빼고 수치·Azure 비용·리소스 정지 확인을 더한다"
```

---

### Task 11: `.claude/agents/code-reviewer.md`

**Files:**
- Create: `.claude/agents/code-reviewer.md`

- [x] **Step 1: 파일 없음 확인**

Run: `ls .claude 2>&1`
Expected: `No such file or directory`

- [x] **Step 2: 작성**

```markdown
---
name: code-reviewer
description: 라운드 코드·인프라·문서를 영역별로 정적 리뷰한다. 정확성·코딩표준·보안(RBAC·비밀값·쓰기 도구 경로)·인프라 비용·문서 일관성을 severity로 보고. 읽기 전용(파일·git·클러스터·클라우드 미수정). 라운드 리뷰 단계에서 영역마다 병렬로 띄워 쓴다.
tools: Read, Grep, Glob
model: opus
---

너는 이 프로젝트(hybrid-ops-agent — 온프레미스 k3s와 Azure AKS를 함께 쓰는 쿠버네티스 운영 에이전트)의 정적 리뷰어다. 지정된 영역(코드 디렉터리·인프라 정의·문서 집합)을 읽고 결함을 찾아 보고한다. 파일을 수정하지 않는다. git·kubectl·helm·terraform·az·테스트를 실행하지 않는다. 리뷰할 범위(파일 목록·변경 내용·명령 출력)는 호출하는 쪽이 프롬프트로 넘긴다.

## 프로젝트 맥락 (판단 기준)
- 전체 설계: `docs/superpowers/specs/2026-11-09-hybrid-ops-agent-design.md`. 이번 라운드 범위는 그 라운드의 spec·plan(`docs/superpowers/plans/`)이 정한다 — 뒤 라운드 기능이 아직 없다는 것은 결함이 아니다.
- 에이전트: LangGraph(triage → supervisor → 서브에이전트 → 진단 → 조치 계획(`propose_fix`, 허용 목록 안) → 사람 승인 → 실행·검증 → postmortem). 에이전트의 클러스터 접근은 MCP 서버를 거쳐서만 한다 — 에이전트가 아닌 예외 두 곳(graphrag 동기화 잡·eval 장애 주입)은 `docs/standards/coding-standard.md` 「외부 호출 격리」.
- 배치: 상태 있는 것(Neo4j·Postgres·vLLM·관측)은 상시 켜진 온프레미스에, AKS에는 상태 없는 앱만 둔다. AKS는 작업할 때만 켠다.
- 코딩 표준 정본: `docs/standards/coding-standard.md`. 그 문서 「백로그」에 적힌 반례는 새 결함으로 재보고하지 않는다 — 신규/수정 코드가 반례를 새로 늘리는 경우에만 지적한다.

## 점검 항목
1. **정확성**: 버그·엣지케이스·미구현(placeholder)·죽은 코드.
2. **코딩표준**: 워크스페이스 멤버 경계(다른 멤버 내부 import, 이미지에 불필요한 의존성), LLM 호출이 `llm.py`를 거치는지·주입되는지, 경계 데이터가 Pydantic 모델인지, 신규 기능에 테스트가 있는지(TDD).
3. **보안**:
   - 비밀값 하드코딩, 평문 시크릿 매니페스트, 커밋된 kubeconfig·tfstate·tfvars.
   - RBAC 최소 권한 — 쓰기 권한이 데모 네임스페이스 밖으로 새는지, Role/ClusterRole에 `*` 동사·리소스가 있는지.
   - 쓰기 MCP 도구가 허용 목록·서버 측 dry-run·사람 승인을 우회하는 경로.
   - 도구 결과(로그·이벤트·런북 문장)가 구조화된 plan을 거치지 않고 실행 경로로 흘러가는 프롬프트 인젝션 경로.
4. **인프라**: 이미지 태그 고정, resources requests/limits, Terraform이 비용 나는 리소스를 상시 켜 두는지(AKS 자동 정지·예산 알림 누락), CI에 `terraform apply`나 클라우드 쓰기 권한이 들어갔는지, Terraform 변경이 기존 리소스를 교체·삭제하는지(재생성을 일으키는 속성 변경, 상태 있는 리소스의 `lifecycle { prevent_destroy }` 누락). `terraform plan`은 실행하지 않으므로 `.tf` 소스와 호출하는 쪽이 붙여 준 plan 출력으로 본다.
5. **일관성**(문서 리뷰 시): 문서↔코드, 문서 간(어휘·스택·결정) 정합 + stale 서술. 교본은 실제 파일과 한 글자도 다르지 않아야 한다(전체 수록 규칙).
6. **반복 함정**(`docs/ops/recurring-gotchas.md`): 리뷰 전에 먼저 읽고, 기록된 패턴과 대조한다.

## 보고 형식
- 각 결함: severity(high=동작불가/보안 · medium=표준위반/불일치/누락 · low=개선) · location(파일:라인) · issue(파일 근거로 구체적) · suggestion.
- 추측 금지 — 읽은 근거만. 발견 없으면 "없음"을 명확히.
- 동작을 막는 high는 맨 앞에. 요약 1~2문장 + 결함 목록.
```

- [x] **Step 3: frontmatter 확인**

Run: `head -5 .claude/agents/code-reviewer.md`
Expected: `---` / `name: code-reviewer` / `description: ...` / `tools: Read, Grep, Glob` / `model: opus`

- [x] **Step 4: 커밋**

```bash
git add .claude/agents/code-reviewer.md
git commit -m "[Docs] round00 — code-reviewer 에이전트: NL-Lib 형식을 옮기고 RBAC·쓰기 도구 우회·프롬프트 인젝션 경로·클라우드 비용 점검을 더한다"
```

---

### Task 12: `.claude/skills/round-finish/SKILL.md`

**Files:**
- Create: `.claude/skills/round-finish/SKILL.md`

- [x] **Step 1: 파일 없음 확인**

Run: `ls .claude/skills 2>&1`
Expected: `No such file or directory`

- [x] **Step 2: 작성**

````markdown
---
name: round-finish
description: hybrid-ops-agent 라운드를 종료할 때 사용 — dev에 머지된 라운드를 검증 확인 후 dev→main 머지 + origin push. "라운드 끝내자/라운드 종료/main 올리고 push" 같은 요청에 활성화. 작업 브랜치→dev 머지에는 쓰지 않는다.
---

# round-finish — 라운드 종료 절차

한 라운드(사용자 프롬프트 1개의 구현)가 검증·리뷰까지 끝나 `main`에 올리고 원격에 동기화하는 절차다. 상세 흐름은 `GIT_WORKFLOW.md` §라운드 생애주기.

## 전제 (확인 후 진행)
- 작업 브랜치가 이미 `dev`에 머지돼 있다(사용자 승인 하).
- `dev`의 CI가 green이다 — 원격 상태를 받은 뒤에 봐야 하므로 확인은 절차 6단계에서 한다.
- 핵심 기능 수동 스모크를 확인했다.
- 사용자가 라운드 종료를 승인했다(이 단계는 `main`을 움직이므로 임의 진행 금지). round02부터는 `main` push가 Argo CD 배포를 일으킨다.
- **`main`·`dev` 체크아웃은 주 저장소 디렉토리에서 한다** — 라운드 작업을 격리 워크트리에서 했다면 그 워크트리 안에서 `main`을 체크아웃하지 않는다(그 라운드의 신규 파일이 아직 `main`에 없어 사라져 보이고, `main`·`dev`가 다른 워크트리에 물려 있으면 체크아웃 자체가 거부된다).

## 절차
1. 핵심 동작 수동 스모크를 확인했는지 본다(CI는 6단계에서 원격 기준으로 본다).
2. 완료노트(`docs/roadmap/round<NN>-완료노트.md`)의 `## 상태` 체크리스트(정적 리뷰·CI·스모크·문서 갱신·Azure 정지·머지 승인) 확인.
3. 라운드 중 실제로 돌려 보며 새로 겪은 함정(개발 환경 포함)이 있으면 `docs/ops/recurring-gotchas.md`에 추가됐는지 확인.
4. `docs/roadmap/00_status.md` 갱신 확인(최종 갱신 날짜·현재 상태·다음 할 일·라운드 이력 — 라운드 이력만 바꾸고 현재 상태를 그대로 두지 않는다).
5. AKS를 켠 라운드면 꺼져 있는지 확인: `az aks show -g <그룹> -n <클러스터> --query powerState.code -o tsv` → `Stopped`.
6. **머지 전 확인** — 하나라도 어긋나면 중단하고 사용자에게 보고한다:
   ```bash
   git fetch origin
   git status --porcelain                          # 출력이 있으면 중단 — 커밋 안 된 변경
   git merge-base --is-ancestor origin/<작업 브랜치> dev && echo merged || echo 중단   # merged가 아니면 중단 — 완료노트 「브랜치:」 줄의 작업 브랜치가 dev에 머지되지 않았거나 원격에 없다
   git rev-parse dev origin/dev                    # 두 값이 다르면 중단 — 로컬만 앞서면 dev를 push해 CI부터, 원격이 앞서면(다른 PC에서 push) 먼저 받아서 정리
   git rev-parse main origin/main                  # 두 값이 다르면 중단 — 원격이 앞서면 먼저 받아서 정리, 로컬에만 있는 커밋이면 원인부터 확인
   gh run list --workflow ci.yml --event push --branch dev --limit 1 --json status,conclusion,headSha
   ```
   마지막 명령은 `status`가 `completed`, `conclusion`이 `success`이고 `headSha`가 `git rev-parse origin/dev`와 같아야 한다 — 진행 중인 실행이나 이전 커밋의 실행을 green으로 보지 않는다.
7. `dev → main` 머지
   ```bash
   git checkout main
   git merge --no-ff dev -m "Merge dev into main — round<NN> (<요약>)"
   ```
8. origin push
   ```bash
   git push origin main
   ```
   (`dev`는 6단계에서 원격과 같다는 것을 확인했으므로 다시 push하지 않는다.)
9. push 뒤 `main` CI 확인: `gh run list --workflow ci.yml --event push --branch main --limit 1 --json databaseId,headSha`에서 `headSha`가 `git rev-parse origin/main`인 실행을 `gh run watch <databaseId> --exit-status`로 끝까지 본다. push 직후라 그 실행이 아직 없으면(`headSha`가 다르면) 잠시 뒤 다시 조회한다. 실패하면 멈추고 사용자에게 보고한다(round02부터는 배포가 이미 시작됐을 수 있다).
10. 작업 복귀: `git checkout dev`.
11. 완료노트 「상태」의 마지막 줄(`dev→main` 머지 + push 완료)은 이 절차 뒤 `dev`에서 체크·커밋해 `dev`에만 push한다 — 그 한 줄 때문에 `main`을 다시 머지하지 않는다(다음 라운드 머지 때 함께 올라간다).

## 주의
- 평소 작업은 `dev`에서 분기 → 작업 브랜치. `main` 직접 작업은 이 종료 절차에서만.
- 머지 충돌이나 커밋 안 된 변경이 있으면 진행하지 말고 사용자에게 보고한다.
- 비밀정보·kubeconfig·Terraform state는 커밋·push 금지(`.gitignore`). public 저장소다.
- round02에서 Argo CD가 들어오면 이 절차에 "push 뒤 Argo CD 동기화 상태 확인" 단계를 더한다.
````

- [x] **Step 3: frontmatter 확인**

Run: `head -4 .claude/skills/round-finish/SKILL.md`
Expected: `---` / `name: round-finish` / `description: hybrid-ops-agent 라운드를 종료할 때 사용 ...` / `---`

- [x] **Step 4: 커밋**

```bash
git add .claude/skills/round-finish/SKILL.md
git commit -m "[Docs] round00 — round-finish 스킬: NL-Lib 종료 절차를 옮기고 CI green 확인·AKS 정지 확인·main push 뒤 CI 확인을 더한다"
```

---

### Task 13: `README.md`

**Files:**
- Create: `README.md`

- [x] **Step 1: 파일 없음 확인**

Run: `ls README.md 2>&1`
Expected: `No such file or directory`

- [x] **Step 2: 작성**

````markdown
# hybrid-ops-agent

온프레미스(집 GPU PC의 k3s)와 Azure(AKS·Azure OpenAI)를 함께 쓰는 **쿠버네티스 운영 에이전트**. 클러스터 장애를 MCP 도구로 조사하고, GraphRAG로 비슷한 과거 장애와 런북을 찾아 원인을 진단하고, 사람 승인을 받아 조치한다.

> 학습 목적의 개인 프로젝트다. 라운드 단위로 쌓아 가며 라운드마다 설계(spec)·계획(plan)·완료노트·교본을 남긴다.

## 무엇을 해 보나

| 기술 | 이 프로젝트에서의 역할 |
|---|---|
| LangGraph 멀티에이전트 | supervisor + 서브에이전트, 체크포인트(중단·재개), interrupt로 사람 승인 |
| MCP 서버·클라이언트 | 클러스터 조회·조치·관측 도구를 MCP 서버로 직접 만들고 에이전트가 MCP로 호출 |
| GraphRAG | Neo4j에 클러스터 구조 + 장애 지식 그래프, 벡터 RAG와 진단 정확도 비교 |
| 쿠버네티스 + IaC | 온프레미스 k3s + Azure AKS, Terraform, Helm, Argo CD, GitHub Actions |
| 관측·자동 평가 | Prometheus·Loki·Tempo, OpenTelemetry → Langfuse, 장애 시나리오 자동 채점 |

## 어디서 무엇이 도나

| 위치 | 켜짐 | 역할 |
|---|---|---|
| 집 RTX 3060 PC (Ubuntu + k3s) | 상시 | 로컬 LLM, Neo4j, Postgres, 관측 스택, Argo CD, 데모 앱·에이전트·MCP 서버 |
| Azure AKS | 작업할 때만 | 상태 없는 앱(에이전트 API·MCP 서버·웹 UI), 데모 앱 사본 |
| Azure OpenAI | 사용량 과금 | 계획·진단·그래프 추출 |
| Langfuse Cloud | 상시(SaaS) | 에이전트 트레이스·평가 데이터셋 |

자세한 설계와 라운드 로드맵: [전체 설계 spec](docs/superpowers/specs/2026-11-09-hybrid-ops-agent-design.md) · 진행 상황: [docs/roadmap/00_status.md](docs/roadmap/00_status.md)

## 시작하기

[uv](https://docs.astral.sh/uv/) 0.11(0.11.31 이상 — `pyproject.toml`의 `[tool.uv] required-version`)이 필요하다(Python 3.12는 uv가 준비한다). CI 결과 확인과 라운드 종료 절차에는 [GitHub CLI](https://cli.github.com/)(`gh auth login`)를 쓴다.

```bash
uv sync
uv run pre-commit install
uv run pytest
uv run hoa --version
```

devcontainer(`.devcontainer/`)를 쓰면 uv·kubectl·helm·terraform·az가 갖춰진 컨테이너에서 `uv run pytest`·`uv run hoa --version`을 그대로 쓴다(`uv sync`는 컨테이너를 만들 때 끝난다). `pre-commit install`과 커밋은 호스트에서 한다 — [GIT_WORKFLOW.md](GIT_WORKFLOW.md) §개발 환경.

## 문서

- [CLAUDE.md](CLAUDE.md) — 작업 진입점(어떤 문서를 어디서 보나)
- [GIT_WORKFLOW.md](GIT_WORKFLOW.md) — 브랜치·커밋·품질 게이트·라운드 생애주기
- [docs/standards/coding-standard.md](docs/standards/coding-standard.md) — 코딩 표준
````

- [x] **Step 3: 링크 대상 확인**

Run: `for p in docs/superpowers/specs/2026-11-09-hybrid-ops-agent-design.md CLAUDE.md GIT_WORKFLOW.md docs/standards/coding-standard.md .devcontainer; do ls -d "$p" >/dev/null && echo "OK $p"; done`
Expected: 5줄 모두 `OK`. (`docs/roadmap/00_status.md`는 Task 14에서 만든다.)

- [x] **Step 4: 커밋**

```bash
git add README.md
git commit -m "[Docs] round00 — README: 프로젝트 소개·학습 대상 기술·배치 요약·시작하기"
```

---

### Task 14: `docs/roadmap/00_status.md`

**Files:**
- Create: `docs/roadmap/00_status.md`

- [x] **Step 1: 파일 없음 확인**

Run: `ls docs/roadmap/00_status.md 2>&1`
Expected: `No such file or directory`

- [x] **Step 2: 작성**

```markdown
# 현재 상태 · 다음 할 일

최종 갱신: 2026-11-09 (round00 진행 중 — 저장소 골격·라운드 방식 이식)

## 현재 상태
- 전체 설계 확정: `docs/superpowers/specs/2026-11-09-hybrid-ops-agent-design.md`.
- round00 진행 중 — uv 워크스페이스(`agent` 멤버, `hoa` CLI), pre-commit(ruff·gitleaks), GitHub Actions CI, devcontainer, 라운드 운영 문서(CLAUDE.md·GIT_WORKFLOW.md·코딩 표준·반복 함정·템플릿·code-reviewer·round-finish).

## 다음 할 일
- round00 마무리: 원격 첫 push와 CI 확인 → code-reviewer 리뷰 → 교본·완료노트 → `dev` 머지(승인) → `main` 머지·push(승인).
- round01 — 끝-끝 경로: 개발 PC kind + 데모 앱(gateway·orders·inventory) + 장애 2종 + MCP `k8s-read` + 단일 LangGraph 에이전트 + Azure OpenAI, 평가 러너 v0. 착수 전에 Azure 구독과 Azure OpenAI 배포 모델·리전을 정한다(spec §10).

## 라운드 이력
| 라운드 | 요약 | 상태 |
|---|---|---|
| round00 | 저장소 골격 + 라운드 방식 이식 | 진행 중 |
```

- [x] **Step 3: 커밋**

```bash
git add docs/roadmap/00_status.md
git commit -m "[Docs] round00 — 00_status: 현재 상태(round00 진행 중)·다음 할 일(round00 마무리, round01 끝-끝 경로)·라운드 이력"
```

---

### Task 15: 원격 첫 push와 CI 확인 — **사용자 승인 필요**

public 저장소에 처음 올리는 단계다(첫 공개 push라 예외로 승인을 받는다 — 그 뒤의 push 규칙은 `CLAUDE.md` §3). 시작 전에 사용자에게 "로컬 검증이 끝났으니 `main`·`dev`·`feat/round00-scaffold`를 push해도 되는지" 묻고 승인을 받는다.

- [x] **Step 1: 로컬 전체 검증**

Run:
```bash
uv sync --locked
uv run pre-commit run --all-files
uv run pytest -v
git status --short
```
Expected: 모든 훅 `Passed`, `2 passed`, `git status --short` 출력 없음(커밋 안 된 변경 없음).

- [x] **Step 2: [승인 뒤] push — `main`을 먼저 올려 기본 브랜치로 만든다**

Run:
```bash
git push -u origin main
git push -u origin dev
git push -u origin feat/round00-scaffold
gh repo view Jeonghyun-An/hybrid-ops-agent --json defaultBranchRef --jq .defaultBranchRef.name
```
Expected: 세 push 성공, 기본 브랜치 `main`. 다르게 나오면 `gh repo edit Jeonghyun-An/hybrid-ops-agent --default-branch main`.

- [x] **Step 3: CI 결과 확인**

Run:
```bash
gh run list --repo Jeonghyun-An/hybrid-ops-agent --branch feat/round00-scaffold --limit 1
gh run watch --repo Jeonghyun-An/hybrid-ops-agent --exit-status $(gh run list --repo Jeonghyun-An/hybrid-ops-agent --branch feat/round00-scaffold --limit 1 --json databaseId --jq '.[0].databaseId')
```
Expected: `린트·테스트`·`비밀값 검사(gitleaks, 전체 이력)` 두 잡 모두 ✓, 종료 코드 0.

실패하면 `gh run view <id> --log-failed`로 원인을 보고 고친다. gitleaks가 무언가를 찾았다면 **고치기 전에 사용자에게 먼저 알린다**(public 이력에 이미 올라간 값이면 키 폐기가 필요하다).

---

### Task 16: 정적 리뷰 — code-reviewer

- [x] **Step 1: 영역별 리뷰를 병렬로 띄운다**

이 저장소를 작업 폴더로 연 세션이면 `code-reviewer` 에이전트를 쓴다. 다른 저장소(NL-Lib 등)를 작업 폴더로 연 세션이면 그 세션의 `code-reviewer`는 NL-Lib 맥락이므로 쓰지 않는다 — general-purpose 에이전트에 "`C:\Users\LANDSOFT\mygit\hybrid-ops-agent\.claude\agents\code-reviewer.md`를 읽고 그 지시대로 리뷰하라, 파일은 수정하지 마라"고 넘긴다.

두 영역을 한 메시지에서 동시에 띄운다:
- 영역 A(코드·설정): `pyproject.toml`·`agent/`·`uv.lock`(의존성만)·`.pre-commit-config.yaml`·`.github/workflows/ci.yml`·`.devcontainer/devcontainer.json`·`.gitattributes`·`.gitignore`. 기준: spec §7 round00 행, 이 plan Task 1~5.
- 영역 B(문서): `CLAUDE.md`·`GIT_WORKFLOW.md`·`README.md`·`docs/standards/`·`docs/ops/`·`docs/roadmap/`·`docs/guides/_TEMPLATE.md`·`.claude/`. 기준: spec §8, 문서 간 어휘·경로·결정 정합.

- [x] **Step 2: 발견 반영**

high·medium은 모두 고친다. low는 고치거나, 고치지 않는 이유를 완료노트 「결정」에 한 줄로 적는다. 고친 것마다 커밋한다(`[Fix] round00 — <무엇을>`). 고친 뒤 Task 15 Step 1의 로컬 검증을 다시 돌리고 `git push`로 CI를 다시 확인한다.

---

### Task 17: 교본 · 완료노트 · 00_status 마감

**Files:**
- Create: `docs/guides/round00/00-개요.md`
- Create: `docs/roadmap/round00-완료노트.md`
- Modify: `docs/roadmap/00_status.md`

- [x] **Step 1: 교본 작성 — `docs/guides/round00/00-개요.md`**

`docs/guides/_TEMPLATE.md` 구성을 따른다. 「3. 구현」에는 아래 파일을 **최종 커밋 상태 그대로**(리뷰 수정 반영본) 순서대로 한 절씩 싣는다. 내용은 손으로 옮기지 말고 `cat <파일>` 출력을 그대로 붙인다. 코드펜스가 들어 있는 파일(`GIT_WORKFLOW.md`·`README.md`·`docs/guides/_TEMPLATE.md`·`.claude/skills/round-finish/SKILL.md`)은 바깥 펜스를 `~~~~`로 쓴다.

순서: `.gitattributes` → `.gitignore` → `.python-version` → `pyproject.toml` → `agent/pyproject.toml` → `agent/src/hoa_agent/__init__.py` → `agent/src/hoa_agent/cli.py` → `agent/tests/test_cli.py` → `.pre-commit-config.yaml` → `.github/workflows/ci.yml` → `.devcontainer/devcontainer.json` → `CLAUDE.md` → `GIT_WORKFLOW.md` → `docs/standards/coding-standard.md` → `docs/ops/recurring-gotchas.md` → `docs/roadmap/_ROUND_COMPLETE_TEMPLATE.md` → `docs/guides/_TEMPLATE.md` → `.claude/agents/code-reviewer.md` → `.claude/skills/round-finish/SKILL.md` → `README.md`. (`uv.lock`은 생성물이라 싣지 않고 「4. 검증」에 `uv sync`로 생성된다고 적는다.)

「0. 사용자 프롬프트」:
> NL-Lib에서 쓰던 라운드 개발 방식을 새 프로젝트에 옮겨, 클라우드(Azure)와 온프레미스(집 RTX 3060 PC)를 함께 쓰는 에이전트 시스템을 만들고 싶다. 많이 안 해본 것 위주로 — GraphRAG, LangGraph 멀티에이전트, MCP, 쿠버네티스 + IaC, 관측·자동 평가. round00은 그 출발점으로 빈 저장소에 개발 체계와 품질 게이트를 세운다.

「1. 설계 요약」: spec 링크, 그리고 이번 라운드 결정 네 가지 — (1) uv 워크스페이스 멤버 분리(이미지별 의존성), (2) 품질 게이트는 대상 파일이 있는 것만 라운드별로 도입, (3) gitleaks 이중화(pre-commit + CI 전체 이력), (4) `.gitattributes`로 LF 고정.

「2. 개념 입문」: 이 라운드에 처음 나온 개념을 기초부터 한 절씩 적는다(쉬운 정의 + `**여기서는**:` 이 저장소에서 쓴 곳) — 패키지 매니저와 잠금 파일, 워크스페이스, 콘솔 스크립트, TDD, 린터와 포매터, Git 훅과 pre-commit, CI(GitHub Actions), 비밀값 스캐닝, 줄 끝 문자, 컨테이너와 devcontainer, `--no-ff` 머지, 공급망 보안(태그 vs 커밋 SHA). 학습 프로젝트라 처음 보는 분야도 익힐 수 있게 하라는 사용자 요청(2026-11-10)으로 더한 절이다.

「4. 검증」: Task 15 Step 1의 명령 4개와 실제 출력, CI 실행 결과(실행 ID와 두 잡 결론).

「5. 면접식 Q&A」 — 아래 9문항을 그대로 싣는다:

**Q1. 왜 Python 코드를 uv 워크스페이스의 여러 멤버로 나눴나?**

A. 멤버마다 컨테이너 이미지가 따로 나가기 때문이다. MCP 서버 이미지에 LangGraph까지 들어가면 이미지가 커지고 공격 면도 넓어진다. 워크스페이스는 멤버별 의존성을 분리하면서도 잠금 파일(`uv.lock`) 하나로 버전을 일관되게 묶는다. 다른 멤버의 내부 모듈을 import하지 못하게 하는 경계 역할도 한다.

**Q2. 루트 `pyproject.toml`에 `[build-system]`이 없는 이유는?**

A. 루트는 배포할 패키지가 아니라 워크스페이스와 개발 도구(pytest·ruff·pre-commit)를 묶는 자리다. uv는 build-system이 없는 프로젝트를 패키지로 빌드·설치하지 않고 의존성만 맞춘다. 실제 코드는 멤버(`agent/`)가 hatchling으로 빌드한다.

**Q3. CI에서 `uv sync`가 아니라 `uv sync --locked`를 쓰는 이유는?**

A. `--locked`는 잠금 파일이 `pyproject.toml`과 어긋나면 실패한다. 로컬에서 의존성을 바꾸고 `uv.lock` 갱신을 빠뜨린 커밋을 CI가 잡고, CI가 개발 PC와 같은 버전으로 테스트한다는 것을 보장한다.

**Q4. gitleaks를 pre-commit과 CI 두 곳에 둔 이유는?**

A. pre-commit은 스테이징된 변경만 빠르게 보고, `--no-verify`나 훅 미설치로 건너뛸 수 있다. CI는 `fetch-depth: 0`으로 전체 이력을 다시 본다. public 저장소는 한 번 push된 비밀값을 이력에서 지워도 이미 노출된 것으로 봐야 하므로(키 폐기만이 해결) 두 겹으로 막는다.

**Q5. `.gitattributes`의 `eol=lf`와 `core.autocrlf`는 무엇이 다른가?**

A. `core.autocrlf`는 사람마다 다른 개인 설정이고, `.gitattributes`는 저장소에 커밋되어 모두에게 같은 규칙을 강제한다. `eol` 속성은 `core.autocrlf`보다 우선한다. Windows에서 만든 셸 스크립트가 CRLF로 Linux(집 PC·CI·컨테이너)에 가면 줄 끝 `\r` 때문에 실행이 실패하므로 LF로 고정했다.

**Q6. argparse의 `action="version"`은 테스트에서 어떻게 다뤘나?**

A. 이 액션은 버전을 출력한 뒤 `SystemExit(0)`을 던진다. 테스트는 `pytest.raises(SystemExit)`로 잡아 종료 코드가 0인지, `capsys`로 표준출력이 `hoa <버전>`인지 확인한다. 콘솔 스크립트는 `main()`의 반환값을 `sys.exit`에 넘기므로 `main`은 정상 종료 시 0을 반환한다.

**Q7. `dev` 브랜치를 클러스터에 배포하지 않고 CI로만 검증하는 이유는?**

A. 상시 클러스터가 집 PC 한 대뿐이고 AKS는 작업할 때만 켜므로 환경을 둘로 나눌 자원이 없다. 대신 `main`을 Argo CD가 보게 해 "main = 배포 기준"을 GitOps로 문자 그대로 만들고, `dev`는 통합 검증(CI, round01부터 kind 통합 테스트)에 쓴다.

**Q8. helm lint·terraform validate 같은 게이트를 round00에 미리 넣지 않은 이유는?**

A. 검사할 Helm 차트나 Terraform 파일이 아직 없으면 그 게이트는 늘 통과하고 아무것도 증명하지 못한다. 대상 파일이 처음 생기는 라운드(round02·round03)에 게이트를 더하고, 그 라운드의 완료 기준에 포함한다.

**Q9. 혼자 하는 프로젝트인데 브랜치·리뷰·승인 절차를 지키는 이유는?**

A. 코드 대부분을 에이전트(Claude)가 쓰므로, 사람이 확인하는 지점(spec·계획서 확인·dev 머지 승인·main 머지 승인)이 품질과 안전의 게이트가 된다. 라운드마다 남는 spec·plan·완료노트·교본은 결정의 근거를 기록해서, 나중에 왜 이렇게 만들었는지 설명할 수 있게 해 준다.

- [x] **Step 2: 교본이 실제 파일과 같은지 확인**

Run: `grep -c '^### 3\.' docs/guides/round00/00-개요.md`
Expected: `21` — Step 1 순서 목록의 파일 20개 + `docs/guides/_TEMPLATE.md` 본문 안에 들어 있는 `### 3.1 <파일/컴포넌트명>` 한 줄. 이어서 교본의 코드블록을 뽑아 실제 파일과 diff해 20개가 모두 같은지 확인하고(제목 수만으로는 내용 일치를 보장하지 못한다), code-reviewer(Task 16 영역 B를 한 번 더)로 한 번 더 본다. 커밋 전에는 `uv run pre-commit run ruff-format --files docs/guides/round00/00-개요.md`를 돌린 뒤 `git diff`가 비어 있는지 본다 — ruff format이 교본 안의 python 블록을 고치면 수록본이 실제 파일과 달라진다. 구조도 확인한다 — `grep -c '^### Task'`가 `0`(plan 본문이 섞이지 않았다), `grep -c '^\*\*Q[0-9]'`가 `10`(수록된 교본 템플릿의 `**Q1. <질문>**` 1개 + 9문항), 파일 끝이 Q9 답변이다.

- [x] **Step 3: 완료노트 작성 — `docs/roadmap/round00-완료노트.md`**

`docs/roadmap/_ROUND_COMPLETE_TEMPLATE.md`를 복사해 채운다. 고정 내용:
- 날짜 `2026-11-09`(실제 종료일이 다르면 그 날짜), 브랜치 `feat/round00-scaffold`, spec `docs/superpowers/specs/2026-11-09-hybrid-ops-agent-design.md`, plan `docs/superpowers/plans/2026-11-09-round00-scaffold.md`, 교본 `docs/guides/round00/00-개요.md`.
- 「한 일」: Task 1~14 산출물을 한 줄씩.
- 「결정」: 교본 「1. 설계 요약」의 결정 네 가지 + Task 16에서 고치지 않은 low 발견과 그 이유.
- 「수치」: `없음 — round00은 평가 대상 기능이 없다. 테스트 2개, CI 두 잡.`
- 「Azure 비용」: `사용 안 함`.
- 「이월」: Task 5 Step 4를 못 했으면 `devcontainer 실제 기동 미확인`. 그 밖에 리뷰에서 다음 라운드로 넘긴 것.
- 「다음 라운드 진입점」: `round01 — 끝-끝 경로. 착수 전 Azure 구독과 Azure OpenAI 배포 모델·리전 결정(spec §10), 개발 PC에 kind 설치.`
- 「상태」: 실제로 끝난 항목만 체크한다(이 시점에는 `dev` 머지·`main` 머지 두 줄은 비어 있다).

- [x] **Step 4: `docs/roadmap/00_status.md` 갱신**

- 최종 갱신 줄: `최종 갱신: <날짜> (round00 종료 — 저장소 골격·라운드 방식 이식)`
- 「현재 상태」 두 번째 항목을 `round00 종료 — ...(산출물 목록 그대로). 상세: round00-완료노트.md.`로 바꾼다.
- 「다음 할 일」에서 round00 마무리 항목을 지운다.
- 라운드 이력 행: `| round00 | [저장소 골격 + 라운드 방식 이식](round00-완료노트.md) · [교본](../guides/round00/00-개요.md) | 완료 (main 머지·push) |`

- [x] **Step 5: 커밋과 push**

```bash
git add docs/guides/round00/00-개요.md docs/roadmap/round00-완료노트.md docs/roadmap/00_status.md
git commit -m "[Docs] round00 — 교본(개념 입문 + 전체 파일 수록 + 면접 Q&A 9문항)·완료노트·00_status 마감"
git push
```
Expected: CI 두 잡 green(`gh run list --branch feat/round00-scaffold --limit 1`).

---

### Task 18: 머지 — **단계마다 사용자 승인 필요**

- [x] **Step 1: [승인 뒤] 작업 브랜치 → `dev`**

사용자에게 리뷰 결과·CI 결과·완료노트를 요약해 보여 주고 `dev` 머지 승인을 받는다.

```bash
git checkout dev
git merge --no-ff feat/round00-scaffold -m "Merge feat/round00-scaffold into dev — round00 (저장소 골격·라운드 방식 이식)"
git push origin dev
gh run list --branch dev --limit 1
```
Expected: 머지 성공, `dev` CI green.

- [x] **Step 2: 완료노트 「상태」의 `dev` 머지 승인 체크**

`dev` 위에서 `docs/roadmap/round00-완료노트.md`의 `- [ ] \`dev\` 머지 승인`을 `- [x]`로 바꾸고(「CI green(작업 브랜치 마지막 커밋)」 줄이 아직 비어 있으면 그 커밋의 CI 결과를 확인해 함께 체크한다) 커밋·push:
```bash
git add docs/roadmap/round00-완료노트.md
git commit -m "[Docs] round00 — 완료노트 상태: dev 머지 승인 체크"
git push origin dev
```

- [ ] **Step 2a: [승인 뒤] 수정분 재머지**

첫 `dev` 머지 뒤 사용자 승인으로 `CLAUDE.md`·`GIT_WORKFLOW.md`를 고친 경우(round00에서 실제로 있었다): 작업 브랜치를 `dev`에 맞춘(`git merge --ff-only dev`) 뒤 고치고, code-reviewer 확인과 CI green을 거쳐 사용자 승인을 받아 Step 1과 같은 방식으로 다시 `--no-ff` 머지한다. 그 뒤 `dev`에서 완료노트 「상태」의 리뷰·CI 줄을 최종 커밋 기준으로 고친다.

- [ ] **Step 3: [승인 뒤] 라운드 종료**

사용자가 라운드 종료를 승인하면 `/round-finish` 스킬(`.claude/skills/round-finish/SKILL.md`) 절차대로 `dev → main` 머지 + push. 이 저장소를 작업 폴더로 연 세션이 아니면 스킬이 목록에 없으므로 그 파일을 읽고 절차를 그대로 따른다.

- [ ] **Step 4: 마지막 체크**

`dev`에서 완료노트의 `- [ ] \`dev→main\` 머지 + push 완료`를 `- [x]`로 바꾸고 커밋해 `dev`에만 push한다(`[Docs] round00 — 완료노트 상태: main 머지·push 완료 체크`). 이 한 줄 때문에 `main`을 다시 머지하지 않는다 — 다음 라운드 머지 때 함께 올라간다.
