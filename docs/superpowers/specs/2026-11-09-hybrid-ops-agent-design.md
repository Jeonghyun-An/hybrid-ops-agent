# hybrid-ops-agent — 전체 설계 (브레인스토밍 spec)

> 상태: 설계 확정(2026-11-09, 사용자 승인). round00부터 이 문서를 기준으로 라운드별 plan을 쓴다.
> 이 문서는 프로젝트 전체 설계다. 라운드마다 세부 결정은 그 라운드 spec에 쓰고, 여기와 어긋나면 이 문서를 고친다.
> 바뀐 이력: 2026-11-11(round01a) — 클라우드 Azure → GCP, 온프레미스 집 PC → 회사 GPU 서버와 두 실행 티어, round01을 round01a·round01b로 나눔. 근거: `docs/superpowers/specs/2026-11-11-round01a-kind-mcp-read-design.md` §3. 2026-11-16(round01b) — 기본 LLM을 회사 GPU의 Gemma로 바꿈(사용자 결정 — Gemini는 회사망 밖의 대체·평가 비교 기준), Gemini 모델과 조사 예산을 정함(§10), Gemini 3의 도구 호출 서명을 `llm.py`가 되돌려 줌. 근거: `docs/superpowers/specs/2026-11-16-round01b-agent-llm-eval-design.md`.

## 1. 목적

- 온프레미스(회사 GPU 서버)와 클라우드(GCP)를 함께 쓰는 **쿠버네티스 운영 에이전트**를 만든다. 에이전트는 자기가 올라가 있는 하이브리드 클러스터의 장애를 조사·진단하고, 사람 승인을 받아 조치한다.
- 목표는 **이번에 많이 안 해본 기술을 실제로 굴려 보는 것**이다. 서비스 품질보다 각 기술을 "왜 이렇게 썼는가"까지 설명할 수 있게 만드는 것이 우선이다.
- 이전 프로젝트에서 쓰던 **라운드 개발 방식**(spec → plan → TDD → 리뷰 → 승인 머지 → 완료노트·교본)을 그대로 옮겨 쓴다.

### 학습 대상 기술

| 기술 | 이 프로젝트에서의 역할 |
|---|---|
| LangGraph 멀티에이전트 | supervisor + 서브에이전트, 체크포인트(중단·재개), interrupt로 사람 승인 |
| MCP 서버·클라이언트 | 클러스터 조회·조치·관측 도구를 MCP 서버로 직접 만들고, 에이전트가 MCP로 호출 |
| GraphRAG | Neo4j에 클러스터 구조 + 장애 지식 그래프, 벡터 RAG와 진단 정확도 비교 |
| 쿠버네티스 + IaC | 온프레미스 k3s + GCP GKE, Terraform, Helm, Argo CD(GitOps), GitHub Actions |
| 관측·자동 평가 | Prometheus·Loki·Tempo, OpenTelemetry → Langfuse, 장애 시나리오 자동 채점, RAGAS |

## 2. 결정 요약

