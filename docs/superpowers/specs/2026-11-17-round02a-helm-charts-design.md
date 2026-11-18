# round02a — Helm 차트·클러스터 안 MCP 서버·에이전트 API 설계

> 상태: 승인(2026-11-17)
> 라운드: round02a. round02를 둘로 나눈 앞쪽이다. 배포 패키징을 로컬 티어(kind)에서 끝내고, GPU 티어(k3s·GPU Operator·vLLM 이전·임베딩·Argo CD·SOPS)는 round02b에서 한다(§3.1).
> 전체 설계: `docs/superpowers/specs/2026-11-09-hybrid-ops-agent-design.md` §3·§4·§7·§8. 직전 라운드: `docs/superpowers/specs/2026-11-16-round01b-agent-llm-eval-design.md`, `docs/roadmap/round01b-완료노트.md`.
> 브랜치: `feat/round02a-helm-charts`

## 1. 목표와 완료 기준

round01b까지 kind에 일반 YAML로 올리던 데모 앱과, 개발 PC에서만 돌던 MCP `k8s-read` 서버·에이전트를 Helm 차트 셋으로 클러스터 안에 올린다. 로컬 티어(kind)는 그 차트를 kind 값으로 쓰고, CI는 차트와 클러스터 안 배선을 증명한다. round02b는 같은 차트에 GPU 티어 값 파일만 더해 Argo CD로 올리면 되는 상태가 목표다.

완료 기준:

1. `bash scripts/dev-cluster.sh up`이 kind에 차트 셋(데모 앱·MCP `k8s-read`·에이전트)을 설치한다. 장애 주입·복구(`fault`·`reset`)와 평가 러너가 전처럼 돈다.
2. 클러스터 안 에이전트 API에 포트포워드로 경보 문장을 보내면 Gemma로 조사한 진단 JSON이 돌아온다. 손으로 하는 스모크로 장애 2종을 각 1회 돌려 원인 라벨을 맞힌다.
3. 차트로 올린 kind에서 `hoa-eval run --repeat 1`(Gemma)을 돌리면 두 시나리오가 모두 맞는다. 진단 대상이 바뀌지 않았다는 회귀 확인이다.
4. CI 잡이 모두 green이다. 새 차트 잡(helm lint·kubeconform·차트 정책 테스트)이 더해지고, 통합 테스트에는 「에이전트 파드 → 가짜 LLM → MCP 파드 → 쿠버네티스 API」 끝-끝 확인이 더해진다.

## 2. 범위

| 이번에 한다 | 이번에 하지 않는다(언제) |
|---|---|
| 이미지 셋(데모 앱·MCP·에이전트)을 Dockerfile 하나로 | 이미지 레지스트리(round02b에서 정한다 — GHCR을 round03에서 당길지) |
| Helm 차트 셋 + kind 값 파일 | GPU 티어 값 파일, Argo CD, SOPS(round02b) |
| MCP 서버: streamable HTTP 전송, 클러스터 안 ServiceAccount 인증 | MCP HTTP 인증(OAuth) — 클러스터 밖에서 부르는 곳이 생기는 round03에서 다시 본다 |
| 에이전트 HTTP API(`POST /investigations`, 동기, 동시 1건) | Alertmanager 웹훅·비동기 조사(round04), SSE·웹 UI(round06) |
| `dev-cluster.sh`·평가 러너 복구를 차트 기준으로 바꾸고 `deploy/kind/demo`·`deploy/kind/rbac`를 지운다 | k3s·GPU Operator·vLLM 이전·임베딩 모델(round02b) |
| CI: 차트 잡, 차트 기반 통합 테스트. helm·kubeconform 버전 고정, check-yaml에서 `templates/` 제외 | 이그레스 NetworkPolicy(부르는 외부 주소가 티어마다 달라 round02b 이후에 본다) |

## 3. 결정과 이유

### 3.1 round02를 02a(차트)·02b(GPU 티어)로 나눈다

사용자 결정(2026-11-17)이다. 전체 설계 §7의 round02에는 성격이 다른 두 덩어리가 들어 있다. 하나는 회사 서버 작업(k3s·GPU Operator·Gemma vLLM 이전·임베딩)이고, 다른 하나는 배포 패키징(차트·클러스터 안 에이전트·CI 게이트)이다. 회사 서버 작업은 사용자 승인과 일정 조율이 필요하고, 이전하는 동안 그 vLLM을 쓰는 다른 쪽도 멈춘다(`CLAUDE.md` §4). 배포 패키징은 회사 서버 없이 kind와 CI만으로 만들고 검증할 수 있다. 그래서 패키징을 먼저 끝내고, 02b에서는 그 차트를 Argo CD로 GPU 티어에 올린다. 한 라운드로 묶으면 교본·리뷰가 너무 커지고, 서버 일정이 막히면 라운드 전체가 멈춘다.

