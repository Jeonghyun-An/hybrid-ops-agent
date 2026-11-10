# hybrid-ops-agent — 전체 설계 (브레인스토밍 spec)

> 상태: 설계 확정(2026-11-09, 사용자 승인). round00부터 이 문서를 기준으로 라운드별 plan을 쓴다.
> 이 문서는 프로젝트 전체 설계다. 라운드마다 세부 결정은 그 라운드 spec에 쓰고, 여기와 어긋나면 이 문서를 고친다.

## 1. 목적

- 온프레미스(집 GPU PC)와 클라우드(Azure)를 함께 쓰는 **쿠버네티스 운영 에이전트**를 만든다. 에이전트는 자기가 올라가 있는 하이브리드 클러스터의 장애를 조사·진단하고, 사람 승인을 받아 조치한다.
- 목표는 **이번에 많이 안 해본 기술을 실제로 굴려 보는 것**이다. 서비스 품질보다 각 기술을 "왜 이렇게 썼는가"까지 설명할 수 있게 만드는 것이 우선이다.
- NL-Lib에서 쓰던 **라운드 개발 방식**(spec → plan → TDD → 리뷰 → 승인 머지 → 완료노트·교본)을 그대로 옮겨 쓴다.

### 학습 대상 기술

| 기술 | 이 프로젝트에서의 역할 |
|---|---|
| LangGraph 멀티에이전트 | supervisor + 서브에이전트, 체크포인트(중단·재개), interrupt로 사람 승인 |
| MCP 서버·클라이언트 | 클러스터 조회·조치·관측 도구를 MCP 서버로 직접 만들고, 에이전트가 MCP로 호출 |
| GraphRAG | Neo4j에 클러스터 구조 + 장애 지식 그래프, 벡터 RAG와 진단 정확도 비교 |
| 쿠버네티스 + IaC | 온프레미스 k3s + Azure AKS, Terraform, Helm, Argo CD(GitOps), GitHub Actions |
| 관측·자동 평가 | Prometheus·Loki·Tempo, OpenTelemetry → Langfuse, 장애 시나리오 자동 채점, RAGAS |

## 2. 결정 요약

| 항목 | 결정 | 이유 |
|---|---|---|
| 도메인 | 클러스터 운영 에이전트(장애 진단·조치) | 학습 대상 기술이 전부 자연스럽게 맞물리고, 정답(원인)이 분명해 평가가 쉽다 |
| 온프레미스 | 집 RTX 3060(12GB) PC에 Ubuntu 설치 + k3s, 개발 PC는 Docker Desktop + kind | Linux 직접 설치가 GPU·네트워크 구성이 가장 단순하다 |
| 클라우드 | Azure — AKS(Free 티어), Azure OpenAI, Key Vault | 사용자 선택. AKS Free 티어는 컨트롤 플레인 요금이 없다 |
| 비용 운영 | AKS는 작업할 때만 켠다(`az aks stop/start`), 상시 켜둘 것은 온프레미스에 | 월 수만 원 이하 |
| 클라우드 LLM | Azure OpenAI | 사용자 선택 |
| 로컬 LLM | 3060에서 vLLM으로 8B급 4bit 양자화 모델 + 임베딩 모델 | 싸고 잦은 일(분류·요약)을 맡긴다 |
| 진행 순서 | 얇은 끝-끝 경로 먼저(round01), 이후 라운드마다 두께를 늘림 | 라운드마다 시연할 결과가 나오고 평가 기준이 일찍 생긴다 |
| 교본 | NL-Lib과 같이 전체 코드 수록 + 면접 Q&A, 그리고 처음 나온 개념을 기초부터 정리하는 「개념 입문」(2026-11-10 추가) | 사용자 선택 — 학습 프로젝트라 모르던 분야도 익힌다 |
| 저장소 | https://github.com/Jeonghyun-An/hybrid-ops-agent (개인 계정, public) | 포트폴리오. 비밀값 커밋은 gitleaks로 막는다 |

## 3. 전체 배치

| 위치 | 켜짐 | 올라가는 것 |
|---|---|---|
| 집 3060 PC (Ubuntu + k3s + NVIDIA GPU Operator) | 상시 | vLLM(로컬 LLM·임베딩), Neo4j, Postgres(LangGraph 체크포인트), Prometheus·Alertmanager·Grafana·Loki·Tempo, Argo CD, 데모 앱, 에이전트·MCP 서버 |
| AKS (Terraform으로 생성) | 작업할 때만 | 에이전트 API·MCP 서버·웹 UI(상태 없는 것만), 데모 앱 사본 |
| Azure 관리형 | 사용량 과금 | Azure OpenAI, Key Vault, 예산 알림 |
| Langfuse Cloud(무료 등급) | 상시(SaaS) | 에이전트 트레이스·평가 데이터셋 |
| 개발 PC (Docker Desktop + kind) | 개발할 때 | round01 끝-끝 경로, 이후 로컬 개발·통합 테스트 |