| 항목 | 결정 | 이유 |
|---|---|---|
| 도메인 | 클러스터 운영 에이전트(장애 진단·조치) | 학습 대상 기술이 전부 자연스럽게 맞물리고, 정답(원인)이 분명해 평가가 쉽다 |
| 온프레미스 | 회사 GPU 서버(H200 1장, 이 프로젝트가 쓸 수 있는 GPU 메모리 약 60GB)에 k3s, 개발 PC는 Docker Desktop + kind | 사용 허락을 받은 서버라 GPU가 크고, 개발 PC와 같은 망이라 터널이 필요 없다(2026-11-11 집 RTX 3060 PC에서 바꿈) |
| 클라우드 | GCP — GKE, Gemini, Secret Manager | 무료 체험($300, 90일)은 자동 과금이 없다. Azure 무료 체험은 Azure OpenAI 할당량이 0이라 바꿨다(2026-11-10) |
| 비용 운영 | GKE 노드는 작업할 때만 켜고 끝나면 0으로 줄인다, 상시 켜둘 것은 온프레미스에. GCP 무료 체험은 GKE가 처음 필요한 round03 직전에 시작한다 | 체험 크레딧 안에서 끝낸다 |
| 클라우드 LLM | Gemini — round01~02는 Google AI Studio 무료 등급 키(결제 미연결), round03부터 Vertex AI. 기본 LLM은 회사 GPU의 Gemma이고 Gemini는 회사망 밖에서의 대체이자 평가의 비교 기준이다(2026-11-16) | 무료 등급으로 시작할 수 있고, OpenAI 호환 엔드포인트가 있어 클라이언트 하나로 부른다 |
| 온프레미스 LLM | 회사 GPU 서버의 vLLM — Gemma 4 26B A4B(MoE, 전체 25.2B·활성 3.8B, 도구 호출 지원, 문맥 32K) + 임베딩 모델(round02) | 기본 LLM(2026-11-16) — 요청 수 제한이 없고 클러스터 데이터가 회사 밖으로 나가지 않는다 |
| 실행 티어 | GPU 티어(회사 GPU 서버의 k3s, 모든 역할의 기본 모델은 온프레미스 Gemma) / 로컬 티어(개발 PC의 kind, GPU 없음 — LLM은 회사망 안이면 GPU 서버의 Gemma, 밖이면 Gemini 무료 등급) — 티어는 클러스터와 역할별 모델 설정의 기본값 묶음이고, 같은 코드·같은 차트에 설정만 다르다 | 회사 GPU를 못 쓰게 돼도 로컬 티어로 계속 개발하고, CI와 저장소를 클론한 사람은 로컬 티어로 돌린다 |
| 진행 순서 | 얇은 끝-끝 경로 먼저(round01a·01b), 이후 라운드마다 두께를 늘림 | 라운드마다 시연할 결과가 나오고 평가 기준이 일찍 생긴다 |
| 교본 | 이전 프로젝트와 같이 전체 코드 수록 + 면접 Q&A, 그리고 처음 나온 개념을 기초부터 정리하는 「개념 입문」(2026-11-10 추가) | 사용자 선택 — 학습 프로젝트라 모르던 분야도 익힌다 |
| 저장소 | https://github.com/Jeonghyun-An/hybrid-ops-agent (개인 계정, public) | 포트폴리오. 비밀값 커밋은 gitleaks로 막는다 |

## 3. 전체 배치

| 위치 | 켜짐 | 올라가는 것 |
|---|---|---|
| 회사 GPU 서버 (k3s + NVIDIA GPU Operator) — GPU 티어 | 상시 | vLLM(Gemma·임베딩), Neo4j(위치는 round05에서 확정), Postgres(LangGraph 체크포인트), Prometheus·Alertmanager·Grafana·Loki·Tempo, Argo CD, 데모 앱, 에이전트·MCP 서버 |
| GKE (Terraform으로 생성) | 작업할 때만 | 에이전트 API·MCP 서버·웹 UI(상태 없는 것만), 데모 앱 사본 |
| GCP 관리형 | 사용량 과금(체험 크레딧) | Gemini(Vertex AI), Secret Manager, 예산 알림 |
| Langfuse Cloud(무료 등급) | 상시(SaaS) | 에이전트 트레이스·평가 데이터셋 |
| 개발 PC (Docker Desktop + kind) — 로컬 티어 | 개발할 때 | 데모 앱·MCP 서버·에이전트(LLM은 회사망 안이면 Gemma, 밖이면 Gemini 무료 등급), 통합 테스트 |

배치 원칙:

1. **상태가 있는 것(DB·모델·관측)은 상시 켜진 온프레미스에 둔다.** GKE 노드를 꺼도 데이터가 남는다.
2. **상태 없는 앱은 Helm 차트 하나로 두 클러스터에 같이 배포한다.** Argo CD(온프레미스에서 실행) ApplicationSet이 k3s와 GKE 양쪽을 대상으로 잡는다. GKE 노드가 꺼져 있으면 온프레미스 쪽 에이전트가 응답한다.
3. **클러스터 간 연결은 round03 착수 전에 정한다.** 기본안은 Tailscale 쿠버네티스 오퍼레이터로 회사 GPU 서버의 vLLM·Neo4j·Postgres를 GKE에서 사설 주소로 부르는 것이다. 회사 서버에 Tailscale을 둘 수 있는지는 회사 망 정책을 확인해 정하고(§10), 묶지 못하면 GKE 쪽 에이전트는 Gemini만 쓰고 독립으로 돈다. 어느 쪽이든 인바운드 포트는 열지 않는다.
4. **비밀값**: GKE는 Workload Identity Federation으로 키 없이 Gemini(Vertex AI)·Secret Manager에 접근한다. 온프레미스는 SOPS(age)로 암호화한 시크릿을 git에 둔다. 로컬 티어의 Gemini 키는 커밋하지 않는 `.env`에 둔다.
5. **Langfuse는 Cloud 무료 등급부터 쓴다.** 셀프호스팅 v3는 ClickHouse까지 필요해 회사 GPU 서버에 다른 시스템과 같이 올리기 무겁다. 계측은 OpenTelemetry로 해 두어 백엔드를 바꿀 수 있게 한다.

**실행 티어**: GPU 티어(회사 GPU 서버의 k3s, 온프레미스 LLM은 vLLM의 Gemma — 32K 문맥)와 로컬 티어(개발 PC의 kind, GPU 없음, LLM은 회사망 안이면 GPU 서버의 Gemma, 밖이면 Gemini 무료 등급)는 같은 코드와 같은 Helm 차트를 쓰고 설정만 다르다. 「로컬」은 이 티어 이름에만 쓰고, 회사 GPU의 모델은 「온프레미스 LLM(Gemma)」이라 부른다. CI는 회사망에 닿지 않으므로 항상 로컬 티어(가짜 LLM)로 돈다. 도구 출력 크기와 문맥 예산은 가장 작은 문맥(32K)에 맞춘다.

**회사 자원 경계**: 회사 GPU 서버는 연산 자원으로만 쓴다. 그 위에는 이 저장소의 코드, 공개 가중치 모델, 데모 데이터, 직접 쓴 문서와 공개 문서만 올린다. 회사 저장소의 코드·회사 데이터·회사가 학습시킨 모델은 쓰지 않고, 서버 주소·호스트명·계정·사내 네트워크 정보는 커밋하지 않는다(`CLAUDE.md` §2).

### 진단 대상 — 데모 앱

직접 만드는 작은 3-서비스 앱: `gateway → orders → inventory`(데이터는 메모리, Postgres는 DB 장애 시나리오가 들어오는 라운드에 더한다). 각 서비스는 OpenTelemetry로 계측한다(Tempo 서비스 그래프가 GraphRAG 구조 층의 의존 관계 재료가 된다).

장애는 쿠버네티스 단골부터 심는다: 이미지 태그 오류(ImagePullBackOff), 메모리 한도 초과(OOMKilled), 잘못된 환경변수(CrashLoopBackOff), Service 셀렉터 불일치(엔드포인트 없음), 하류 서비스 지연. round07에서 Chaos Mesh로 넓힌다.

## 4. 에이전트 구조 — LangGraph + MCP

```
경보(Alertmanager 웹훅)·사용자 질문
  → triage            [온프레미스 Gemma]  경보 분류, 대상 클러스터·네임스페이스·심각도
  → supervisor        [온프레미스 Gemma]  조사 계획, 서브에이전트 배정
      ├─ k8s 조사관    MCP k8s-read   pod·events·describe·logs
      ├─ 지표 분석관   MCP observability  PromQL, Loki 로그 검색
      └─ 지식 담당     GraphRAG       의존 서비스, 비슷한 과거 장애, 런북
  → diagnose          원인 가설 + 근거(도구 결과 인용) + 확신도
  → propose_fix       조치 계획(허용 목록 안에서만)
  → human_approval    interrupt() — 승인 / 수정 / 거절
  → execute           MCP k8s-write (서버 측 dry-run 뒤 실행)
  → verify            다시 조회해 회복 확인
  → postmortem        장애 기록을 지식 그래프에 쓴다
```