### 3.2 클러스터 안 에이전트는 작은 HTTP API다

사용자 결정(2026-11-17)이다. 고려한 안은 세 가지였다.

| 안 | 장점 | 단점 |
|---|---|---|
| **HTTP API Deployment(채택)** | 늘 떠 있어 Argo CD(02b)가 다루기 자연스럽다. round04 Alertmanager 웹훅의 바탕이 된다 | HTTP 계층과 그 테스트만큼 범위가 늘어난다 |
| 조사 1건 = Job 1개 | CLI 계약을 그대로 쓰고 새 코드가 가장 적다 | 경보마다 Job을 만드는 스크립트가 필요하고, 「배포된 에이전트」가 없다 |
| 에이전트는 개발 PC에 둔다 | 범위가 가장 작다 | 전체 설계 §7의 「에이전트가 배포된다」가 모두 02b로 밀린다 |

### 3.3 차트는 컴포넌트마다 하나다

사용자 결정(2026-11-17)이다. 장애를 심는 대상(데모 앱)과 진단하는 쪽(MCP·에이전트)은 릴리스와 롤백을 따로 한다. 02b에서는 Argo CD Application 셋으로 따로 동기화하고, round03에서는 GKE에 데모 앱 사본만 따로 올린다. 우산 차트는 설치 명령이 하나지만 대상과 진단 쪽이 한 릴리스로 묶인다. 차트 하나에 모두 넣으면 켜고 끄는 `if` 분기가 늘어난다.

## 4. 준비물과 환경

- **helm**: 개발 PC 호스트에 설치한다. kind와 통합 테스트는 호스트에서 돈다 — devcontainer 안에서는 kind API 주소에 닿지 않는다(`GIT_WORKFLOW.md` §개발 환경). 같은 버전(v4.3.2)을 devcontainer 기능 옵션, CI 다운로드 URL·체크섬, `scripts/dev-cluster.sh`, 문서에 고정한다. Helm 4는 새 릴리스를 server-side apply로 올린다(§5.5).
- **kubeconform**: CI에만 둔다. 버전(v0.8.0)과 체크섬을 다운로드 단계에 고정하고, 스키마는 쿠버네티스 v1.37.0(kind 노드와 같다)으로 본다.
- **기존 kind 클러스터**: kubectl로 만든 리소스에는 Helm 소유 표시가 없어 `helm install`이 거절한다. 전환할 때 한 번 `down` → `up`한다(README·완료노트에 안내).
- **LLM 설정**: `.env`(커밋하지 않는다)에서 `HOA_GEMMA_BASE_URL`·`GEMINI_API_KEY`·`HOA_GEMINI_MODEL`만 골라 클러스터 안 Secret `hoa-agent-llm`으로 만든다. 회사 vLLM 주소가 클러스터 안 Secret에만 생기고 저장소에는 남지 않는다. 만드는 과정에서 값을 출력하지 않는다.
- **kind 파드에서 회사 vLLM**: 개발 PC가 회사망 안이면 Docker Desktop NAT를 거쳐 닿을 것으로 본다. 스모크 전에 확인한다(§8).

## 5. 구성 요소

### 5.1 이미지 셋 — `deploy/docker/Dockerfile`

- Dockerfile 하나가 `ARG PACKAGE`(uv 패키지 이름 `hoa-demo`·`hoa-mcp`·`hoa-agent`)와 `ARG MEMBER`(폴더 `demo_app`·`mcp_servers`·`agent`)로 이미지 셋을 만든다. 방식은 지금 `demo_app/Dockerfile`과 같다. 의존성 레이어를 먼저 설치하고(`--no-install-workspace`), 소스를 복사해 다시 설치하고, 실행 이미지에는 가상환경만 옮기고, 비루트 `65532:65532`로 돈다.
- 멤버 pyproject를 복사하는 목록이 한 곳에만 있어, 멤버가 늘면 Dockerfile 하나와 그 옆 `Dockerfile.dockerignore`만 고친다. `demo_app/Dockerfile`·`Dockerfile.dockerignore`는 지우고, 코딩 표준 「패키지 경계」의 예시 경로를 바꾼다.
- 이미지마다 `uv sync --package`로 자기 멤버의 의존성만 담는다. 예를 들어 MCP 이미지에는 LangGraph가 없고, 에이전트 이미지에는 MCP 서버 패키지가 없다(에이전트는 클러스터 안에서 HTTP로 붙는다).
- 실행 명령은 차트가 정한다(`hoa-demo`·`hoa-mcp-k8s-read`·`hoa serve`).
- 태그는 `0.1.0`으로 고정한다(`hoa-demo:0.1.0`·`hoa-mcp:0.1.0`·`hoa-agent:0.1.0`). kind에는 `kind load docker-image`로 넣고, 태그가 같으므로 다시 올릴 때는 rollout restart한다(지금 방식).

