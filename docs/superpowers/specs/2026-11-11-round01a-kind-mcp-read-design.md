# round01a — kind 개발 클러스터·데모 앱·MCP `k8s-read` 설계

> 상태: 초안(2026-11-11) — 사용자 검토 대기
> 라운드: round01a. round01을 성격에 따라 둘로 나눈 앞쪽이다 — 01a는 클러스터·데모 앱·MCP 읽기 도구(LLM 없음), 01b는 에이전트·LLM 두 티어·평가 러너 v0.
> 전체 설계: `docs/superpowers/specs/2026-11-09-hybrid-ops-agent-design.md` — 이 라운드에서 §7.3대로 고친다.
> 브랜치: `feat/round01a-kind-mcp-read`

## 1. 목표와 완료 기준

개발 PC의 kind 클러스터에 데모 앱을 띄우고 장애 2종을 심는다. 그 증상을 MCP `k8s-read` 서버의 읽기 전용 도구로 확인할 수 있게 하고, 이 과정을 CI의 kind 통합 테스트가 push마다 검증한다. LLM은 부르지 않는다 — 비용이 없고 Gemini 키도 필요 없다. 이 kind 클러스터가 로컬 티어(§4)의 바탕이 된다.

같이 하는 일: 2026-11-10~11의 결정(클라우드 GCP 전환, 회사 GPU 서버와 두 티어 — §3)을 운영 문서와 전체 설계에 반영한다.

완료 기준:

1. `bash scripts/dev-cluster.sh up` 하나로 kind 클러스터 `hoa`에 데모 앱 세 서비스가 뜬다 — 개발 PC(Windows, Git Bash)와 CI(Linux) 모두.
2. 장애 2종 각각에서 MCP 도구 출력에 원인 단서가 나오는 것을 통합 테스트가 확인한다(§5.3 표).
3. MCP 서버의 자격 증명(읽기 전용 ServiceAccount)으로는 `demo` 밖 네임스페이스와 Secret을 읽지 못하는 것을 통합 테스트가 확인한다.
4. CI 세 잡이 green이다 — 린트·테스트, 비밀값 검사, 통합 테스트(kind).
5. 운영 문서와 전체 설계에 Azure·AKS·집 PC 서술이 남지 않는다(round00 기록 문서와 설계서의 「바뀐 이력」은 그대로 둔다). devcontainer가 바뀐 구성으로 실제 기동한다.

## 2. 범위

| 이번에 한다 | 이번에 하지 않는다(언제) |
|---|---|
| kind 클러스터 스크립트, 일반 YAML 매니페스트 | Helm 차트·Argo CD(round02) |
| 데모 앱 3서비스(메모리 데이터) | Postgres(DB 장애 시나리오가 들어오는 라운드), OpenTelemetry 계측(round04) |
| 장애 2종 주입·복구(스크립트) | 시나리오 YAML·평가 러너(round01b) |
| MCP `k8s-read` 도구 4개, 읽기 전용 RBAC | 에이전트·LLM 호출·`llm.py`(round01b), `k8s-write`(round06) |
| 단위 테스트, kind 통합 테스트, CI 잡 | 이미지 레지스트리 push(round03, GHCR) |
| 운영 문서·전체 설계의 GCP·두 티어 전환 | gcloud 도구·GCP 리소스(round03) |
| devcontainer에서 Azure CLI 제거, kubectl 버전 고정 | devcontainer 안에서 kind 쓰기(§8) |

## 3. 배경 결정 (2026-11-10~11, 사용자 결정)

### 3.1 클라우드: Azure → GCP

- 이유: Azure 무료 체험은 Azure OpenAI 할당량이 0이라 round01부터 종량제가 필요하다. GCP 무료 체험($300, 90일)은 자동 과금이 없다. 학습 대상 기술은 클라우드 종류에 기대지 않는다. (팀장 권고, 사용자 결정 2026-11-10)
- 대응: AKS → GKE, Azure OpenAI → Gemini, Key Vault → Secret Manager, AKS Workload Identity → GKE Workload Identity Federation, `az aks stop` → GKE 노드를 0으로 줄이기(Standard 노드 풀인지 Autopilot인지는 round03에서 정한다).
- 시점: round01~02는 Google AI Studio의 Gemini API 무료 등급 키(개인 Google 계정, 결제 미연결)만 쓴다. GCP 무료 체험은 GKE가 처음 필요한 round03 직전에 시작한다 — 90일이 가입 시점부터 흐르고 멈출 수 없다.

### 3.2 온프레미스: 집 PC → 회사 GPU 서버, 두 티어

- 사용자가 회사 GPU 서버(H200 1장)를 이 프로젝트에 쓸 수 있게 됐다(2026-11-11). SSH로 k3s·GPU Operator·vLLM을 직접 올릴 수 있고, 다른 시스템이 함께 돌아 이 프로젝트가 쓸 수 있는 GPU 메모리는 약 60GB다.
- 집 RTX 3060 PC는 계획에서 뺀다. 개발 PC와 GPU 서버가 같은 망에 있어 집↔회사 터널이 필요 없고, GPU도 더 크다.
- 로컬 LLM은 서버에 이미 vLLM으로 떠 있는 Gemma 4 26B A4B를 쓴다. MoE 모델이라 전체 25.2B 중 토큰마다 3.8B만 계산하고, 도구 호출을 지원한다(vLLM `--enable-auto-tool-choice --tool-call-parser gemma4`). 현재 `--max-model-len 32768`이다.
- round01b는 이 인스턴스를 그대로 부르고, round02에서 같은 모델을 이 프로젝트의 k3s(GPU Operator·Helm·Argo CD) 관리로 옮긴다 — GPU 메모리를 두 배로 쓰지 않으면서 vLLM 운영을 익힌다.
- Neo4j는 GPU를 쓰지 않지만, 예전에 이 서버에서 메모리를 크게 잡아 무거웠다. 둘 곳과 메모리 한도는 round05에서 정한다.

