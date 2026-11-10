# round00 완료노트

날짜: 2026-11-10
브랜치: `feat/round00-scaffold`
spec: `docs/superpowers/specs/2026-11-09-hybrid-ops-agent-design.md`
plan: `docs/superpowers/plans/2026-11-09-round00-scaffold.md`
교본: `docs/guides/round00/00-개요.md`

## 한 일
- 줄 끝·무시 목록: `.gitattributes`(LF 고정, `.ps1`만 CRLF), `.gitignore`(비밀값·kubeconfig·Terraform state·캐시).
- uv 워크스페이스: 가상 루트(uv `>=0.11.31,<0.12` 요구) + 첫 멤버 `agent`(`hoa-agent`), `hoa` CLI(`--version`·도움말)와 테스트 2개(TDD).
- pre-commit: 기본 위생 6개 + ruff(check·format) + gitleaks.
- GitHub Actions CI: `린트·테스트`(`uv sync --locked`·ruff·pytest)와 `비밀값 검사(gitleaks, 전체 이력)`, 권한은 `contents: read`.
- devcontainer: `mcr.microsoft.com/devcontainers/python:3-3.12-bookworm` + docker-outside-of-docker·kubectl·helm·terraform·az, 작업 폴더 밖 venv, 기능 잠금 파일(`devcontainer-lock.json`). 실제 기동까지 확인.
- 운영 문서: `CLAUDE.md`, `GIT_WORKFLOW.md`(브랜치·커밋·머지 승인·품질 게이트·개발 환경·라운드 생애주기 8단계), 코딩 표준, 반복 함정 3건, `README.md`, `00_status.md`.
- 라운드 도구: 완료노트·교본 템플릿, code-reviewer 에이전트, round-finish 스킬.
- 교본: `docs/guides/round00/00-개요.md` — 개념 입문 12절 + 파일 20개 전체 수록 + 검증 + 면접식 Q&A 9문항.

## 결정
- uv 워크스페이스 멤버 분리 — 컴포넌트마다 이미지가 따로 나가므로 의존성을 멤버별로 나누고, 버전은 `uv.lock` 하나로 묶는다.
- 품질 게이트는 대상 파일이 생기는 라운드에 도입 — round00은 ruff·pytest·gitleaks만, helm lint·kubeconform은 round02, terraform 검사는 round03.
- gitleaks 이중화 — pre-commit(스테이징된 변경) + CI(전체 이력). public 저장소라 한 번 push된 비밀값은 키 폐기만이 해결이다.
- `.gitattributes`로 LF 고정 — Windows 개발 PC(`core.autocrlf=true`)와 Linux 실행 환경 사이의 CRLF 문제를 저장소 규칙으로 막는다.
- 실측으로 바꾼 것: `astral-sh/setup-uv@v10.3.3`(v8부터 메이저 태그 없음), devcontainer 이미지 `3-` 태그(만료된 Yarn 키, 함정 2번), uv는 `pipx`로 설치, 컨테이너 venv는 `UV_PROJECT_ENVIRONMENT`로 작업 폴더 밖, `safe.directory`는 `--system`, 커밋은 호스트에서(CRLF 훅, 함정 3번).
- uv 버전을 `[tool.uv] required-version = ">=0.11.31,<0.12"`로 묶었다(리뷰 지적) — CI의 setup-uv가 이 값을 읽어 0.11.33을 설치한 것을 로그로 확인했다.
- 교본에 「개념 입문」 절을 더했다 — 학습 프로젝트라 처음 보는 분야도 익힐 수 있게 하라는 사용자 요청(2026-11-10). 템플릿 절 번호가 한 칸씩 밀렸다(구현 3, 검증 4, Q&A 5).
- push는 2026-11-10 사용자가 `git push` 권한을 허용해 Claude가 했다. 이 규칙을 문서(`CLAUDE.md`·`GIT_WORKFLOW.md`)에 적는 것은 사용자 확인 뒤로 미뤘다(「이월」).
- Task 16 리뷰에서 고치지 않은 low와 이유:
  - CI 액션 커밋 SHA 고정·gitleaks 바이너리 체크섬 — Azure 자격 증명이 워크플로에 들어오는 round03 전에 Dependabot과 함께 한다.
  - devcontainer 안 kubectl·helm·terraform·az 버전 고정 — 그 도구를 실제로 쓰는 라운드(round01~03)에 고정한다.
  - code-reviewer 보안 점검에 쓰기 감사 로그·토큰 상한 — 그 기능이 들어오는 라운드(round06·round07)에 더한다.
  - `.gitignore`의 `k3s.yaml`이 저장소 어디서나 걸림 — round02에서 그 이름의 매니페스트를 피하거나 패턴을 좁힌다.