### 5.2 Helm 차트 셋 — `deploy/helm/<이름>`, kind 값은 `deploy/values/kind/<이름>.yaml`

| 차트 | 릴리스 네임스페이스 | 만드는 것 |
|---|---|---|
| `demo-app` | `demo` | values의 서비스 목록(`inventory`·`orders`·`gateway`)마다 Deployment·Service |
| `mcp-k8s-read` | `hoa-system` | Deployment·Service `hoa-mcp-k8s-read`, ServiceAccount `hoa-mcp-read`, ClusterRole `hoa-k8s-read`, 대상 네임스페이스마다 RoleBinding, NetworkPolicy |
| `agent` | `hoa-system` | Deployment·Service `hoa-agent`, NetworkPolicy, 기존 Secret 참조 |

- **demo-app**
  - 렌더 결과가 지금 `deploy/kind/demo/*.yaml`과 같은 객체여야 한다. 이름, 라벨(`app: <이름>` 셀렉터 포함), 환경변수, 프로브, 자원, securityContext가 같아야 장애 패치(`deploy/kind/faults/`)와 시나리오 YAML이 그대로 맞는다.
  - plan의 한 단계에서 렌더 결과와 기존 YAML을 비교해 같음을 확인한 뒤 기존 파일을 지운다.
- **mcp-k8s-read**
  - ClusterRole 규칙은 지금 `deploy/kind/rbac/mcp-read.yaml` 그대로다(pods·events·pods/log·deployments·replicasets 읽기, Secret·ConfigMap 없음).
  - RoleBinding은 values `targetNamespaces`(kind는 `[demo]`)의 네임스페이스마다 만든다. 허용 네임스페이스 환경변수(`HOA_MCP_ALLOWED_NAMESPACES`)도 같은 값에서 채운다 — RBAC과 서버 검사가 어긋나지 않게.
  - ServiceAccount 이름이 그대로라 `dev-cluster.sh mcp-kubeconfig`(개발 PC stdio용 12시간 토큰)도 그대로 돈다.
  - NetworkPolicy: 인그레스는 `hoa-system`의 에이전트 파드에서 MCP 포트로 오는 것만 허용한다.
- **agent**
  - NetworkPolicy는 인그레스를 모두 막는다. 02a에서 부르는 쪽은 포트포워드뿐이다. Alertmanager 쪽 문은 round04에 연다.
  - LLM 설정은 차트 밖에서 만든 Secret을 values `existingSecret`(kind는 `hoa-agent-llm`)으로 참조한다. 비밀값은 차트와 values에 들어가지 않는다.
  - 쿠버네티스 API를 부르지 않으므로 `automountServiceAccountToken: false`다.
- **공통**
  - 모든 컨테이너에 requests/limits를 두고, 데모 앱과 같은 securityContext(비루트·권한 상승 금지·capability 제거·seccomp·읽기 전용 루트 파일시스템)를 쓴다.
  - 표준 라벨 `app.kubernetes.io/name`·`app.kubernetes.io/instance`를 붙인다.
  - 이미지 저장소·태그는 values로 둔다.
  - 네임스페이스는 차트가 만들지 않는다. kind는 `deploy/kind/namespaces.yaml`(`demo`·`hoa-system`, 둘 다 `pod-security.kubernetes.io/enforce: restricted`)을 스크립트가 적용하고, 02b의 Argo CD는 네임스페이스 메타데이터 설정으로 같은 라벨을 단다. 차트는 `.Release.Namespace`만 쓴다(대상 네임스페이스의 RoleBinding만 예외).

### 5.3 MCP 서버 — HTTP 전송과 클러스터 안 인증