- **상태**는 Pydantic 모델로 타입을 고정한다(incident, evidence 목록, hypotheses, plan, approval).
- **체크포인트**는 온프레미스 Postgres(`langgraph-checkpoint-postgres`의 PostgresSaver)에 둔다. GKE에서 시작해 승인 대기 중이던 조사를 GKE 노드가 꺼진 뒤 k3s 쪽에서 이어 갈 수 있다(클러스터 간 연결이 될 때 — §3 배치 원칙 3).
- **모델 분업**: 기본은 모든 역할이 온프레미스 Gemma다(사용자 결정 2026-11-16 — 요청 한도가 없고 클러스터 데이터가 회사 밖으로 나가지 않는다). Gemini는 회사 GPU에 닿지 않을 때(저장소를 클론한 사람, GKE에서 회사 서버에 연결하지 못할 때)의 대체이자 평가의 비교 기준이다. round01b부터 같은 시나리오를 두 모델로 돌려 비교하고, Gemma가 기준에 못 미치는 역할을 Gemini로 돌릴지는 round07 라우팅 실험에서 정한다. 두 쪽 다 OpenAI 호환 API라 같은 클라이언트 코드로 부른다(Gemini 3가 도구 호출마다 붙이는 `thought_signature`를 다음 요청에 되돌려 주는 작은 확장만 `llm.py`에 둔다).
- **MCP 서버**는 공식 Python SDK(FastMCP)로 직접 만든다. SDK 2.x는 FastMCP를 MCPServer로 바꿨지만 에이전트 쪽 `langchain-mcp-adapters`가 아직 1.x만 지원해 워크스페이스 전체를 `mcp>=1.30,<2`로 고정한다(round01a).
  - `k8s-read`: 클러스터마다 하나. 그 클러스터의 읽기 전용 ServiceAccount만 갖는다.
  - `k8s-write`: 데모 네임스페이스에만 권한이 있는 별도 ServiceAccount. 도구는 rollout restart·rollout undo·범위 안 scale뿐이다.
  - `observability`: Prometheus·Loki 질의.
  - 에이전트는 `langchain-mcp-adapters`로 여러 MCP 서버에 동시에 붙는다.
- **postmortem 기록 고리**: 조치가 끝나면 장애 기록이 지식 그래프에 들어가 다음 진단의 재료가 된다.
- **서빙**: FastAPI + SSE 스트리밍. 웹 UI는 학습 대상이 아니므로 Nuxt로 채팅·조사 타임라인·승인 버튼만 최소로 만든다(round06).

## 5. GraphRAG — Neo4j 두 층

**구조 층** (LLM 없이 결정적으로 채움)
- 노드: Cluster, Namespace, Deployment, Service, Pod, Node
- 관계: `CONTAINS`, `RUNS_ON`, `SELECTS`, `CALLS`(Tempo 서비스 그래프)
- 동기화 잡이 k8s API와 Tempo를 주기적으로 읽어 갱신한다.

**지식 층** (LLM 구조화 출력으로 추출, 스키마 고정 — 회사 GPU의 Gemma가 기본, Gemini와 비교해 round05에서 정한다)
- 노드: Incident, Symptom, Cause, Fix, Runbook
- 관계: `Incident -AFFECTED→ Service`, `Incident -HAD→ Symptom`, `Symptom -CAUSED_BY→ Cause`, `Cause -FIXED_BY→ Fix`, `Runbook -COVERS→ Symptom`
- 원천: 데모 앱용으로 직접 쓴 런북, 쿠버네티스 공식 문서의 트러블슈팅 문서(CC BY 4.0, 출처 표기), 시나리오를 돌리며 쌓이는 postmortem.