배치 원칙:

1. **상태가 있는 것(DB·모델·관측)은 상시 켜진 온프레미스에 둔다.** AKS를 꺼도 데이터가 남는다.
2. **상태 없는 앱은 Helm 차트 하나로 두 클러스터에 같이 배포한다.** Argo CD(온프레미스에서 실행) ApplicationSet이 k3s와 AKS 양쪽을 대상으로 잡는다. AKS가 꺼져 있으면 온프레미스 쪽 에이전트가 응답한다.
3. **두 클러스터는 Tailscale로 묶는다.** Tailscale 쿠버네티스 오퍼레이터로 집 PC의 Neo4j·vLLM·Postgres를 AKS에서 사설 주소로 부른다. 집 공유기 포트는 열지 않는다. (검토한 대안: Azure Arc + Flux — 더 Azure답지만 쓰는 곳이 좁아 채택하지 않음)
4. **비밀값**: AKS는 Workload Identity로 키 없이 Azure OpenAI·Key Vault에 접근한다. 온프레미스는 SOPS(age)로 암호화한 시크릿을 git에 둔다.
5. **Langfuse는 Cloud 무료 등급부터 쓴다.** 셀프호스팅 v3는 ClickHouse까지 필요해 집 PC 한 대에 다른 스택과 같이 올리기 무겁다. 계측은 OpenTelemetry로 해 두어 백엔드를 바꿀 수 있게 한다.

### 진단 대상 — 데모 앱

직접 만드는 작은 3-서비스 앱: `gateway → orders → inventory` + Postgres. 각 서비스는 OpenTelemetry로 계측한다(Tempo 서비스 그래프가 GraphRAG 구조 층의 의존 관계 재료가 된다).

장애는 쿠버네티스 단골부터 심는다: 이미지 태그 오류(ImagePullBackOff), 메모리 한도 초과(OOMKilled), 잘못된 환경변수(CrashLoopBackOff), Service 셀렉터 불일치(엔드포인트 없음), 하류 서비스 지연. round07에서 Chaos Mesh로 넓힌다.

## 4. 에이전트 구조 — LangGraph + MCP