- **전송** `HOA_MCP_TRANSPORT=stdio|http`(기본 `stdio` — 개발 PC CLI와 평가 러너는 바뀌지 않는다).
  - `http`는 FastMCP streamable HTTP로 `${HOA_MCP_HOST:-127.0.0.1}:${HOA_MCP_PORT:-8080}`의 `/mcp`에 연다. 차트가 파드 안에서 `HOA_MCP_HOST=0.0.0.0`을 준다. 기본값을 루프백으로 둔 것은 개발 PC에서 HTTP 모드를 띄워도 LAN에 열리지 않게 하려는 것이다 — 허용 Host는 접근 제어가 아니다(구현 리뷰 반영, 2026-11-18).
  - `stateless_http=True`로 둔다. 에이전트가 조사마다 연결을 열고 닫으므로 서버가 세션을 쥘 필요가 없고, 복제본이 늘어도 세션을 한 파드에 고정하지 않아도 된다.
  - 진행 알림을 스트리밍하지 않으므로 응답은 JSON(`json_response=True`)으로 둔다.
  - 프로브용 `/healthz`를 둔다. 쿠버네티스 API를 부르지 않는다.
- **DNS 리바인딩 보호**: FastMCP(mcp 1.30)는 localhost에 묶을 때만 허용 Host 검사를 저절로 켠다. `0.0.0.0`에 묶으면 꺼지므로 `HOA_MCP_ALLOWED_HOSTS`(차트가 Service 이름들과 포트포워드용 `127.0.0.1:*`·`localhost:*`로 채운다)를 명시해 켠다. `http`인데 이 값이 비면 설정 오류로 시작하지 않는다.
- **인증** `HOA_MCP_KUBE_AUTH=kubeconfig|in-cluster`(기본 `kubeconfig`).
  - `kubeconfig`는 지금 규칙 그대로다. `HOA_MCP_KUBECONFIG`가 필요하고 컨텍스트가 정확히 1개여야 한다.
  - `in-cluster`는 파드의 ServiceAccount 토큰을 쓴다(`kubernetes_asyncio`의 `load_incluster_config`). 이때 `HOA_MCP_KUBECONFIG`가 함께 있으면 설정 오류다. 시작할 때 토큰을 한 번 읽어 보고, 없으면 원인과 함께 종료 코드 2로 끝난다 — 파드가 Ready인데 도구만 모두 실패하는 상태를 막는다(구현 리뷰 반영). 투영된 SA 토큰은 주기적으로 바뀌므로 호출마다 토큰 파일을 다시 읽는다.
- 도구 4개, 허용 네임스페이스 검사, 출력 상한, 비밀값 가리기는 그대로다.

### 5.4 에이전트 HTTP API — `hoa serve`

- **구성**: `hoa_agent/api.py`의 FastAPI 앱 팩토리가 조사 함수를 주입받는다(테스트에서 가짜를 끼운다). `hoa serve [--port 8080]`이 uvicorn 워커 하나로 연다. `agent` 의존성에 `fastapi`·`uvicorn`을 더한다(데모 앱이 이미 잠금 파일에 올려 둔 패키지다).
- **`POST /investigations`**
  - 본문은 `InvestigationRequest{alert: str}`(1~2,000자)이다.
  - 조사를 끝까지 돌린 뒤(동기) 200과 `InvestigationResult` JSON을 돌려준다. CLI `--json`과 같은 모양이다.
  - 모델은 서버 설정 `HOA_MODEL`(`gemma`·`gemini`, 기본 `gemma`)로만 정한다. 요청마다 바꾸지 않는다.
- **동시 1건**: 조사 중에 또 요청이 오면 기다리게 하지 않고 바로 429와 `Retry-After`를 준다. 조사 예산(도구 6번·문맥 26K)이 1건 기준이고, GPU 티어에서는 GPU를 다른 시스템과 같이 쓰기 때문이다.
- **제한 시간**: 조사 전체에 `HOA_INVESTIGATION_TIMEOUT`(기본 300초)을 둔다. 넘으면 조사를 취소하고(MCP 세션도 닫힌다) 504를 준다.
- **오류 분류**: CLI 종료 코드와 같은 분류를 한 함수에 두고, CLI(종료 코드)와 API(상태 코드)가 함께 쓴다. 본문은 `ApiError{kind, message}`이고, 원문에 내부 주소가 섞일 수 있는 예외는 서버 로그에만 남긴다(MCP 서버와 같은 규칙).

  | 상황 | CLI | API | `kind` |
  |---|---|---|---|
  | 진단 완료 | 0 | 200 | — |
  | 요청 형식 오류(경보 길이 등) | — | 422 | FastAPI 기본 |
  | 조사 중 | — | 429 | `busy` |
  | 조사 실패(LLM 오류·스키마 위반) | 1 | 502 | `investigation_failed` |
  | 설정 오류(MCP 연결 실패·LLM 키·주소 없음) | 2 | 503 | `setup_error` |
  | LLM 요청 한도 | 3 | 503 | `llm_rate_limited` |
  | 제한 시간 초과 | — | 504 | `timeout` |

