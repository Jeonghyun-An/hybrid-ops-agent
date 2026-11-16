# round01a 완료노트

날짜: 2026-11-16
브랜치: `feat/round01a-kind-mcp-read`
spec: `docs/superpowers/specs/2026-11-11-round01a-kind-mcp-read-design.md`
plan: `docs/superpowers/plans/2026-11-11-round01a-kind-mcp-read.md`
교본: `docs/guides/round01a/00-개요.md`

## 한 일
- 워크스페이스 멤버 둘: `demo_app`(`hoa-demo` — FastAPI 3서비스 gateway → orders → inventory, 메모리 데이터, 이미지 하나에 역할은 환경변수)과 `mcp_servers`(`hoa-mcp` — FastMCP stdio 서버 `hoa-mcp-k8s-read`).
- 데모 앱 이미지: 멤버 의존성만 설치(`uv sync --locked --package hoa-demo --no-dev`), 빌드·실행 단계 분리, 비루트 사용자·그룹 65532, 읽기 전용 루트 파일시스템.
- kind 개발 클러스터(로컬 티어): `scripts/dev-cluster.sh`(up·down·fault·reset·mcp-kubeconfig)와 `deploy/kind/`(restricted 파드 보안 표준을 강제한 데모 매니페스트, `demo`에만 묶인 읽기 전용 RBAC, 장애 패치 2종).
- MCP `k8s-read` 도구 4개(`list_pods`·`get_events`·`describe_deployment`·`get_pod_logs`) — Pydantic 구조화 출력, 응답당 12,000자 상한(넘으면 목록을 자르고 `truncated`, 줄어들지 않으면 도구 오류), 비밀값 가리기(이름·값), 허용 네임스페이스와 이름 검증, 예상 밖 예외는 서버 로그에만 원문, 읽기 전용 표시.
- 테스트: 단위 105개(demo_app 28·mcp_servers 70·교본 대조 스크립트 7, agent 2는 기존), kind 통합 6개(`integration` 마커, 기본 실행 제외). CI에 shellcheck 단계와 「통합 테스트(kind)」 잡(스크립트 `fault`·`reset` 단계, 실패·취소 시 kind 로그 아티팩트). ruff `ANN`(타입힌트)과 pytest 경고-오류·`--strict-markers`를 켰다.
- 교본 대조 스크립트 `scripts/check_guide.py`(round00 이월).
- 문서 전환: `CLAUDE.md`(사용자 승인 — §0, §2 회사 자원 경계, §3 접미 라운드, §4 클라우드 비용·회사 서버 승인), `GIT_WORKFLOW.md`, 전체 설계, `README.md`, 코딩 표준, code-reviewer, 완료노트 템플릿, round-finish, 반복 함정(4·5·6번 추가), devcontainer(az 제거, kubectl 1.37.0 고정).
- 교본: `docs/guides/round01a/` — 개념 입문 13절, 정적 리뷰로 바뀐 것, 파일 58개 전체 수록(네 파일로 나눔), 검증, 면접식 Q&A 15문항.