### 3.3 round01 나누기

- round01a(이 문서) — 클러스터·데모 앱·MCP 읽기 도구. LLM 없이 끝까지 검증된다.
- round01b — LangGraph 단일 에이전트, LLM 두 티어(Gemini·Gemma), 평가 러너 v0. 01a가 끝난 뒤 따로 spec을 쓴다(§11).

## 4. 실행 티어와 회사 자원 경계

### 4.1 두 티어

| 티어 | 클러스터 | LLM | 쓰는 곳 |
|---|---|---|---|
| GPU 티어 | 회사 GPU 서버의 k3s(round02) | vLLM의 Gemma 4 26B A4B(32K 문맥) | 운영 시연, 많이 부르는 평가 |
| 로컬 티어 | 개발 PC의 kind(이번 라운드) | Gemini 무료 등급, CI에서는 가짜 LLM | 개발, CI, 저장소를 클론한 사람 |
| (클라우드) | GKE(round03) | Gemini | 작업할 때만 노드를 켠다 |

- 두 티어는 같은 코드와 같은 Helm 차트(round02)를 쓰고 설정만 다르다. LLM은 둘 다 OpenAI 호환 API라 `llm.py`(round01b)의 설정 묶음으로 바꾼다.
- CI(GitHub Actions)는 회사망에 닿지 않으므로 항상 로컬 티어로 돈다. GPU 티어 검증은 회사망 안의 개발 PC에서 손으로 한다.
- 도구 출력 크기와 문맥 예산은 가장 작은 문맥(GPU 티어 32K)에 맞춘다(§5.4).

### 4.2 회사 자원 경계

- **쓴다**: 회사 GPU 서버의 연산 자원(GPU·CPU·메모리·디스크). 그 위에 올리는 것은 이 저장소의 코드, 공개 가중치 모델, 데모 앱이 만든 데이터, 직접 쓴 문서와 공개 문서뿐이다.
- **쓰지 않는다**: 회사 저장소의 코드(복사·옮겨 적기·의존성 모두), 회사 데이터(업무·고객 데이터, 사내 문서, 회사 시스템의 로그·지표), 회사가 학습시킨 모델, 회사의 다른 서버·클러스터·DB.
- **커밋하지 않는다**: 회사 서버의 주소·호스트명·계정·kubeconfig와 사내 네트워크 구조. `.env`나 저장소 밖 파일에만 둔다. gitleaks는 내부 주소를 잡지 못하므로 커밋 전에 직접 보고, code-reviewer 보안 점검에도 넣는다(§7.4).
- 공개 문서에는 GPU 종류(H200)까지만 적고 회사 이름·주소는 적지 않는다. 로컬 절대 경로처럼 사용자 환경이 드러나는 값도 새로 적지 않는다.
- 로컬 티어의 Gemini 무료 등급은 입력이 구글 서비스 개선에 쓰일 수 있다. 그래서 보내는 것은 데모 데이터와 공개 문서뿐이다 — 회사 데이터는 애초에 쓰지 않는다.
- 서버에서 이미 돌고 있는 시스템(직접 띄운 vLLM 등)을 멈추거나 바꾸는 작업은 사용자 승인 뒤에만 한다(§7.1, `CLAUDE.md` §4).

## 5. 구성 요소

### 5.1 kind 개발 클러스터 — `scripts/dev-cluster.sh`

- bash 스크립트 하나를 개발 PC(Git Bash)와 CI(Linux)가 같이 쓴다. 다시 실행하는 운영 도구라 `scripts/`에 둔다.
- 하위 명령:
  - `up` — 클러스터 `hoa`가 없으면 만든다 → 데모 이미지를 빌드해 `kind load`로 넣는다 → 매니페스트를 적용하고 rollout을 기다린다 → MCP용 kubeconfig를 쓴다(§5.5). 여러 번 실행해도 결과가 같다.
  - `down` — 클러스터를 지운다.
  - `fault <image-pull|bad-config>` — 장애를 심는다(§5.3).
  - `reset` — 기준 매니페스트를 다시 적용해 장애를 걷고 rollout을 기다린다.
  - `mcp-kubeconfig` — 읽기 전용 ServiceAccount의 토큰을 새로 받아 kubeconfig를 다시 쓴다.
- 모든 kubectl 호출은 `--context kind-hoa`를 명시한다 — 개발 PC에 회사 서버 컨텍스트가 같이 있어도 다른 클러스터를 건드리지 않는다.
- 버전 고정: kind v0.33.0, 노드 이미지는 그 릴리스의 이미지를 다이제스트까지 고정한다(정확한 값은 plan에서 릴리스 노트로 확인한다). 스크립트는 시작할 때 `kind version`이 고정 버전인지 확인한다. devcontainer의 kubectl도 노드와 같은 마이너로 고정한다.
- 매니페스트는 `deploy/kind/`에 일반 YAML로 둔다 — `kind-config.yaml`(노드 1개), `demo/`(Namespace·Deployment·Service), `rbac/`(§5.5), `faults/`(§5.3). round02에서 데모 앱 매니페스트는 Helm 차트로 바뀌고, 로컬 티어는 그 차트를 로컬 값으로 쓴다.