- **`GET /healthz`**: 프로세스만 본다. LLM이나 MCP가 죽었다고 에이전트를 재시작하지 않는다 — 그건 503으로 알린다.
- **설정 검사 시점**: `hoa serve`는 시작할 때 `HOA_MCP_URL`이 없으면 종료 코드 2로 끝난다. MCP 주소는 차트가 늘 채우는 값이고, 에이전트 이미지에는 stdio로 띄울 MCP 서버가 없기 때문이다. LLM 설정은 요청 때 검사한다(503 `setup_error`). `.env` 없이 올린 kind에서도 파드는 Ready가 되고, 무엇이 없는지는 응답이 알려 준다.
- **MCP 연결**(`mcp_tools.py`): `HOA_MCP_URL`이 있으면 `streamable_http` 연결, 없으면 지금처럼 stdio다. 그래서 개발 PC의 `hoa investigate`도 포트포워드로 클러스터 안 MCP에 붙을 수 있다. 세션 밖 예외 풀기(`sole_exception`·`surfaced`, 반복 함정 9)는 두 전송이 같은 경로를 탄다.
- **결과 저장**: 하지 않는다. 요청마다 경보 앞부분·원인 라벨·시간·멈춘 이유를 로그 한 줄로 남긴다. 추적은 round04(OpenTelemetry → Langfuse)에서 한다.

### 5.5 로컬 티어 스크립트·평가 러너

- **`dev-cluster.sh up` 순서**
  1. 클러스터를 만들거나 kubeconfig를 다시 쓴다(지금과 같다).
  2. `deploy/kind/namespaces.yaml`을 적용한다.
  3. 이미지 셋을 빌드해 `kind load`한다.
  4. `.env`가 있으면 필요한 키만 골라 Secret `hoa-agent-llm`을 만들거나 바꾼다. 없으면 빈 Secret을 만든다.
  5. 차트 셋을 `helm upgrade --install`한다.
  6. 이미 있던 클러스터면 rollout restart한다(같은 태그).
  7. rollout을 기다린다.
  8. MCP용 kubeconfig를 쓴다.
- **`reset`**: 데모 앱 차트를 다시 `helm upgrade --install`하고, rollout restart → rollout 대기 → 종료 중인 파드가 사라질 때까지 기다린다(`wait_settled`).
- **평가 러너 복구**(`eval/src/hoa_eval/cluster.py`): `kubectl apply -f deploy/kind/demo` 대신 같은 helm 명령을 쓴다. 릴리스 이름·차트·값 경로는 스크립트와 러너 두 곳에 같은 값으로 두고, 통합 테스트가 두 경로를 다 돌린다. 평가 러너가 관리자 컨텍스트로 장애를 주입·복구하는 예외(코딩 표준)에 helm도 들어간다. 컨텍스트는 `--kube-context kind-hoa`로 명시한다.
- **helm이 장애를 되돌리는 방법**: Helm 4는 새 릴리스를 server-side apply로 올린다. `kubectl patch`(장애 주입)는 바꾼 필드의 소유자를 가져가므로, 기준 상태로 되돌리는 `helm upgrade`는 그 필드에서 충돌한다. 그래서 설치·복구 명령은 모두 `--server-side=true --force-conflicts`를 줘서 차트 값으로 그 필드를 되찾는다(plan 작성 중 helm v4.3.2 소스로 확인, 구현 때 실제로 확인). 장애 패치는 지금처럼 차트에 이미 있는 필드(이미지 태그·환경변수 값)만 바꾼다. CI의 「스크립트 장애 주입·복구」 단계가 계속 증명한다.
- **남기고 지우는 것**: `deploy/kind/kind-config.yaml`과 `deploy/kind/faults/`는 그대로 둔다(시나리오 YAML의 패치 경로 규칙도 그대로). `deploy/kind/demo/`·`deploy/kind/rbac/`는 지운다.

## 6. 테스트·CI