```
경보(Alertmanager 웹훅)·사용자 질문
  → triage            [로컬 8B]       경보 분류, 대상 클러스터·네임스페이스·심각도
  → supervisor        [Azure OpenAI]  조사 계획, 서브에이전트 배정
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
- **체크포인트**는 온프레미스 Postgres(`langgraph-checkpoint-postgres`의 PostgresSaver)에 둔다. AKS에서 시작해 승인 대기 중이던 조사를 AKS가 꺼진 뒤 k3s 쪽에서 이어 갈 수 있다.
- **모델 분업**: triage만 로컬 모델, 계획·진단·추출은 Azure OpenAI. 이 분업 비율이 round07 라우팅 실험의 대상이다. 두 쪽 다 OpenAI 호환 API라 같은 클라이언트 코드로 부른다.
- **MCP 서버**는 공식 Python SDK(FastMCP)로 직접 만든다.
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

**지식 층** (Azure OpenAI 구조화 출력으로 추출, 스키마 고정)
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

- **인프라 관측**: kube-prometheus-stack(Prometheus·Alertmanager·Grafana) + Loki + Tempo, 집 PC.
- **에이전트 추적**: OpenTelemetry 계측 → Langfuse. 조사 1건 = 트레이스 1개. 노드별 지연·토큰·비용을 로컬/Azure로 나눠 본다.
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
| round01 | 끝-끝 경로: 개발 PC kind + 데모 앱 + 장애 2종 + MCP `k8s-read` + 단일 LangGraph 에이전트 + Azure OpenAI, 평가 러너 v0 | 시나리오 2종을 러너로 돌려 원인 라벨을 맞힘, 단위 테스트 green |
| round02 | 온프레미스: 집 PC Ubuntu·k3s·GPU Operator·vLLM, Tailscale, Argo CD, Helm 차트, SOPS | git push만으로 집 k3s에 에이전트·데모 앱이 배포되고, 로컬 LLM triage가 동작 |
| round03 | 클라우드: Terraform(AKS·Azure OpenAI·Key Vault·Workload Identity·예산 알림), ApplicationSet으로 AKS 배포, 이미지는 GHCR, 야간 `az aks stop` | AKS를 켜면 같은 차트가 자동 배포되고, AKS의 에이전트가 Tailscale로 집 vLLM·Neo4j를 부름 |
| round04 | 관측: Prometheus·Loki·Tempo, Alertmanager → 에이전트 웹훅, Langfuse | 장애 주입만으로 경보 → 조사 시작까지 자동, 트레이스가 Langfuse에 남음 |
| round05 | GraphRAG: Neo4j 두 층, 추출·검색, 벡터 RAG와 비교 | 비교 수치가 완료노트에 있음 |
| round06 | 멀티에이전트 + 사람 승인: supervisor·서브에이전트, PostgresSaver, interrupt, MCP `k8s-write`, verify, postmortem 기록, 웹 UI | 웹에서 승인 → 조치 → 회복 확인 → 그래프 기록까지 한 번에 돎 |
| round07 | 평가 고도화 + LLM 라우팅: 시나리오 10종 이상(프롬프트 인젝션 1종 포함), Chaos Mesh, 로컬/Azure 분업 비율 실험 | 라우팅 정책별 정확도·비용 표가 완료노트에 있음 |

라운드 안에서 성격이 다른 덩어리가 생기면 `round02a`·`round02b`처럼 접미로 나눈다.

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
├─ deploy/           helm/ · argocd/
├─ infra/            terraform/azure/ · onprem/(k3s 부트스트랩)
├─ docs/             specs · superpowers/{specs,plans} · roadmap · guides · standards · ops
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
- `GIT_WORKFLOW.md`의 개발 환경 절은 kind / k3s / AKS 기준으로 새로 쓴다(docker compose·Portainer 내용은 가져오지 않는다).
- code-reviewer 에이전트에 인프라 점검을 더한다: Terraform plan 변화, RBAC 최소 권한, 비밀값 커밋 여부, 이미지 태그 고정.
- CI 게이트: ruff, pytest, gitleaks(round00), `helm lint`·kubeconform(round02), `terraform fmt -check`·`terraform validate`(round03). 검사 대상 파일이 처음 생기는 라운드에 그 게이트를 더한다 — 대상 없는 검사는 아무것도 증명하지 못한다.
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
- 시나리오 평가: 라운드 검증 단계에서 손으로 돌린다. CI는 Azure 비용이 들지 않는 검사만 돌린다.

**비용**
- Azure 예산 알림을 건다(금액은 round03에서 사용자가 정한다).
- 매일 밤 GitHub Actions 예약 작업이 `az aks stop`을 실행한다.
- `terraform apply`는 CI가 아니라 로컬에서 손으로만 한다.

## 10. 라운드 spec으로 넘기는 결정

다음은 해당 라운드를 시작할 때 측정·확인한 뒤 그 라운드 spec에서 정한다.

| 결정 | 라운드 | 판단 근거 |
|---|---|---|
| Azure OpenAI 배포 모델·리전 | round01 | 리전별 모델 가용성, 단가 |
| 로컬 LLM 모델명, 임베딩 서빙 방식(vLLM 2개 인스턴스 / TEI) | round02 | 3060 12GB에서 실측한 메모리·지연 |
| 집 PC 메모리에 따른 Langfuse 셀프호스팅 이전 여부 | round04 | 관측 스택을 올린 뒤 남는 메모리 |
| Azure 예산 알림 금액 | round03 | 사용자 결정 |

## 11. 위험 요소

| 위험 | 대응 |
|---|---|
| 집 PC 한 대에 GPU 모델·Neo4j·관측 스택이 몰려 메모리 부족 | Langfuse는 Cloud로 시작, round02에서 실측 후 리소스 한도 설정 |
| 집 네트워크·전원이 끊기면 상태 저장소가 같이 멈춤 | 학습 프로젝트라 감수한다. Postgres·Neo4j는 주기 백업 스크립트를 둔다(round02) |
| 8B 로컬 모델의 triage 품질 부족 | triage 결과를 평가 러너로 따로 채점하고, 기준 미달이면 Azure 소형 모델로 대체 |
| AKS를 끄는 것을 잊어 요금 발생 | 야간 자동 stop + 예산 알림 |
| public 저장소에 비밀값 노출 | gitleaks pre-commit + CI, SOPS 암호화, Workload Identity로 키 자체를 줄임 |
