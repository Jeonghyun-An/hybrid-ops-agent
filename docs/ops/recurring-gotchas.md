# 반복 함정 (Recurring Gotchas)

라이브(클러스터·클라우드·실데이터)에서만 드러나는 패턴을 기록한다. 겪을 때마다 아래에 `## N. 제목` 섹션을 추가한다 — 라운드 문서가 아니라 상시 갱신 문서다. 표가 아니라 산문 섹션인 이유: 항목 하나가 원인 여러 개·하위 절차·쉘 명령(`|` 포함)을 가지는 경우가 흔한데, 표 셀에는 이게 안 들어간다.

각 섹션 구성: 날짜 · 증상 · 원인 · 해결 · 재발 방지.

## 1. Windows에서 커밋할 때 "LF will be replaced by CRLF" 경고

- **날짜**: 2026-11-09 (round00)
- **증상**: Windows 개발 PC에서 `git commit` 때 `warning: in the working copy of '<파일>', LF will be replaced by CRLF the next time Git touches it`가 뜬다.
- **원인**: 전역 설정 `core.autocrlf=true`가 작업 사본을 CRLF로 바꾸려 한다. 같은 파일을 Linux(집 PC·CI·컨테이너)에서 쓰면 줄바꿈이 섞이고, 셸 스크립트는 줄 끝의 `\r` 때문에 `bad interpreter`로 죽는다.
- **해결**: 저장소 `.gitattributes`에 `* text=auto eol=lf`를 둔다. `eol` 속성은 개인 설정 `core.autocrlf`보다 우선하므로 작업 사본도 LF로 고정된다(PowerShell 스크립트만 CRLF). 이미 들어간 파일은 `git add --renormalize .`로 다시 정규화한다.
- **재발 방지**: 확인은 `git ls-files --eol`에서 모든 줄이 `i/lf w/lf`인지 본다. Windows 전용 파일 종류가 새로 생기면 `.gitattributes`에 규칙을 더한다.

## 2. devcontainer 이미지 빌드가 Yarn 저장소 서명 오류로 실패

- **날짜**: 2026-11-09 (round00)
- **증상**: `devcontainer up`이 기능(feature) 설치 중 `E: The repository 'https://dl.yarnpkg.com/debian stable InRelease' is not signed.`(`NO_PUBKEY 62D54FD4003F6525`)를 내고 `Feature "Docker (docker-outside-of-docker)" ... failed to install!`로 멈춘다.
- **원인**: 이미지 태그 `mcr.microsoft.com/devcontainers/python:1-3.12-bookworm`은 이미지 1번대에서 갱신이 멈춘 태그라, 서명 키가 만료된 Yarn apt 저장소(`/etc/apt/sources.list.d/yarn.list`)가 남아 있다. 기능 설치 스크립트의 `apt-get update`가 이 저장소에서 실패한다.
- **해결**: 현재 메이저 태그 `3-3.12-bookworm`을 쓴다(Yarn 저장소가 없다).
- **재발 방지**: devcontainer 이미지는 현재 메이저 태그를 쓴다. 태그를 바꿀 때는 `docker run --rm --entrypoint sh <이미지> -c 'ls /etc/apt/sources.list.d/'`로 남아 있는 서드파티 저장소를 먼저 보고, `npx -y @devcontainers/cli up --workspace-folder .`로 실제 기동까지 확인한다.

## 3. Windows 호스트와 공유한 작업 폴더에서 컨테이너 git이 멈추고 훅이 안 돎

- **날짜**: 2026-11-09 (round00)
- **증상**: devcontainer 안에서 `git status`가 `fatal: detected dubious ownership in repository at '/workspaces/hybrid-ops-agent'`로 멈춘다. `safe.directory`로 넘겨도 `.git/hooks/pre-commit` 실행이 `not found`(종료 코드 127)로 실패한다.
- **원인**: (1) Windows 호스트의 작업 폴더는 bind mount 안에서 컨테이너 사용자(`vscode`)와 소유자가 달라, git의 소유자 검사가 저장소를 거부한다. (2) `.git/hooks`는 추적되지 않는 파일이라 `.gitattributes`가 적용되지 않는데, 호스트(Windows)의 pre-commit이 훅 스크립트를 CRLF로 쓴다. 첫 줄 `#!/bin/sh\r`의 `\r` 때문에 Linux가 인터프리터를 찾지 못한다(Git Bash는 이를 견딘다).
- **해결**: `postCreateCommand` 맨 앞에서 `sudo git config --system --replace-all safe.directory ${containerWorkspaceFolder}`로 작업 폴더를 등록한다(시스템 설정이라 VS Code가 복사해 넣는 `~/.gitconfig`에 덮이지 않는다). 커밋은 호스트에서 한다 — 컨테이너에서 `pre-commit install`로 훅을 다시 쓰면 이번엔 호스트 커밋이 깨진다(훅이 컨테이너 Python 경로를 가리킨다).
- **재발 방지**: 컨테이너는 도구(uv·kubectl·helm·terraform·az)와 테스트·`pre-commit run`용으로 쓰고, `git commit`은 호스트에서 한다(`GIT_WORKFLOW.md` §개발 환경). 컨테이너의 venv는 `UV_PROJECT_ENVIRONMENT`로 작업 폴더 밖에 둬서 호스트 `.venv`를 건드리지 않는다.