- **단위 테스트**(기존 「린트·테스트」 잡)
  - 에이전트 API: httpx `ASGITransport`와 가짜 조사 함수로 시험한다 — 200 응답 모양, 422(경보 길이), 429(동시 1건), 502·503·504와 `kind`, 오류 본문에 예외 원문이 없는지.
  - 오류 분류 함수: CLI 종료 코드와 API 상태 코드가 같은 분류에서 나오는지.
  - MCP 설정: 전송·인증 조합, `http`인데 허용 Host가 없을 때, `in-cluster`와 kubeconfig를 함께 줄 때의 설정 오류.
  - MCP HTTP 앱: `/healthz`, 허용 밖 Host 거절.
  - `mcp_tools`: `HOA_MCP_URL`에 따라 연결 종류를 고르는지.
- **차트 잡**(CI에 새로 — helm·kubeconform 버전 고정)
  - 차트마다 `helm lint`(kind 값 파일 포함).
  - `helm template | kubeconform -strict -summary`. 쿠버네티스 스키마 버전은 kind 노드(v1.37)에 맞춘다. 스키마가 아직 없으면 가장 가까운 버전으로 고정하고 이유를 적는다.
  - 차트 정책 테스트(새 마커 `charts` — 기본 `pytest`에서 빠지고 이 잡에서 돈다): 렌더 결과의 모든 컨테이너에 requests/limits와 비루트 securityContext가 있다, `latest` 태그가 없다, ServiceAccount 토큰은 MCP 파드에만 마운트한다, 모든 Deployment에 NetworkPolicy가 짝지어져 있다(데모 앱 제외).
- **통합 테스트**(kind, 기존 잡 — helm 설치 단계를 더한다)
  - 기존 테스트(stdio MCP·에이전트 배선·러너)는 그대로 돈다.
  - MCP HTTP: 포트포워드로 클러스터 안 MCP 서버의 도구를 부른다 — 데모 파드 목록이 나오고, 허용 밖 네임스페이스는 거절된다.
  - RBAC: `kubectl auth can-i --as=system:serviceaccount:hoa-system:hoa-mcp-read`로 데모 네임스페이스의 Secret과 다른 네임스페이스의 파드를 읽지 못하는지 본다.
  - NetworkPolicy: 다른 네임스페이스의 임시 파드가 MCP Service에 닿지 못하는지 본다. kind 기본 CNI가 NetworkPolicy를 지키는지는 plan에서 확인한다(§8).
  - 끝-끝
    - 표준 라이브러리만 쓰는 가짜 OpenAI 호환 서버 스크립트를 테스트 폴더에 둔다. ConfigMap으로 넣어 에이전트 이미지의 Python으로 실행하므로, 이미지를 따로 받지 않는다.
    - 대본대로 `list_pods` → `get_events` 도구 호출을 내고, 마지막에 구조화 출력 요청에 진단 JSON을 돌려준다.
    - 에이전트의 LLM Secret을 그쪽으로 향하게 하고 `POST /investigations`를 보낸다. 결과의 도구 출력에 실제 데모 파드 이름이 있는지(진짜 MCP 파드와 쿠버네티스 API를 거쳤는지) 본다.
    - 테스트가 끝나면 Secret을 되돌린다.
  - LLM과 회사망은 부르지 않는다.
- **손 검증**(라운드 검증 단계, 개발 PC)
  - 포트포워드로 에이전트 API에 장애 2종을 Gemma로 각 1회 보낸다(완료 기준 2).
  - `uv run --env-file .env hoa-eval run --repeat 1`로 회귀를 확인한다(완료 기준 3).
  - 결과를 완료노트 「수치」에 옮긴다.

## 7. 문서