### 5.2 데모 앱 — 새 멤버 `demo_app`

- 패키지 `hoa-demo`, import 이름 `hoa_demo`. FastAPI + httpx, 데이터는 메모리에 둔다.
- 서비스 3개, 호출 흐름 `gateway → orders → inventory`:
  - gateway `GET /api/orders/{order_id}` → orders `GET /orders/{order_id}` → inventory `GET /stock/{sku}`. gateway가 주문과 재고를 합쳐 돌려준다.
  - 세 서비스 모두 `GET /healthz`를 둔다(readiness·liveness 프로브).
  - 하류 호출이 실패하면 gateway·orders는 502와 원인(어느 서비스, 어떤 오류)을 돌려준다.
- 이미지 하나에 역할을 환경변수로 고른다 — `HOA_DEMO_ROLE`(gateway·orders·inventory), `HOA_DEMO_PORT`, 하류 주소(`HOA_DEMO_ORDERS_URL`, `HOA_DEMO_INVENTORY_URL`). 시작할 때 Pydantic 모델로 설정을 검증하고, 틀리면 무엇이 틀렸는지 한 줄 로그를 남기고 종료 코드 1로 끝난다 — 장애 `bad-config`의 단서가 된다.
- 이미지:
  - `demo_app/Dockerfile`, 빌드 컨텍스트는 저장소 루트. 무시 목록은 `demo_app/Dockerfile.dockerignore`에 둔다 — BuildKit이 Dockerfile 옆의 이 파일을 읽으므로 루트에 `.dockerignore`를 두지 않고 `CLAUDE.md` §2의 루트 규칙을 지킨다.
  - 의존성은 `uv sync --locked --package hoa-demo --no-dev`로 이 멤버 것만 설치한다(round00 이월).
  - 태그는 `hoa-demo:0.1.0`으로 고정한다. 레지스트리에 올리지 않고 `kind load`로만 넣는다.
- 매니페스트: Deployment마다 replicas 1, resources requests/limits, 프로브, 기본 RollingUpdate, `progressDeadlineSeconds: 120`(멈춘 롤아웃이 2분 안에 `ProgressDeadlineExceeded`로 드러나게). Service는 ClusterIP.

### 5.3 장애 2종

단서가 나오는 곳이 서로 다른 둘을 골랐다. 주입은 `deploy/kind/faults/`의 패치 파일을 `kubectl patch`로 적용한다. round01b의 시나리오 YAML이 같은 파일을 가리킨다.

| 장애 | 주입 | 증상 | 단서가 있는 곳 | 기대 원인 라벨(01b) |
|---|---|---|---|---|
| `image-pull` | orders 이미지를 없는 태그로 바꾼다 | 새 파드가 `ErrImagePull` → `ImagePullBackOff` | 이벤트(`Failed to pull image ...`), 파드 대기 사유, ReplicaSet별 이미지 | `image_pull_error` |
| `bad-config` | inventory의 `HOA_DEMO_PORT`를 숫자가 아닌 값으로 바꾼다 | 새 파드가 시작 직후 종료를 반복 → `CrashLoopBackOff` | 직전 컨테이너 로그(`previous`), Deployment의 환경변수 | `bad_config` |

둘 다 RollingUpdate라 이전 파드가 살아 있어 서비스는 계속 응답하고, 롤아웃만 멈춘다. 실제 운영에서 흔한 모습이고, 에이전트는 "서비스는 되는데 배포가 끝나지 않는다"를 읽어 내야 한다.

### 5.4 MCP `k8s-read` 서버 — 새 멤버 `mcp_servers`

- 패키지 `hoa-mcp`, import 이름 `hoa_mcp`, 이 서버는 `hoa_mcp.k8s_read`. 공식 MCP Python SDK의 FastMCP로 만들고, 쿠버네티스 API는 `kubernetes_asyncio`로 비동기 호출한다(코딩 표준).
- 실행 방식 — 세 안을 비교해 A로 정했다.

| 안 | 내용 | 장점 | 단점 |
|---|---|---|---|
| **A (채택)** | 호스트에서 stdio로 실행, 읽기 전용 ServiceAccount 토큰으로 만든 kubeconfig | 최소 권한을 처음부터 익힌다. 구성이 가볍고, 01b 에이전트가 stdio로 바로 띄운다 | 클러스터 밖에서 돈다(최종 배치와 다르다) |
| B | 클러스터 안 Deployment + HTTP 전송 | 최종 배치에 가깝다 | 이미지·Service·포트포워드가 더 필요하다 — Helm이 들어오는 round02가 자연스럽다 |
| C | 호스트에서 관리자 kubeconfig로 실행 | 가장 쉽다 | 권한 경계를 배우지 못하고, 실수가 클러스터 전체에 닿는다 |

- 도구 4개. 입력·출력은 Pydantic 모델이다. 도구 설명과 출력은 영어로 쓴다 — LLM과 쿠버네티스 메시지가 영어라서다.

| 도구 | 입력 | 출력 요지 |
|---|---|---|
| `list_pods` | `namespace` | 파드마다 이름·phase·준비된 컨테이너 수·재시작 수·대기 사유(`ImagePullBackOff` 등)·마지막 종료 사유·나이 |
| `get_events` | `namespace`, `object_name`(선택), `limit`(기본 20, 최대 50) | 최신순 이벤트 — 유형·사유·대상·메시지·횟수·마지막 시각 |
| `describe_deployment` | `namespace`, `name` | 원하는·갱신된·준비된·가용 복제 수, conditions, 컨테이너별 이미지·환경변수·resources, ReplicaSet별 리비전·이미지·복제 수 |
| `get_pod_logs` | `namespace`, `pod`, `container`(선택), `previous`(기본 false), `tail_lines`(기본 100, 최대 200) | 로그 줄 목록(최신 줄을 남긴다) |