**검색**
1. 경보에서 앵커를 잡는다: 대상 서비스 노드 + Symptom 벡터 유사도(Neo4j 벡터 인덱스).
2. k-hop으로 넓힌다: 상·하류 서비스, 비슷한 증상의 과거 Incident, 그 Cause·Fix, 관련 Runbook.
3. 부분그래프를 문맥으로 직렬화해 진단 노드에 넘긴다.

**비교 실험**
- 같은 장애 시나리오에서 벡터만 쓴 RAG와 GraphRAG의 진단 정확도를 비교한다(§6 평가 러너).
- Microsoft GraphRAG 라이브러리(커뮤니티 요약·global search)는 `research/`에서 1회성 비교로만 돌린다.

## 6. 관측·평가

- **인프라 관측**: kube-prometheus-stack(Prometheus·Alertmanager·Grafana) + Loki + Tempo, 회사 GPU 서버.
- **에이전트 추적**: OpenTelemetry 계측 → Langfuse. 조사 1건 = 트레이스 1개. 노드별 지연·토큰·비용을 온프레미스/클라우드 모델로 나눠 본다.
- **시나리오 평가**: `eval/scenarios/<이름>.yaml` 하나가 다음을 담는다.
  - 장애 주입 절차, 기대 원인 라벨, 기대 조치
  - 러너가 주입 → 경보(또는 직접 질문) → 에이전트 실행 → 채점까지 자동으로 돈다.
  - 채점: 원인 라벨 일치, 근거 인용 여부, 단계 수·시간·비용, **위험 행동 시도 횟수(0이어야 함)**.
- **검색 품질**: 런북 질의 세트로 RAGAS context precision·recall을 재 벡터 RAG와 GraphRAG를 비교한다.
- 평가 결과는 라운드 완료노트에 수치로 남긴다. 사람 검증 없이 LLM 채점만 한 수치는 그렇다고 적는다.

## 7. 라운드 로드맵

| 라운드 | 내용 | 완료 기준 |
|---|---|---|
| round00 | 저장소 골격 + 라운드 방식 이식(§8), uv 워크스페이스·ruff·pytest, GitHub Actions CI, gitleaks, devcontainer | main·dev 브랜치, 운영 문서·템플릿·스킬·리뷰 에이전트가 있고 CI green |
| round01a | 로컬 티어 기반: 개발 PC kind + 데모 앱 + 장애 2종 + MCP `k8s-read`(읽기 전용 RBAC), kind 통합 테스트 CI, GCP·두 티어 문서 전환 | 장애 2종의 단서를 MCP 도구로 확인하는 통합 테스트가 CI에서 green |
| round01b | 끝-끝 경로: 직접 짠 LangGraph 단일 에이전트(MCP `k8s-read` 도구, 조사 예산) + LLM 두 종(기본 회사 GPU의 Gemma, 비교 기준 Gemini 무료 등급 Flash-Lite, 클러스터는 로컬 티어 kind), 평가 러너 v0(새 멤버 `eval`) | Gemma 시나리오 2종 × 3회와 Gemini 시나리오마다 1회의 결과표 — 원인 라벨 정답률·근거 인용률·도구 호출 수·시간·토큰·형식이 깨진 도구 호출 |
| round02 | 온프레미스(GPU 티어): 회사 GPU 서버의 k3s·GPU Operator·vLLM(기존 Gemma 인스턴스를 k3s 관리로 옮김)·임베딩 모델, Argo CD, Helm 차트(로컬 티어는 같은 차트를 로컬 값으로), SOPS | git push만으로 회사 GPU 서버의 k3s에 에이전트·데모 앱이 배포되고, 온프레미스 LLM(Gemma) triage가 동작 |
| round03 | 클라우드: Terraform(GKE·Gemini(Vertex AI)·Secret Manager·Workload Identity Federation·예산 알림), ApplicationSet으로 GKE 배포, 이미지는 GHCR, 야간 GKE 노드 0 축소, 클러스터 간 연결(§10 결정에 따름) | GKE 노드를 켜면 같은 차트가 자동 배포되고, GKE의 에이전트가 조사한다 — 회사 서버의 vLLM(Gemma)에 연결되면 그것을, 안 되면 Gemini(Vertex AI)를 쓴다 |
| round04 | 관측: Prometheus·Loki·Tempo, Alertmanager → 에이전트 웹훅, Langfuse | 장애 주입만으로 경보 → 조사 시작까지 자동, 트레이스가 Langfuse에 남음 |
| round05 | GraphRAG: Neo4j 두 층, 추출·검색, 벡터 RAG와 비교 | 비교 수치가 완료노트에 있음 |
| round06 | 멀티에이전트 + 사람 승인: supervisor·서브에이전트, PostgresSaver, interrupt, MCP `k8s-write`, verify, postmortem 기록, 웹 UI | 웹에서 승인 → 조치 → 회복 확인 → 그래프 기록까지 한 번에 돎 |
| round07 | 평가 고도화 + LLM 라우팅: 시나리오 10종 이상(프롬프트 인젝션 1종 포함), Chaos Mesh, 온프레미스/클라우드 모델 분업 비율 실험 | 라우팅 정책별 정확도·비용 표가 완료노트에 있음 |