| 파일 | 바꾸는 것 |
|---|---|
| `GIT_WORKFLOW.md` | 품질 게이트 표(helm lint·kubeconform을 round02a로), 같이 올리는 버전 목록(helm: devcontainer·CI·문서, kubeconform: CI), 개발 환경 절(호스트 helm, `up` 새 순서, 기존 클러스터 전환, 에이전트 API 스모크 — 포트포워드와 `curl --max-time`), 개발 환경 표의 GPU 티어 행을 round02b로 |
| `README.md` | 시작하기에 helm 설치와 클러스터 안 에이전트 호출 |
| 전체 설계 | §7 round02 행을 02a·02b 두 행으로 나누고, 02b 완료 기준의 「온프레미스 LLM(Gemma) triage가 동작」을 「클러스터 안 에이전트가 온프레미스 Gemma로 조사를 끝낸다」로 바꾼다(triage 노드는 round06에 생긴다). §4 서빙 줄(02a는 동기 HTTP API, SSE·웹 UI는 round06), §7 저장소 구조의 `deploy/`(`kind/`·`helm/`·`values/`·`docker/`·`argocd/`), §8 CI 게이트의 helm lint·kubeconform 라운드 |
| `docs/standards/coding-standard.md` | 「패키지 경계」의 Dockerfile 경로, 「쿠버네티스·인프라」에 차트 규칙(값으로 빼는 것, 네임스페이스는 차트 밖, 모든 Deployment에 NetworkPolicy, 비밀값은 `existingSecret` 참조만) |
| `.pre-commit-config.yaml` | check-yaml에서 `^deploy/helm/.*/templates/` 제외(Go 템플릿이라 YAML 파서가 읽지 못한다) |
| `.devcontainer/devcontainer.json` | helm 버전 고정 |
| `.env.example` | 변수 설명에 「`dev-cluster.sh up`이 LLM 변수로 클러스터 안 Secret을 만든다」 한 줄 |
| `docs/ops/recurring-gotchas.md` | 구현하며 새로 겪은 함정 |
| `docs/roadmap/00_status.md`, 완료노트 | 라운드 기록 |

`CLAUDE.md`는 바꾸지 않는다 — §2의 `deploy/`(kind 매니페스트·Helm·Argo CD) 문구가 새 폴더를 이미 포함한다.

교본은 `docs/guides/round02a/`에 round01b처럼 여러 파일로 나눈다. 개념 입문에 넣을 것:
- 컨테이너 이미지: 다단계 빌드, 레이어 캐시, 비루트 실행, uv 워크스페이스에서 멤버 하나만 담기.
- Helm: 차트·템플릿·values·릴리스, `upgrade --install`, rollback, 3-way merge와 server-side apply, 릴리스 소유 표시.
- 클러스터 안 인증: ServiceAccount와 투영된 토큰, in-cluster 설정, ClusterRole + RoleBinding으로 범위 좁히기, `kubectl auth can-i --as`.
- 네트워크·운영 객체: Service와 클러스터 DNS, NetworkPolicy(기본 허용 → 선택되면 거부, 포트포워드와 노드 트래픽), 프로브, Secret, 파드 보안 표준, 포트포워드.
- MCP 전송: stdio와 streamable HTTP, 상태 없는 모드, DNS 리바인딩과 허용 Host.
- 동기 HTTP API 설계: 동시성 제한(429와 `Retry-After`), 제한 시간과 취소, 상태 코드 고르기, 헬스 체크가 의존 대상을 부르지 않는 이유.
- 검사 도구: lint와 스키마 검사(kubeconform), 정책을 테스트로 쓰기.

## 8. 위험과 대응

| 위험 | 대응 |
|---|---|
| kind 파드에서 회사 vLLM에 닿지 않는다(Docker Desktop NAT·사내 방화벽) | 스모크 전에 파드 안에서 확인한다. 안 되면 kind 스모크는 Gemini로 하고, 클러스터 안 Gemma 확인은 round02b(k3s가 같은 서버)로 넘긴다. 완료노트에 그대로 적는다 |
| 장애 패치가 가져간 필드를 helm upgrade가 되찾지 못한다 | `--server-side=true --force-conflicts`(§5.5). 그래도 안 되면 복구를 「장애 패치를 거꾸로 적용」으로 바꾸고 이유를 남긴다. CI 주입·복구 단계가 계속 지킨다 |
| kind 기본 CNI가 NetworkPolicy를 지키지 않는다 | kind v0.24부터 기본 CNI(kindnet)가 NetworkPolicy를 지킨다(릴리스 노트, 2026-11-17 확인). 통합 테스트가 막히는지 직접 본다. 안 지키면 그 확인을 빼고 완료노트에 적은 뒤 k3s(02b)에서 확인한다. 정책 객체 자체는 차트 정책 테스트가 지킨다 |
| kubeconform 스키마가 쿠버네티스 1.37과 맞지 않는다 | 스키마 저장소에 v1.37.0이 있다(2026-11-17 확인). kind 노드를 올릴 때 `-kubernetes-version`을 같이 올린다 |
| MCP HTTP 엔드포인트에 인증이 없다 | ClusterIP, NetworkPolicy(에이전트 파드만), 읽기 전용 RBAC, 허용 네임스페이스, 허용 Host로 막는다. MCP 인증은 클러스터 밖에서 부르는 곳이 생기는 round03에서 다시 본다 |
| 동기 요청이 길다(Gemma 6~20초, Gemini는 더 길 수 있다) | 서버 제한 시간 300초를 두고 `curl --max-time`을 안내한다. 비동기 조사(202 + 상태 조회)는 round04 웹훅 때 다시 정한다 |
| 회사 vLLM 주소가 Secret을 만드는 과정에서 샌다 | 필요한 키만 임시 파일(권한 600)에 골라 `--from-env-file`로 만들고 값을 출력하지 않는다. 커밋 전에 직접 확인한다(`CLAUDE.md` §2) |
| 이미지가 셋으로 늘어 CI 통합 잡이 길어진다 | 같은 Dockerfile이라 기반 이미지·uv 레이어를 공유한다. 잡 제한 시간(20분)을 넘으면 plan에서 빌드 캐시를 더한다 |
| 기존 kind 클러스터에 helm 설치가 소유권 오류로 실패한다 | 전환 때 한 번 `down` → `up`(§4) |