- **출력 상한**(GPU 티어 32K 문맥 기준): 도구 응답 하나를 직렬화한 크기가 12,000자(약 3K 토큰)를 넘지 않게 자른다. 로그 줄은 500자, 이벤트 메시지는 300자에서 자르고, 목록은 개수로 자른다(로그는 앞쪽, 이벤트는 오래된 쪽을 버린다). 잘렸으면 출력의 `truncated: true`로 알린다. 근거: 시스템 프롬프트·도구 정의 약 3K 토큰 + 도구 호출 6번 × 3K 토큰이면 32K 안에 답변 여유가 남는다. 조사 1건의 누적 예산은 01b에서 정한다.
- **비밀값 가리기**: 환경변수 이름에 `PASSWORD`·`SECRET`·`TOKEN`·`KEY`·`CREDENTIAL`이 들어 있으면(대소문자 무시) 값을 `***`로 가린다. `valueFrom`(Secret·ConfigMap 참조)은 참조 이름만 보이고 값은 읽지 않는다. 로컬 티어에서는 도구 출력이 외부 API(Gemini)로 나가므로 필요한 장치다.
- **허용 네임스페이스**: `HOA_MCP_ALLOWED_NAMESPACES`(쉼표로 구분, 기본 `demo`). 서버가 먼저 확인하고, 밖이면 쿠버네티스를 부르지 않고 도구 오류(`namespace not allowed`)를 돌려준다. RBAC(§5.5)와 이중 방어다 — 서버 확인은 알아보기 쉬운 오류를, RBAC는 실제 경계를 맡는다.
- **오류**: 쿠버네티스 403·404는 도구 오류(MCP `isError`)로 바꿔 무엇이 없는지, 권한이 없는지 적는다. 그 밖의 예외는 숨기지 않고 드러낸다(코딩 표준 「에러 처리」).
- **설정과 진입점**: `HOA_MCP_KUBECONFIG`(kubeconfig 경로), `HOA_MCP_ALLOWED_NAMESPACES`. 콘솔 스크립트 `hoa-mcp-k8s-read`가 stdio로 서버를 띄운다.
- **구조**: 쿠버네티스 응답을 출력 모델로 바꾸는 부분은 순수 함수로 두어 단위 테스트한다. API를 부르는 부분은 주입받는 얇은 계층으로 두어 테스트에서 가짜로 바꾼다.

### 5.5 RBAC와 자격 증명

- Namespace `hoa-system`에 ServiceAccount `hoa-mcp-read`를 둔다.
- ClusterRole `hoa-k8s-read`: `get`·`list`·`watch` — `pods`, `pods/log`, `events`(core와 `events.k8s.io`), `deployments`, `replicasets`, `services`, `endpointslices`. Secret·ConfigMap은 넣지 않고 `*`도 쓰지 않는다.
- `demo` 네임스페이스의 RoleBinding으로 위 ClusterRole을 묶는다 — 권한 정의는 한 번(ClusterRole), 범위는 네임스페이스(RoleBinding)로 좁히는 쿠버네티스 관용 방식이다.
- 토큰: `kubectl create token hoa-mcp-read -n hoa-system --duration=12h`로 만료가 있는 토큰을 받아 kubeconfig를 쓴다. 기본 경로는 저장소 밖 `~/.kube/hoa-kind-mcp-read.kubeconfig`(CI는 `$RUNNER_TEMP`), 파일 권한은 600이다. 저장소 안에 실수로 두더라도 `.gitignore`의 `*.kubeconfig`에 걸린다.

## 6. 테스트·CI

- **단위 테스트**(기본 `pytest`):
  - demo_app — 각 서비스의 응답, 하류 실패 시 502, 설정 검증 실패 시 종료 코드 1과 오류 로그. 하류 호출은 httpx `MockTransport`로 바꾼다.
  - mcp_servers — 변환 함수(대기 사유·재시작 수·conditions 추출), 비밀값 가리기, 출력 상한과 `truncated`, 허용 네임스페이스 거부. 쿠버네티스 응답은 `kubernetes_asyncio` 모델 객체로 만든 가짜를 쓴다.
- **통합 테스트**(`integration` 마커, kind 필요):
  - 마커를 루트 `pyproject.toml`에 등록하고 기본 실행에서 뺀다(`addopts`에 `-m "not integration"`). `uv run pytest -m integration`으로 따로 돌린다.
  - 정상: 세 Deployment가 Available이고, API 서버의 서비스 프록시로 부른 gateway `/api/orders/1`이 200이다.
  - 장애 2종: `bash scripts/dev-cluster.sh fault <이름>`으로 주입 → 증상이 나타날 때까지 기다림(최대 120초 폴링) → MCP 클라이언트 세션으로 도구를 불러 §5.3의 단서를 확인 → `reset`으로 복구.
  - 권한: MCP 서버로 `kube-system`을 부르면 거부된다. 읽기 전용 ServiceAccount로는 `demo`의 Secret 조회가 403이다.
  - MCP 연결: 대부분은 SDK의 메모리 전송(서버와 클라이언트를 한 프로세스에서 연결)으로 부르고, 한 건은 실제 콘솔 스크립트를 stdio로 띄워 도구 목록을 받는다 — 진입점까지 확인한다.
  - 장애 주입·상태 대기는 관리자 컨텍스트로 하고, 도구 호출은 반드시 읽기 전용 kubeconfig로 한다. 테스트 코드의 관리자 클라이언트는 코딩 표준 「외부 호출 격리」(제품 코드 규칙)의 대상이 아니다.
