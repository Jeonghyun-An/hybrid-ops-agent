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
