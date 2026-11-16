# Git Workflow

> 이 프로젝트(hybrid-ops-agent)의 브랜치·커밋·머지 규칙과 품질 게이트·개발 환경. 모든 작업은 이 문서를 따른다.

## 브랜치 모델

| 브랜치 | 역할 | 규칙 |
|---|---|---|
| `main` | 배포 기준 — round02부터 Argo CD가 이 브랜치를 클러스터에 동기화한다 | 평소 직접 작업 금지. 라운드 종료 시 사용자 승인 하에 `dev → main` 머지 후 `origin` push. |
| `dev` | 통합 브랜치 | 완성된 작업 브랜치가 모이는 곳. 클러스터에 배포하지 않고 CI로만 검증한다. 직접 커밋은 완료노트 「상태」 체크만 한다(§라운드 생애주기 7·8). |
| `<type>/round<NN>-<설명>` | 작업 브랜치 | `dev`에서 분기. 한 작업 단위 = 한 브랜치. |

- 타입(Conventional): `feat`·`fix`·`docs`·`chore`·`refactor`·`test`
- 설명은 영문 kebab-case(예: `feat/round01a-kind-mcp-read`) — 한글 브랜치명은 Windows·CI 호환성 문제로 쓰지 않는다.
- 접미 라운드: 한 라운드가 성격이 다른 여러 덩어리로 쪼개지면 소문자 접미를 붙인다(`round02a`, `round02b`…). 접미는 성격 라벨이며 실행 순서가 아니다. 접미 라운드도 각각 한 라운드로 센다 — spec·plan·완료노트·교본을 따로 두고, 파일·폴더·브랜치 이름과 머지 커밋에 접미를 그대로 쓴다(`round01a-완료노트.md`, `docs/guides/round01a/`, `feat/round01a-…`, `— round01a (…)`).

## 흐름

```
dev ─분기→ <type>/round<NN>-<설명> ─개발·커밋·push(CI)─→ 리뷰 ─[사용자 승인]→ merge→ dev ─[라운드 종료 승인]→ main ─push→ origin (round02부터 = 배포)
```

1. `dev`에서 작업 브랜치 분기
2. 개발 → 커밋 → 원격 push. 솔로 작업이라도 작업 브랜치를 push한다 — CI는 push에서 돈다. 일반 push는 따로 승인받지 않는다(§머지 승인 규칙).
3. 완성되면 리뷰(서브에이전트 정적 리뷰 + 자가 점검) → 사용자 승인을 받은 뒤 `dev`로 `--no-ff` 머지 (승인 전 머지 금지)
4. `dev` push
5. 라운드 종료(사용자 승인): `dev → main` 머지 + `origin` push

## 머지 승인 규칙

- 작업 브랜치 → `dev`: 매번 사용자 채팅 승인 필수. 리뷰 게이트는 (1) `.claude/agents/code-reviewer.md` 서브에이전트의 정적 리뷰와 (2) 자가 점검 체크리스트(CI green + 관련 기능 수동 스모크 + 문서 갱신 여부)를 순서대로 통과하는 것이다.
- 리뷰 발견 처리: high·medium은 모두 고친다. low는 고치거나, 고치지 않는 이유를 완료노트 「결정」에 한 줄로 적는다. 고친 뒤에는 CI를 다시 확인한다.
- `dev` → `main`: 라운드 종료 판단·승인은 사용자. round02부터는 `main` push가 곧 배포다.
- push: 작업 브랜치와 `dev`의 일반 push는 Claude가 따로 묻지 않고 한다. 강제 push와 원격 브랜치 삭제는 묻는다. `main` push는 위 라운드 종료 승인 없이는 하지 않는다. 라운드 흐름에서 사용자가 확인하는 지점은 spec·계획서(§라운드 생애주기 1·2)와 위 두 머지다 — 비용이 나는 클라우드 작업과 회사 서버의 기존 시스템·서버 설정을 바꾸는 작업의 승인(`CLAUDE.md` §4)은 별도다.

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
| shellcheck | pre-commit + CI(pre-commit으로 같은 버전) | round01a |
| 통합 테스트(`pytest -m integration`, kind 클러스터) | CI | round01a |
| helm lint · kubeconform | CI | round02 |
| terraform fmt -check · terraform validate | pre-commit + CI | round03 |