## 결정
- 클라우드 Azure → GCP(2026-11-10), 온프레미스 집 PC → 회사 GPU 서버와 두 실행 티어(2026-11-11) — spec §3.
- round01을 01a(LLM 없는 클러스터·도구)와 01b(에이전트·LLM·평가)로 나눴다 — 01a는 Gemini 키 없이 끝까지 검증된다.
- MCP 서버는 호스트 stdio + 읽기 전용 ServiceAccount 토큰(spec §5.4 안 A). 클러스터 안 배치(안 B)는 Helm이 들어오는 round02.
- MCP SDK는 1.x로 고정 — 2.x(MCPServer)는 `langchain-mcp-adapters`가 아직 지원하지 않는다(반복 함정 5번). 어댑터를 빼고 직접 짜는 안도 검토했지만, round01b에서 LangChain 생태계를 겪어 보려고 어댑터를 쓰기로 했다(사용자 결정 2026-11-16). 어댑터가 안에서 하는 일은 교본 Q11에서 풀었다.
- 도구 출력 상한은 가장 작은 문맥(GPU 티어 32K)에 맞춘 응답당 12,000자.
- RBAC는 도구가 읽는 리소스와 동사만 — Service·EndpointSlice는 그것을 읽는 도구가 들어올 때 더한다.
- Postgres는 DB 장애 시나리오가 들어오는 라운드로, kubeconform은 Helm과 함께 round02로 미뤘다 — 이번 매니페스트는 CI가 실제 kind(restricted 파드 보안 표준 포함)에 적용해 검증한다.
- devcontainer 안 kind는 미뤘다 — kind와 통합 테스트는 호스트에서 돌린다.
- 장애 이름 → 대상 Deployment 대응이 `scripts/dev-cluster.sh`와 통합 테스트 두 곳에 있다 — 테스트가 Windows에서 `bash`(WSL로 풀릴 수 있다)를 부르지 않게 하려는 것. CI는 스크립트의 `fault`·`reset`도 따로 돌린다. round01b의 시나리오 YAML이 들어오면 한 곳으로 모은다.
- FastAPI는 plan에 적은 0.162가 아니라 잠글 때 나온 0.163.1로 잠겼다 — 테스트가 그 버전에서 통과했다. 의존성은 하한만 두고 버전은 `uv.lock`이 고정한다.
- devcontainer 잠금 파일을 다시 만들면서 남은 기능 셋의 패치 버전도 올라갔다(docker-outside-of-docker 1.10.2, kubectl-helm-minikube 1.3.2, terraform 1.5.1). 실제 기동과 컨테이너 안 테스트(50 passed 당시)를 확인했다.
- 정적 리뷰(영역 넷 — 데모 앱·MCP 서버·클러스터와 CI·문서): high 없음, medium 17건 모두 수정(오탐 1건 제외). 고치지 않은 것과 이유:
  - Codex 로컬 파일(`AGENTS.md`·`.codex/`)이 `git add -A`로 커밋될 수 있다는 지적(medium) — 오탐. round00에 `.git/info/exclude`로 이미 무시하고 있다(`git check-ignore`로 확인).
  - 베이스 이미지 다이제스트 고정, 빌드 백엔드(hatchling) 잠금(low) — 공급망 고정을 몰아서 하는 round03(액션 SHA·Dependabot·체크섬)과 함께 한다.
  - `fit`이 한 개씩 빼며 다시 직렬화해 O(n²)이다(low) — 목록이 수백 개 이하라 실측 영향이 없다. 커지면 누적 크기로 바꾼다.
  - 대기·종료 사유에 컨테이너 이름이 없다(low) — 데모는 컨테이너 하나다. 사이드카가 들어오는 라운드에 더한다.
  - `docker context`·`DOCKER_HOST`를 확인하지 않는다, 호스트 kubectl 버전을 스크립트가 확인하지 않는다(low) — 개발 PC는 Docker Desktop 하나다. 준비물(kubectl ±1 마이너)은 `GIT_WORKFLOW.md`·`README.md`에 적었다.
  - 야간 GKE 축소 잡의 CI 쓰기 권한과 code-reviewer 점검의 충돌(low) — 그 잡이 생기는 round03에 code-reviewer 예외를 함께 적는다.
  - `CLAUDE.md` 두 곳(§3 승인 범위 요약에 「서버 설정」을 넣기, §2 `deploy/`에 kind 매니페스트를 넣기)(low) — `CLAUDE.md` 문구는 사용자 승인이 필요해 「이월」로 넘긴다.
  - 리뷰어가 세션을 시작할 때 읽은 옛 code-reviewer 정의로 떴다(영역 D 보고) — 새 점검 세 가지(회사 정보 노출, 도구 출력 비밀값, kubectl 컨텍스트)는 프롬프트로 직접 넘겼다. 다음 라운드는 새 세션에서 띄운다.