라운드 안에서 성격이 다른 덩어리가 생기면 `round02a`·`round02b`처럼 접미로 나눈다. 접미 라운드도 spec·plan·완료노트·교본을 따로 둔다.

### 저장소 구조

```
hybrid-ops-agent/
├─ CLAUDE.md · GIT_WORKFLOW.md · README.md · .gitignore      운영 파일만 루트에
├─ agent/            LangGraph 에이전트 + FastAPI
├─ mcp_servers/      k8s_read · k8s_write · observability
├─ graphrag/         구조 층 동기화 · 지식 추출 · 검색
├─ demo_app/         gateway · orders · inventory
├─ eval/             scenarios/ · 러너
├─ web/              Nuxt UI (round06)
├─ deploy/           kind/ · helm/ · argocd/
├─ infra/            terraform/gcp/ · onprem/(k3s 부트스트랩)
├─ docs/             superpowers/{specs,plans} · roadmap · guides · standards · ops
├─ scripts/          재실행되는 운영 도구
├─ research/         1회성 실험(스크립트 + 산출물)
└─ .claude/          skills/round-finish · agents/code-reviewer
```

Python 패키지(`agent`·`mcp_servers`·`graphrag`·`demo_app`·`eval`)는 uv 워크스페이스 멤버로 묶는다. CLI 이름은 `hoa`.

## 8. 라운드 방식 이식

**그대로 가져온다**
- `CLAUDE.md` 단일 진입점, 산출물 위치 규칙(`scripts/`=재실행 도구, `research/`=1회성 실험).
- `GIT_WORKFLOW.md`: `main`(배포 기준) / `dev`(통합) / `<type>/round<NN>-<설명>`(작업), 영문 kebab-case 브랜치명, 작업 브랜치 → dev 머지와 dev → main 머지는 매번 사용자 승인.
- 커밋 메시지 `[Type] 한국어 설명`, `Co-Authored-By` 트레일러 없음.
- 라운드 생애주기: 브레인스토밍 spec → writing-plans plan → TDD 구현 → code-reviewer 서브에이전트 정적 리뷰 → 단위 테스트(CI) + 수동 스모크 → 교본·완료노트·`00_status.md` → 승인 머지(`dev`) → `/round-finish`(`dev→main`).
- 교본: 라운드마다 `docs/guides/round<NN>/`에 1권, 전체 코드 수록(발췌·플레이스홀더 금지) + 면접 Q&A.
- `docs/ops/recurring-gotchas.md`(실제로 돌려 봐야만 드러나는 함정), `docs/standards/coding-standard.md`.