- 검사는 그 파일 종류가 처음 생기는 라운드에 더한다 — 대상 없는 검사는 아무것도 증명하지 못한다.
- `terraform apply`는 CI에서 돌리지 않는다. 로컬에서 사용자 승인 뒤 손으로만 한다.
- 클론한 뒤 한 번(호스트에서): `uv run pre-commit install`. devcontainer 안에서는 하지 않는다(§개발 환경).
- 두 곳에 적힌 도구 버전은 같이 올린다: ruff는 `pyproject.toml` dev 그룹과 `.pre-commit-config.yaml` rev, gitleaks는 `.pre-commit-config.yaml` rev와 `.github/workflows/ci.yml` 다운로드 URL. uv는 `pyproject.toml`의 `[tool.uv] required-version`이 정본이다 — CI(setup-uv)는 이 값을 읽고, devcontainer `postCreateCommand`의 `pipx install` 버전 범위는 손으로 맞춘다. kind는 `.github/workflows/ci.yml`의 다운로드 버전, `scripts/dev-cluster.sh`의 `KIND_VERSION`과 `NODE_IMAGE`(그 kind 릴리스 노트의 다이제스트), 이 문서·`README.md`의 kind 버전을, kubectl은 `ci.yml`의 다운로드 버전과 `.devcontainer/devcontainer.json`의 kubectl 버전을 같이 올린다(kind 노드 이미지와 같은 마이너).

## 개발 환경

| 환경 | 용도 | 들어오는 라운드 |
|---|---|---|
| 개발 PC: uv + Docker Desktop | 코드·단위 테스트 | round00 |
| devcontainer (`.devcontainer/`) | 개발 PC가 바뀌어도 같은 도구 세트(uv·kubectl·helm·terraform — gcloud는 round03) | round00 |
| 개발 PC: kind (로컬 티어) | GPU 없이 도는 개발 클러스터, 데모 앱·MCP 통합 테스트 | round01a |
| 회사 GPU 서버: k3s + GPU Operator (GPU 티어) | 상시 클러스터(모델·데이터·관측·Argo CD) | round02 |
| GCP GKE | 작업할 때만 노드를 켜는 클라우드 클러스터 | round03 |

- Python: `uv sync` → `uv run pytest`. Python 버전은 `.python-version`(3.12)에 맞춰 uv가 준비한다.
- GitHub CLI(`gh`)는 호스트에 설치하고 `gh auth login`한다 — CI 결과 확인과 `/round-finish`가 쓴다.
- devcontainer는 작업 폴더와 `.git`을 호스트와 공유한다. 그래서 컨테이너의 venv는 작업 폴더 밖(`/home/vscode/.venv`, `UV_PROJECT_ENVIRONMENT`)에 두고, `pre-commit install`은 호스트에서만 한다 — 컨테이너에서 하면 공유된 훅이 컨테이너 Python을 가리켜 호스트 커밋이 깨진다. Windows 호스트에서는 커밋도 호스트에서 한다 — 호스트에서 설치한 훅 스크립트가 CRLF라 컨테이너에서 실행되지 않는다(`docs/ops/recurring-gotchas.md` 3번).
- kind(로컬 티어, round01a): Docker Desktop, kind v0.33.0, kubectl(노드 v1.37과 ±1 마이너 — Docker Desktop에 들어 있다)을 호스트에 둔다. 처음 `up`하면 사용자 kubeconfig의 current-context가 `kind-hoa`로 바뀐다(스크립트와 테스트는 컨텍스트를 명시해서 쓴다). `bash scripts/dev-cluster.sh up`이 클러스터 `hoa`를 만들고 데모 앱을 빌드·적재·배포한 뒤 MCP 서버용 읽기 전용 kubeconfig(`~/.kube/hoa-kind-mcp-read.kubeconfig`, 토큰 12시간)를 쓴다. 그 밖의 명령은 `down`·`fault <image-pull|bad-config>`·`reset`·`mcp-kubeconfig`이고, 통합 테스트는 `uv run pytest -m integration`이다. kind와 통합 테스트는 호스트에서 돌린다 — devcontainer 안에서는 kind API 주소(`127.0.0.1`)에 닿지 않는다. Windows에서는 Git Bash로 실행한다.
- LLM(round01b): 기본 모델은 회사 GPU의 Gemma(vLLM)이고, Gemini(개인 Google 계정의 AI Studio 키 — 결제를 연결하지 않은 무료 등급)는 회사망 밖에서의 대체이자 평가의 비교 기준이다. 루트의 `.env`(커밋하지 않는다)에 `.env.example`의 변수를 채우고 `uv run --env-file .env <명령>`으로 넘긴다. 손으로 조사 한 번: `uv run --env-file .env hoa investigate "<경보 문장>"`(Gemini는 `--model gemini`). 평가: `uv run --env-file .env hoa-eval run --repeat 3` → 결과는 `eval/results/<시각>-<모델>.jsonl`(커밋하지 않는다), 표는 `uv run hoa-eval report eval/results/*.jsonl`. 둘 다 kind 클러스터와 MCP용 kubeconfig(`dev-cluster.sh up`·`mcp-kubeconfig`)가 있어야 한다. Gemini 무료 등급은 모델마다 하루 요청 수 한도가 있어 한도에 걸리면 `hoa-eval`이 남은 회차를 멈춘다(종료 코드 3 — 에이전트 설정 오류면 2로 멈춘다) — 한도가 풀린 뒤 남은 시나리오만 `--scenario`로 다시 돌리고 `report`로 합친다.
- 각 환경의 세부 절차(설치·접속·기동/정지)는 그 환경이 들어오는 라운드에 이 절에 더한다.