- **CI**(`.github/workflows/ci.yml`):
  - 린트·테스트 잡: 기존 단계 + shellcheck(`uv run pre-commit run shellcheck --all-files` — pre-commit과 같은 버전을 쓴다).
  - 새 잡 「통합 테스트(kind)」: 고정 버전 kind를 내려받고 → `bash scripts/dev-cluster.sh up` → `uv run pytest -m integration`. 실패하면 진단 출력(`kubectl get pods,events -A`, `kind export logs`)을 남긴다. 제한 시간을 둔다. LLM·회사망·클라우드는 부르지 않는다.
- pre-commit에 shellcheck 훅(shellcheck-py)을 더한다. `.sh`가 처음 생기는 라운드라, 검사는 그 파일 종류가 처음 생길 때 더한다는 원칙을 따른다.
- kubeconform은 Helm과 함께 round02에 더한다. 이번 매니페스트는 CI가 실제 kind 클러스터에 적용하므로 스키마 검사보다 강한 검증을 받는다.
- 루트 `pyproject.toml`의 다섯 곳을 새 멤버 둘만큼 고친다(코딩 표준 「패키지 경계」).

## 7. 문서 전환

### 7.1 `CLAUDE.md` — 바꿀 문구 (사용자 승인 대상)

1. §0 프로젝트 한 줄 — 통째로 바꾼다.
   > 온프레미스(회사 GPU 서버의 k3s)와 GCP(GKE·Gemini)를 함께 쓰는 쿠버네티스 운영 에이전트. 같은 코드를 GPU 티어(회사 GPU 서버)와 로컬 티어(개발 PC의 kind, GPU 없음)로 돌린다. 학습 목적의 개인 프로젝트라 각 기술을 "왜 이렇게 썼나"까지 설명할 수 있게 만드는 것이 우선이다. 전체 설계: `docs/superpowers/specs/2026-11-09-hybrid-ops-agent-design.md`.
2. §2 — 마지막 줄 다음에 한 줄을 더한다.
   > - 회사 자원 경계: 회사 GPU 서버는 이 프로젝트의 온프레미스 클러스터(GPU 티어)로 쓴다(2026-11-11 사용 허락). 회사 저장소의 코드·회사 데이터·회사가 학습시킨 모델은 쓰지 않는다 — 복사하지도, 보고 옮겨 적지도 않는다. 회사 서버의 주소·호스트명·계정·kubeconfig와 사내 네트워크 정보는 커밋하지 않고 `.env`나 저장소 밖 파일에만 둔다. gitleaks는 내부 주소를 잡지 못하므로 커밋 전에 직접 확인한다.
3. §3 라운드 번호 줄 — 끝에 덧붙인다.
   > 접미 라운드도 각각 한 라운드로 센다 — spec·plan·완료노트·교본을 따로 두고, 파일·폴더 이름에 접미를 그대로 쓴다(`round01a-완료노트.md`, `docs/guides/round01a/`).
4. §3 확인 지점 줄 — 괄호를 바꾼다.
   - 전: (비용이 나는 Azure 작업 승인은 §4대로 따로 받는다)
   - 후: (비용이 나는 클라우드 작업과 회사 서버의 기존 시스템을 건드리는 작업의 승인은 §4대로 따로 받는다)
5. §4 반복 함정 줄 — 「클러스터·배포·Azure 작업이나」를 「클러스터·배포·클라우드 작업이나」로 바꾼다.
6. §4 Azure 비용 줄 — 아래 두 줄로 바꾼다.
   > - 비용이 나는 클라우드 작업은 사용자 승인 뒤에만 한다 — GCP 결제 계정 연결·무료 체험 시작, 리소스를 만들거나 켜는 작업(`terraform apply`, GKE 노드 늘리기). 작업이 끝나면 GKE 노드를 0으로 줄이는 것까지가 그 작업이다. Gemini API는 결제를 연결하지 않은 무료 등급 키만 쓰고, 유료 전환은 사용자 승인 대상이다.
   > - 회사 GPU 서버에서 이미 돌고 있는 시스템(직접 띄운 vLLM 등)을 멈추거나 바꾸는 작업과 서버 자체 설정(드라이버·방화벽·컨테이너 런타임)을 바꾸는 작업은 사용자 승인 뒤에만 한다. 쿠버네티스 명령은 이 프로젝트의 컨텍스트(`kind-hoa`, round02부터 GPU 티어 k3s)를 명시해서만 실행한다.

6번이 round00 이월의 「대량 호출 비용 승인 규칙」을 대신한다 — 결제를 연결하지 않은 무료 등급은 요금이 나지 않으므로, 승인 지점은 유료 전환이다.

### 7.2 `GIT_WORKFLOW.md`