**바꾼다**
- 배포가 GitOps라 "main = 배포 기준"이 문자 그대로가 된다. Argo CD가 `main`을 본다. `dev`는 CI(kind 통합 테스트)로만 검증한다.
- `GIT_WORKFLOW.md`의 개발 환경 절은 kind / k3s / GKE 기준으로 새로 쓴다(docker compose·Portainer 내용은 가져오지 않는다).
- code-reviewer 에이전트에 인프라 점검을 더한다: Terraform plan 변화, RBAC 최소 권한, 비밀값 커밋 여부, 이미지 태그 고정.
- CI 게이트: ruff, pytest, gitleaks(round00), shellcheck·kind 통합 테스트(round01a), `helm lint`·kubeconform(round02), `terraform fmt -check`·`terraform validate`(round03). 검사 대상 파일이 처음 생기는 라운드에 그 게이트를 더한다 — 대상 없는 검사는 아무것도 증명하지 못한다.
- 개발 PC가 바뀌어도 되도록 개발 환경은 uv + devcontainer로 재현한다.
- 교본에 「개념 입문」 절을 더한다 — 학습 프로젝트라 라운드마다 처음 나온 개념을 기초부터 정리한다(2026-11-10 사용자 요청).

## 9. 안전·테스트·비용

**에이전트 안전**
- 쓰기 도구는 허용 목록(rollout restart·rollout undo·범위 안 scale)만, 데모 네임스페이스에서만, 서버 측 dry-run 뒤, 사람 승인이 있을 때만 실행된다. 권한 경계는 프롬프트가 아니라 RBAC로 보장한다.
- 모든 쓰기 시도(승인·거절 포함)를 감사 로그로 남긴다.
- 로그·이벤트·런북 안의 문장은 데이터로만 다룬다. 조치는 구조화된 plan을 거쳐서만 실행된다. 로그에 심은 프롬프트 인젝션을 평가 시나리오로 하나 둔다(round07).
- 조사 1건당 토큰 상한을 둔다.

**테스트**
- 그래프 노드·라우팅 로직: 가짜 LLM으로 결정적 단위 테스트.
- MCP 서버: kind 클러스터에 붙인 통합 테스트.
- 시나리오 평가: 라운드 검증 단계에서 손으로 돌린다. CI는 LLM·클라우드·회사망을 부르지 않는 검사만 돌린다(로컬 티어, 가짜 LLM).

**비용**
- GCP 예산 알림을 건다(금액은 round03에서 사용자가 정한다).
- 매일 밤 GitHub Actions 예약 작업이 GKE 노드를 0으로 줄인다(방식은 round03에서 정한다).
- Gemini는 round01~02에 결제를 연결하지 않은 무료 등급 키만 쓴다. 무료 등급 입력은 구글 서비스 개선에 쓰일 수 있어 데모 데이터와 공개 문서만 보낸다.
- `terraform apply`는 CI가 아니라 로컬에서 손으로만 한다.

## 10. 라운드 spec으로 넘기는 결정

다음은 해당 라운드를 시작할 때 측정·확인한 뒤 그 라운드 spec에서 정한다.