- 고치지 않은 medium 1건: `CLAUDE.md`에 머지 커밋 형식 예외가 없다(「충돌 시 이 파일이 우선」이라 `GIT_WORKFLOW.md`의 예외와 부딪힌다). `CLAUDE.md` 수정은 사용자 허락 대기라 반영하지 않았다(「이월」). 같은 이유로 `CLAUDE.md` 쪽 low 2건(반복 함정의 표현과 읽을 시점, round 정의 축약)도 미뤘다.

## 수치
(평가 러너·RAGAS·지연·비용처럼 이 라운드에서 잰 값. 잰 것이 없으면 "없음". 사람 검증 없이 LLM 채점만 거친 수치는 그렇다고 적는다.)
- 없음 — round00은 평가 대상 기능이 없다. 테스트 2개, CI 두 잡.

## Azure 비용
(이 라운드에서 만들거나 켠 Azure 리소스와 끈 시각. 쓰지 않았으면 "사용 안 함".)
- 사용 안 함.

## 이월
- `CLAUDE.md`·`GIT_WORKFLOW.md` 수정(사용자 허락 대기): 계획서를 문서로 먼저 보여 준다, 작업 브랜치·`dev` push는 Claude가 승인 없이 한다(`main`은 라운드 종료 승인 뒤), 머지 커밋 형식 예외, 반복 함정을 읽을 시점에 개발 환경 작업 추가, round 정의에 검증·문서 단계와 산출물 plan 포함, §5 교본 설명에 개념 입문 추가.
- 교본 대조 스크립트(교본 코드블록을 뽑아 실제 파일과 diff)를 `scripts/`의 재사용 도구로 둘지 — round01 교본 때 정한다.
- round01: devcontainer 안에서 kind kubeconfig(`127.0.0.1`)가 닿지 않는 문제, Azure OpenAI 대량 호출 비용 승인 규칙, 멤버별 이미지는 `uv sync --locked --package <멤버> --no-dev`로 빌드, devcontainer의 kubectl 버전 고정.
- round02: Helm `templates/`를 check-yaml에서 제외, `k3s.yaml` 무시 패턴, SOPS 암호화 파일 예외 규칙, 접미 라운드(`round02a`…) 완료노트 파일명 규칙, devcontainer의 helm 버전 고정.
- round03: CI 액션 SHA 고정 + Dependabot + gitleaks 체크섬, devcontainer의 terraform·az 버전 고정.
- round06·round07: code-reviewer 보안 점검에 쓰기 감사 로그·토큰 상한을 더한다.

## 다음 라운드 진입점
- round01 — 끝-끝 경로. 착수 전 Azure 구독과 Azure OpenAI 배포 모델·리전 결정(spec §10), 개발 PC에 kind 설치.

## 상태
- [ ] code-reviewer 정적 리뷰 통과(high·medium 수정, low는 수정하거나 「결정」에 이유) — `CLAUDE.md` 쪽 medium 1건이 사용자 허락 대기(「결정」)
- [ ] CI green(작업 브랜치 마지막 커밋) — 이 노트를 push한 뒤 확인해 `dev` 머지 때 체크
- [x] 수동 스모크 확인
- [x] 문서 갱신(교본·00_status·실제로 돌려 보며 새로 겪은 함정(개발 환경 포함)을 `docs/ops/recurring-gotchas.md`에 추가)
- [x] Azure 리소스 정지 확인(AKS를 켠 라운드만 — `az aks show -g <그룹> -n <클러스터> --query powerState.code -o tsv`가 `Stopped`. 켜지 않은 라운드는 「해당 없음」을 덧붙이고 체크) — 해당 없음
- [ ] `dev` 머지 승인
- [ ] `dev→main` 머지 + push 완료