## 개발 가이드 문서 (필수)

- 1 라운드 = 1 교본(가이드). `docs/guides/round<NN>/`에 저장(템플릿: `docs/guides/_TEMPLATE.md`).
- 구성: paraphrase된 라운드 프롬프트 → 설계 요약 → 개념 입문(이 라운드에 처음 나온 개념을 기초부터) → 전 코드/문서 클론코딩 가능하게 수록(발췌·플레이스홀더 금지) → 검증 → 면접식 Q&A.
- 리뷰 흐름: 작업 브랜치 push → 교본↔실제 파일 대조(`uv run python scripts/check_guide.py docs/guides/round<NN>/`가 교본의 「**파일**:」 코드블록을 실제 파일과 diff한다 — 제목 수만 세지 않는다. 그다음 `.claude/agents/code-reviewer.md`로 한 번 더 본다. 리뷰어는 git을 실행하지 않으므로 대조할 파일 목록은 호출하는 쪽이 넘긴다) → 승인 → `dev` 머지.

## 라운드 생애주기

1. 프롬프트→spec: `docs/superpowers/specs/`에 브레인스토밍 설계 작성(브레인스토밍 스킬) → 사용자 확인 뒤 계획으로 넘어간다.
2. 계획: `docs/superpowers/plans/`에 구현 계획 작성(writing-plans 스킬) → 계획서 파일 자체를 사용자에게 보내(채팅 요약으로 대신하지 않는다) 확인받은 뒤 구현한다.
3. 구현: TDD(`docs/standards/coding-standard.md`).
4. 리뷰: `.claude/agents/code-reviewer.md` 서브에이전트로 정적 리뷰 → 발견 처리(§머지 승인 규칙).
5. 검증: CI green + 관련 기능 수동 스모크(round01b부터 평가 러너 시나리오 포함).
6. 문서: 작업 브랜치에서 교본(`docs/guides/round<NN>/`)·완료노트(`docs/roadmap/round<NN>-완료노트.md`, 템플릿 `docs/roadmap/_ROUND_COMPLETE_TEMPLATE.md`)를 쓰고 `docs/roadmap/00_status.md`를 갱신 → 교본 대조 리뷰(§개발 가이드 문서).
7. 머지: 사용자 승인 → 작업 브랜치를 `dev`에 `--no-ff` 머지·push → `dev`에서 완료노트 「상태」의 `dev` 머지 승인 줄을 체크·커밋·push(`dev` CI).
8. 라운드 종료: 사용자 승인 → `/round-finish` 스킬로 `dev→main` 머지 + `origin` push → `dev`에서 완료노트 마지막 줄을 체크·커밋해 `dev`에만 push(다음 라운드 머지 때 `main`에 함께 올라간다).

## 비고

- 비밀정보·kubeconfig·Terraform state는 커밋하지 않는다(`.gitignore`). public 저장소다 — 한 번 push된 비밀값은 이력에서 지워도 이미 노출된 것으로 보고 키를 폐기한다.
- 실행해서 파일을 만들어내는 1회성 스크립트는 대응하는 `research/<주제>/`에 산출물과 함께 둔다(`CLAUDE.md` §2).