| 결정 | 라운드 | 판단 근거 |
|---|---|---|
| Gemini 모델 이름(무료 등급) | round01b — 결정: `gemini-3.5-flash-lite`(`HOA_GEMINI_MODEL`로 바꾼다) | 2026-11-16 실측 — 3.5 Flash는 무료 등급 하루 20회에 조사 1건 약 200초, 3.8·3.7 Flash는 503·시간 초과, 2.5 Flash는 404. 3.5 Flash-Lite는 같은 조사를 26초에 맞혔다 |
| 조사 1건의 문맥·토큰 예산 | round01b — 결정: 도구 호출 6번, 마지막 요청의 입력 토큰 26,000 | GPU 티어 32K 문맥에 진단 요청까지 들어가는 크기(도구 출력 상한 응답당 12,000자). 실측 조사 1건은 도구 2~3번, 모델 호출 4~5번 |
| 임베딩 모델·서빙 방식(vLLM / TEI) | round02 | 회사 GPU 서버에서 실측한 메모리·지연 |
| GKE 운영 방식(Standard 노드 0 축소 / Autopilot) | round03 | 체험 크레딧 소모, 정지 방식. 노드를 0으로 줄여도 클러스터 관리 수수료·LB·디스크·고정 IP는 남는다. Autopilot을 고르면 「노드 0」을 전제한 문구(`CLAUDE.md` §4·완료노트 템플릿·round-finish)를 사용자 승인을 받아 고친다 |
| 온프레미스 Argo CD의 GKE 등록 방식 — 회사망에서 GKE API로 나가는 연결, 자격 증명(서비스 계정 키 / 외부 OIDC Workload Identity Federation / GKE 쪽 별도 배포) | round03 착수 전 | 회사 망 정책, 키를 두지 않는 원칙. 안 되면 GKE에는 GitHub Actions나 GKE 쪽 Argo CD로 배포한다 |
| GKE ↔ 회사 GPU 서버 연결 가능 여부(Tailscale 등) | round03 착수 전 | 회사 망 정책 — 안 되면 GKE 쪽은 Gemini만 쓰고 독립으로 돈다 |
| GCP 예산 알림 금액 | round03 | 사용자 결정 |
| 회사 서버 RAM에 따른 Langfuse 셀프호스팅 이전 여부 | round04 | 관측 스택을 올린 뒤 남는 메모리 |
| Neo4j 위치·메모리 한도 | round05 | 서버 RAM, 그래프 크기 — 메모리를 정하지 않으면 서버 RAM에 맞춰 크게 잡으므로 힙·페이지 캐시를 명시한다 |
| 지식 층 추출 모델(Gemini / Gemma) | round05 | 손으로 정답을 단 작은 세트로 비교 |

## 11. 위험 요소

| 위험 | 대응 |
|---|---|
| 회사 GPU 서버에서 다른 시스템과 GPU·메모리를 나눠 쓴다 | 모든 컨테이너에 requests/limits를 두고 round02에서 실측해 한도를 정한다. 서버의 기존 시스템은 사용자 승인 없이 건드리지 않는다 |
| 회사 서버 접근이 끊기면 GPU 티어가 멈춘다 | 로컬 티어로 계속 개발한다. 주기 백업 스크립트를 둔다 — Postgres(round02)·Neo4j(round05) |
| GCP 무료 체험 90일이 GKE를 쓰는 라운드(round03~07)보다 먼저 끝난다 | 체험은 round03 직전에 시작하고, 끝나면 GKE 작업을 그때 범위로 줄이거나 유료 전환을 사용자에게 묻는다 |
| round03에 결제 계정을 AI Studio 키가 있는 프로젝트에 연결하면 그 Gemini 키가 유료 등급이 된다 | 결제 연결은 사용자 승인 대상(`CLAUDE.md` §4)이고, 무료 키와 결제 프로젝트를 분리한다 |
| 회사 서버에 k3s를 올리며 런타임·iptables가 바뀌고, k3s 기본 대역(10.42/16·10.43/16)이 사내 대역과 겹칠 수 있다 | round02 spec에서 사내 대역을 확인해 `--cluster-cidr`·`--service-cidr`를 정하고, 설치는 사용자 승인 뒤에 한다 |
| Gemma 4의 도구 호출이 정해진 형식을 벗어나 일반 텍스트로 나온다 | 평가 러너에 도구 호출 실패율을 넣고, 기준 미달이면 그 역할은 Gemini로 돌린다 |
| GKE 노드를 끄지 않아 체험 크레딧이 줄어든다 | 야간 자동 축소 + 예산 알림 |
| public 저장소에 비밀값·회사 정보가 노출된다 | gitleaks pre-commit + CI, 커밋 전 직접 확인과 code-reviewer 점검(내부 주소는 gitleaks가 못 잡는다), SOPS 암호화, Workload Identity Federation으로 키 자체를 줄임 |