- 브랜치 모델의 서브라운드 줄: 파일·폴더 이름에도 접미를 그대로 쓴다는 문장을 더한다(§7.1의 3번과 같은 내용).
- 머지 승인 규칙의 push 줄: 끝 문장을 「비용이 나는 클라우드 작업과 회사 서버의 기존 시스템을 건드리는 작업의 승인(`CLAUDE.md` §4)은 별도다」로 바꾼다 — 두 파일에 같은 문장이 있으므로 같이 고친다(round00 「결정」).
- 품질 게이트 표: shellcheck(pre-commit + CI, round01a)와 통합 테스트 `pytest -m integration`(CI, kind, round01a)을 더한다. 「두 곳에 적힌 도구 버전」 줄에 kind를 더한다 — `.github/workflows/ci.yml`의 다운로드 버전과 `scripts/dev-cluster.sh`가 확인하는 버전을 같이 올린다.
- 개발 환경 표:
  - devcontainer 도구에서 az를 뺀다(uv·kubectl·helm·terraform). gcloud는 round03에 더한다.
  - 「개발 PC: kind」 → 로컬 티어, round01a.
  - 「집 PC」 → 「회사 GPU 서버: k3s + GPU Operator」, GPU 티어(모델·데이터·관측·Argo CD), round02.
  - 「Azure AKS」 → 「GCP GKE」, 작업할 때만 노드를 켜는 클라우드 클러스터, round03.
- 개발 환경 절에 kind 절차를 더한다: 준비물(Docker Desktop, kind v0.33.0), `bash scripts/dev-cluster.sh up|down|fault|reset|mcp-kubeconfig`, kind는 호스트에서만 쓴다(devcontainer에서는 kind API 주소 `127.0.0.1`에 닿지 않는다 — §8), Windows는 Git Bash로 실행한다.
- 개발 가이드 문서의 리뷰 흐름: 교본 대조를 `scripts/check_guide.py`로 한다고 적는다(§8).

### 7.3 전체 설계 spec(`2026-11-09-hybrid-ops-agent-design.md`)

- 머리말: 「바뀐 이력」 줄을 더한다 — 2026-11-11(round01a) 클라우드 Azure → GCP, 온프레미스 집 PC → 회사 GPU 서버와 두 티어, round01을 01a·01b로 나눔, 근거는 이 문서 §3.
- §1 목적·학습 대상: 온프레미스는 회사 GPU 서버, 클라우드는 GCP(GKE). §1·§2에서 라운드 방식과 교본 형식의 출처로 적은 이전 프로젝트 이름은 빼고 「이전 프로젝트」로 줄인다(§4.2 — 내부 프로젝트 이름을 현재 문서에 남기지 않는다. 이미 커밋된 이력과 round00 기록 문서는 그대로 둔다).
- §2 결정 요약: 온프레미스(회사 GPU 서버, H200 1장, 이 프로젝트 가용 GPU 메모리 약 60GB), 클라우드(GCP — GKE·Gemini·Secret Manager, 이유는 §3.1), 비용 운영(GKE 노드는 작업할 때만), 클라우드 LLM(Gemini — round01~02는 무료 등급 키), 로컬 LLM(Gemma 4 26B A4B, vLLM, 32K 문맥) 행을 고치고, 「실행 티어」 행을 더한다.
- §3 전체 배치: 표를 회사 GPU 서버·GKE·GCP 관리형(Gemini·Secret Manager·예산 알림)·Langfuse·개발 PC(로컬 티어)로 바꾸고, §4.1의 두 티어 표와 §4.2의 회사 자원 경계를 요약해 넣는다. 배치 원칙 3(클러스터 간 연결)은 「GKE와 회사 GPU 서버의 연결(Tailscale 등)은 회사 망 정책을 확인한 뒤 round03에서 정한다」로 바꾸고 §10으로 넘긴다. 배치 원칙 4는 GKE Workload Identity Federation·Secret Manager로 바꾼다. 데모 앱의 Postgres는 「DB 장애 시나리오가 들어오는 라운드에 더한다」로 바꾼다.
- §4 에이전트 구조: 그림의 `[로컬 8B]` → `[로컬 Gemma]`, `[Azure OpenAI]` → `[클라우드 Gemini]`. 모델 분업은 「기본은 triage만 로컬, 나머지는 클라우드. GPU 티어의 Gemma가 더 커졌으므로 round01b부터 같은 시나리오를 두 모델로 돌려 비교하고, 분업 비율은 round07에서 정한다」로 바꾼다. 체크포인트 설명의 AKS를 GKE로 바꾼다.
- §5 GraphRAG: 지식 층 추출을 「클라우드 Gemini가 기본, 회사 GPU의 Gemma와 비교해 round05에서 정한다」로 바꾼다.
- §6 관측·평가: 관측 스택 위치를 회사 GPU 서버로, Langfuse 구분을 「로컬/클라우드」로 바꾼다.
- §7 로드맵: round01 행을 round01a·round01b 두 행으로 나눈다. round02는 회사 GPU 서버의 k3s·GPU Operator·vLLM(기존 Gemma 인스턴스를 k3s 관리로 옮김)·Argo CD·Helm·SOPS. round03은 GCP — Terraform(GKE·Gemini(Vertex AI)·Secret Manager·Workload Identity Federation·예산 알림), ApplicationSet으로 GKE 배포, 이미지는 GHCR, 야간 노드 0 축소, GKE↔회사 서버 연결은 §10 결정에 따른다. round07의 「로컬/Azure」를 「로컬/클라우드」로 바꾼다. 저장소 구조의 `infra/terraform/azure/`를 `infra/terraform/gcp/`로, `deploy/`에 `kind/`를 더한다.
- §8 바꾼다: 개발 환경 기준을 「kind / k3s / GKE」로 바꾼다.
- §9 안전·테스트·비용: 시나리오 평가 줄은 「CI는 LLM·클라우드·회사망을 부르지 않는 검사만 돌린다(로컬 티어, 가짜 LLM)」로, 비용은 GCP 예산 알림과 야간 GKE 노드 0 축소(방식은 round03)로 바꾼다.
- §10 넘기는 결정: Azure 행들을 지우고 다음으로 바꾼다 — Gemini 모델 이름(round01b, 무료 등급 한도·도구 호출 품질), 임베딩 모델·서빙 방식(round02, 회사 GPU에서 실측), GKE 운영 방식 Standard 노드 0 / Autopilot(round03), GKE↔회사 GPU 서버 연결 가능 여부(round03 착수 전, 회사 망 정책 — 안 되면 GKE 쪽은 Gemini만 쓰고 독립으로 돈다), 회사 서버 RAM에 따른 Langfuse 셀프호스팅 여부(round04), Neo4j 위치·메모리 한도(round05), 지식 층 추출 모델(round05, 손으로 정답을 단 작은 세트로 비교), GCP 예산 알림 금액(round03, 사용자 결정).
- §11 위험 요소: 집 PC 행들을 바꾼다 — 회사 서버에서 다른 시스템과 자원 경쟁(requests/limits, round02 실측), 회사 서버 접근이 끊기면 GPU 티어 정지(로컬 티어로 계속, 백업 스크립트는 round02), Gemma 4 도구 호출이 일반 텍스트로 새는 경우(평가 러너에 도구 호출 실패율, 기준 미달이면 그 역할은 Gemini로), GKE 노드를 끄지 않아 크레딧 소모(야간 자동 축소 + 예산 알림), public 저장소에 비밀값·회사 정보 노출(gitleaks + 커밋 전 확인 + code-reviewer, SOPS, Workload Identity Federation).