## 9. round02b로 넘기는 것

round02b spec을 쓸 때 이 목록에서 시작한다.

- **k3s**: 사내 대역을 확인해 `--cluster-cidr`·`--service-cidr`를 정한다(전체 설계 §11). 서버에 이미 있는 컨테이너 런타임과 함께 쓰는 방법도 정한다. 설치는 사용자 승인 뒤에 한다(`CLAUDE.md` §4).
- **GPU Operator**: 호스트에 이미 있는 드라이버를 쓸지(드라이버 설치를 끌지) 정한다. 쿠버네티스는 GPU 메모리를 나누지 않는다 — GPU 하나를 k3s 밖 프로세스와 함께 쓰므로 vLLM의 메모리 비율 설정으로 상한을 둔다.
- **GPU 메모리**: 2026-11-16 관측으로 남은 VRAM은 약 18GB다. 사용자에 따르면 서버의 다른 모델 하나를 내리면 30GB 이상을 더 쓸 수 있다(사용자가 직접 하고, 기존 시스템 변경이라 승인 대상이다). Gemma 이전은 같은 메모리를 옮겨 쓰는 것이라 늘지 않으므로, 새로 생기는 몫은 임베딩 모델과 여유분이다.
- **Gemma vLLM 이전**: 내리는 동안 그 모델을 쓰는 다른 쪽이 멈춘다(시점은 사용자가 정한다). 다른 사용처를 위해 주소·포트를 유지할지, 서버 디스크의 가중치를 다시 쓸지 정한다.
- **임베딩 모델·서빙 방식(vLLM / TEI)**: 회사 GPU 서버에서 메모리·지연을 실측해 정한다(전체 설계 §10).
- **Argo CD**: `main`을 본다. Application 셋을 둔다. 데모 앱 Application의 자동 복구(selfHeal)는 평가 러너가 심은 장애를 바로 되돌리므로 동기화 정책을 정한다. 네임스페이스의 파드 보안 라벨도 여기서 단다.
- **SOPS(age)**: 첫 암호화 대상은 에이전트 LLM Secret이다. Argo CD에서 복호화하는 방식을 정하고, 암호화 파일의 `.gitignore` 예외 규칙과 파일 이름 규칙을 더한다(round01a 이월).
- **이미지**: k3s가 이미지를 받을 곳(GHCR을 round03에서 당길지, 서버에서 가져올지)과, 회사망에서 GitHub·GHCR로 나가는 연결을 정한다.
- **값 파일**: `deploy/values/gpu/`.
- **Postgres 백업 스크립트**: 전체 설계 §11은 「Postgres(round02)」라고 쓰지만 Postgres는 round06 체크포인트에서 처음 생긴다. 02b spec에서 문구를 맞춘다.

## 10. 이월 처리

| 이월(출처) | 처리 |
|---|---|
| Helm `templates/`를 check-yaml에서 제외(round01a) | 이번(§7) |
| `k3s.yaml` 무시 패턴(round01a) | 이미 `.gitignore`에 있다 — 확인만 한다 |
| SOPS 암호화 파일 예외 규칙(round01a) | round02b — 암호화 파일이 처음 생기는 라운드에 더한다(대상 없는 규칙은 넣지 않는다) |
| devcontainer helm 버전 고정, kubeconform(round01a) | 이번(§4·§6) |
| MCP 서버·에이전트를 클러스터 안으로(Helm)(round01b) | 이번의 본체(§5) |
| 기존 Gemma vLLM의 k3s 이전, 임베딩 모델(round01b) | round02b(§9) |