## 수치
(평가 러너·RAGAS·지연·비용처럼 이 라운드에서 잰 값. 잰 것이 없으면 "없음". 사람 검증 없이 LLM 채점만 거친 수치는 그렇다고 적는다.)
- 평가 수치는 없음 — LLM을 부르지 않는 라운드다.
- 테스트: 단위 107개(agent 2 포함), 통합 6개(개발 PC 21초), CI 세 잡(통합 테스트 잡 약 1분 30초).

## 클라우드 비용
(이 라운드에서 만들거나 켠 GCP 리소스와 Gemini 유료 사용, 켠 것과 끈 시각. 쓰지 않았으면 "사용 안 함".)
- 사용 안 함.

## 이월
- round01b: LangGraph 단일 에이전트(LangChain `ChatOpenAI` + `langchain-mcp-adapters`), `llm.py`로 LLM 두 종(Gemini 무료 등급·회사 GPU의 Gemma), 평가 러너 v0(시나리오 YAML의 주입은 `deploy/kind/faults/`를 가리킨다), 조사 1건의 문맥·토큰 예산(설계서 §10). 착수 전 사용자 준비: Gemini API 키(개인 Google 계정, `.env`), 회사 GPU vLLM의 도구 호출 옵션.
- `CLAUDE.md` 보완 두 곳(사용자 승인 필요): §3 확인 지점의 승인 범위 요약을 「회사 서버의 기존 시스템·서버 설정을 바꾸는 작업」으로(`GIT_WORKFLOW.md`도 같이), §2의 `deploy/` 설명에 kind 매니페스트를 더하기.
- round02: Helm `templates/`를 check-yaml에서 제외, `k3s.yaml` 무시 패턴, SOPS 암호화 파일 예외 규칙, devcontainer의 helm 버전 고정(round00 이월). 데모 앱 매니페스트를 Helm 차트로(로컬 티어는 같은 차트를 로컬 값으로), MCP 서버 클러스터 안 배치, kubeconform, 기존 Gemma 인스턴스를 k3s 관리로, 임베딩 모델, k3s 대역과 사내 대역 확인.
- round03: CI 액션 SHA 고정 + Dependabot + gitleaks·kind·kubectl 체크섬, 베이스 이미지 다이제스트·빌드 백엔드 잠금, devcontainer에 gcloud와 terraform 버전 고정. 착수 전에 GKE↔회사 GPU 서버 연결과 온프레미스 Argo CD의 GKE 등록 방식을 확인(설계서 §10).
- round06·round07: code-reviewer 보안 점검에 쓰기 감사 로그·토큰 상한을 더한다(round00 이월).
- `langchain-mcp-adapters`가 MCP SDK 2.x를 지원하면 서버(FastMCP → MCPServer)와 에이전트를 같은 라운드에 함께 올린다.

## 다음 라운드 진입점
- round01b — spec부터. 착수 전 사용자 준비 두 가지(위 「이월」).

## 상태
- [x] code-reviewer 정적 리뷰 통과(high·medium 수정, low는 수정하거나 「결정」에 이유) — 영역 넷 + 교본, high 없음, medium 모두 수정(오탐 1건). 교본 검토에서 나온 init 컨테이너 종료 사유 결함(medium)도 코드와 테스트로 고쳤다
- [x] CI green(작업 브랜치 마지막 커밋) — `e17cac7`, 실행 43796730523 세 잡 success(리뷰 반영 커밋 `45ffdd5`도 실행 43795316495 success)
- [x] 수동 스모크 확인 — 호출 흐름, 장애 두 가지와 복구, 진행 기한을 넘긴 뒤 `reset`(종료 코드 0), 잘못된 장애 이름(종료 코드 2)
- [x] 문서 갱신(교본·00_status·실제로 돌려 보며 새로 겪은 함정(개발 환경 포함)을 `docs/ops/recurring-gotchas.md`에 추가)
- [x] 클라우드 리소스 정지 확인(GKE 노드를 켠 라운드만 — 확인 명령은 `/round-finish` 5단계. 켜지 않은 라운드는 「해당 없음」을 덧붙이고 체크) — 해당 없음
- [ ] `dev` 머지 승인
- [ ] `dev→main` 머지 + push 완료