### 7.4 그 밖의 문서·설정

| 파일 | 바꾸는 것 |
|---|---|
| `README.md` | 소개 줄, 학습 표, 배치 표를 두 티어·GKE·Gemini로. devcontainer 도구에서 az 제거. 시작하기에 kind 명령(`bash scripts/dev-cluster.sh up`, `uv run pytest -m integration`)을 더한다 |
| `docs/roadmap/00_status.md` | 현재 상태·다음 할 일(round01b)·라운드 이력 |
| `.claude/skills/round-finish/SKILL.md` | 2단계의 「Azure 정지」 → 「클라우드 정지」. 5단계 → 「GKE 노드를 켠 라운드면 노드가 0인지 확인한다 — 확인 명령은 GKE 운영 방식을 정하는 round03에서 여기에 적는다(그 전에는 해당 없음)」 |
| `docs/roadmap/_ROUND_COMPLETE_TEMPLATE.md` | 「Azure 비용」 절 → 「클라우드 비용」(GCP 리소스와 Gemini 유료 사용, 켠 것과 끈 시각). 상태 줄 → 「클라우드 리소스 정지 확인(GKE 노드를 켠 라운드만 — 확인 명령은 round-finish 5단계. 켜지 않은 라운드는 「해당 없음」을 덧붙이고 체크)」 |
| `.claude/agents/code-reviewer.md` | 프로젝트 소개(GKE·두 티어), 실행하지 않는 도구 목록(az → gcloud), 배치 줄(GKE), 인프라 점검(GKE 노드 축소·예산 알림). 보안 점검에 세 가지를 더한다 — 회사 서버 주소·호스트명·계정·사내 네트워크 정보가 커밋됐는지(gitleaks가 못 잡는다), 도구 출력이 비밀값을 가리지 않고 내보내는지, 스크립트·도구가 kubectl 컨텍스트를 명시하지 않아 다른 클러스터에 닿을 수 있는지 |
| `docs/standards/coding-standard.md` | LLM 줄(로컬 vLLM의 Gemma와 클라우드 Gemini, 티어는 설정으로 바꾼다), `integration` 마커 줄(등록했고 기본 실행에서 빠진다), resources 줄의 이유(회사 GPU 서버에서 다른 시스템과 같이 뜬다), 비밀값 줄(GKE는 Secret Manager + Workload Identity Federation). 새 규칙: MCP 도구 출력은 크기 상한과 `truncated`를 두고 비밀값으로 보이는 값을 가린다, 클러스터를 부르는 스크립트는 kubectl 컨텍스트를 명시한다 |
| `docs/ops/recurring-gotchas.md` | 도구 목록에서 az를 빼고, 「집 PC」를 「GPU 서버」로. 구현하며 새로 겪은 함정을 더한다 |
| `pyproject.toml` | 설명 줄(온프레미스 k3s와 GCP GKE) |
| `.devcontainer/devcontainer.json`·`devcontainer-lock.json` | azure-cli 기능을 빼고 kubectl 버전을 고정한다. 잠금 파일을 다시 만들고 실제 기동을 확인한다(반복 함정 2번) |

round00의 기록 문서(완료노트·plan·교본)는 그 라운드의 기록이므로 고치지 않는다.

## 8. round00 이월 처리

| 이월 | 처리 |
|---|---|
| 교본 대조 스크립트를 `scripts/`의 재사용 도구로 둘지 | 둔다 — `scripts/check_guide.py`(표준 라이브러리만). 교본의 「**파일**: `경로`」 다음 코드블록을 실제 파일과 비교해 다르면 diff를 보이고 종료 코드 1을 낸다. 기준 커밋을 지정할 수 있다(`--rev`) — 지난 라운드 교본은 그 라운드의 커밋과 비교한다. 라운드마다 쓰므로 `research/`가 아닌 `scripts/`다. round00 교본(`--rev main`)으로 통과를, 일부러 고친 사본으로 실패를 확인한다 |
| devcontainer 안에서 kind kubeconfig(`127.0.0.1`)가 닿지 않는 문제 | 미룬다. kind와 통합 테스트는 호스트에서 돌리고, devcontainer는 코드·단위 테스트용으로 둔다. 개발 PC가 바뀌어 필요해지면 그때 푼다 |
| Azure OpenAI 대량 호출 비용 승인 규칙 | Gemini 무료 등급 규칙으로 대신한다(§7.1의 6번) |
| 멤버별 이미지는 `uv sync --locked --package <멤버> --no-dev`로 빌드 | demo_app 이미지에 적용한다(§5.2) |
| devcontainer의 kubectl 버전 고정 | 적용한다(§5.1) |
| 접미 라운드 파일 이름 규칙(원래 round02) | 지금 필요하므로 이번에 정한다(§7.1의 3번, §7.2) |
| round02·round03·round06·round07 이월 | 그대로 둔다. round03의 「devcontainer의 terraform·az 버전 고정」은 「terraform·gcloud」로 읽는다 |

## 9. 위험과 대응

| 위험 | 대응 |
|---|---|
| Git Bash가 `/`로 시작하는 인자를 Windows 경로로 바꾼다(MSYS 경로 변환) | 스크립트에서 `MSYS_NO_PATHCONV=1`을 쓰고, 개발 PC와 CI 둘 다에서 실행해 확인한다 |
| Windows에서 커밋한 `.sh`에 실행 비트가 없다 | `git update-index --chmod=+x`로 비트를 넣고, 호출은 문서·CI 모두 `bash scripts/dev-cluster.sh`로 한다 |
| 셸 스크립트에 CRLF가 섞인다 | `.gitattributes`의 LF 고정(반복 함정 1번), shellcheck |
| 장애 증상이 나타나는 시간이 일정하지 않다(CrashLoopBackOff는 10초·20초… 백오프) | 상태를 폴링하고 최대 120초로 제한한다. 실패하면 진단 출력을 남긴다 |
| CI에서 kind 노드 이미지 내려받기가 느리거나 실패한다 | 노드 이미지를 다이제스트로 고정하고, 잡 제한 시간과 `kind export logs`를 둔다 |
| 공식 MCP SDK와 `kubernetes_asyncio`는 API가 자주 바뀐다 | plan에서 설치 버전을 고정하고 그 버전의 문서·소스로 확인한다 |
| 도구 출력이 외부 LLM(Gemini)으로 나간다(01b부터) | 비밀값 가리기, Secret 읽기 권한 없음, 데모 데이터와 공개 문서만 다룬다 |
| kubectl이 다른 클러스터(회사 서버)를 가리킨 채 명령이 실행된다 | 모든 명령에 `--context kind-hoa`를 명시하고, code-reviewer가 점검한다 |

## 10. 검증

- 자동: §6의 단위·통합 테스트, CI 세 잡 green.
- 수동 스모크(개발 PC):
  1. `bash scripts/dev-cluster.sh up` → `kubectl --context kind-hoa -n demo get pods`에서 세 파드가 Running.
  2. `kubectl --context kind-hoa -n demo port-forward svc/gateway 8080:80` → `curl localhost:8080/api/orders/1`이 주문과 재고를 합친 JSON.
  3. `fault image-pull` → `get pods`에 `ImagePullBackOff` → `reset` → 회복. `bad-config`도 같은 순서로 `CrashLoopBackOff`를 확인한다.
  4. (선택, Node.js 필요) MCP Inspector로 서버를 띄워 도구 4개를 화면에서 불러 본다.
  5. devcontainer가 바뀐 구성으로 기동한다.
- 문서: Azure·AKS·`az`·집 PC를 `git grep`으로 찾아 round00 기록 문서와 「바뀐 이력」 말고는 남지 않았는지 본다. `scripts/check_guide.py`로 round01a 교본을 실제 파일과 대조한다.
- 교본은 `docs/guides/round01a/`에 여러 파일로 나눈다(개요·개념 입문, 데모 앱, MCP 서버, 클러스터·CI·문서 — 정확한 파일 목록은 plan에서 정한다). 개념 입문에 넣을 것: 컨테이너 안에서 도는 쿠버네티스(kind), Pod·Deployment·ReplicaSet·Service, 롤링 업데이트와 멈춘 롤아웃, 프로브, `ImagePullBackOff`·`CrashLoopBackOff`, 이벤트와 직전 컨테이너 로그, RBAC(ServiceAccount·ClusterRole·RoleBinding), ServiceAccount 토큰과 kubeconfig, MCP(서버·클라이언트·도구·stdio 전송), async/await, FastAPI, 통합 테스트와 마커, 문맥 길이와 토큰 예산.

## 11. round01b 미리보기

- LangGraph로 단일 에이전트를 직접 그래프로 짠다 — 조사 반복 고리(LLM이 도구 호출을 요청 → MCP로 실행 → 결과를 돌려줌)를 거쳐, Pydantic으로 고정한 구조화 진단(원인 라벨·근거·확신도)을 낸다.
- LLM은 `llm.py` 하나로 두 티어를 부른다 — Gemini(무료 등급)와 회사 GPU의 Gemma 4 26B. 같은 장애 2종을 두 모델로 돌려 정확도·속도·도구 호출 실패율을 비교한다.
- 평가 러너 v0 — 시나리오 YAML(주입은 이번 라운드의 `faults/`를 가리킨다, 기대 원인 라벨) → 주입 → 에이전트 실행 → 채점.
- 01a가 끝난 뒤 따로 spec을 쓴다. 그 전에 Gemma 인스턴스의 도구 호출 옵션을 켠다(사용자).
