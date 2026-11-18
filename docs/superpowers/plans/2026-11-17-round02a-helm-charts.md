# round02a — Helm 차트·클러스터 안 MCP 서버·에이전트 API Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 데모 앱·MCP `k8s-read` 서버·에이전트를 Helm 차트 셋으로 kind(로컬 티어) 클러스터 안에 올린다. MCP 서버는 streamable HTTP와 ServiceAccount 인증으로 돌고, 에이전트는 HTTP API(`POST /investigations`)로 조사한다. CI는 차트(helm lint·kubeconform·정책 테스트)와 클러스터 안 배선(가짜 LLM 끝-끝)을 증명한다.

**Architecture:** 이미지 셋은 Dockerfile 하나(`deploy/docker/Dockerfile`, `ARG PACKAGE`·`ARG MEMBER`)로 만든다. 차트는 컴포넌트마다 하나(`deploy/helm/{demo-app,mcp-k8s-read,agent}`)이고, 티어마다 다른 값(이미지·Secret 이름)은 `deploy/values/kind/`에 둔다. MCP 서버는 설정(`HOA_MCP_TRANSPORT`·`HOA_MCP_KUBE_AUTH`)으로 stdio·kubeconfig(개발 PC)와 HTTP·in-cluster(파드)를 고른다. 에이전트는 `hoa serve`가 FastAPI 앱을 열고, 조사는 CLI와 같은 `run_investigation`을 `HOA_MCP_URL`(HTTP)로 부른다. 실패 분류는 `failures.py` 한 곳에서 CLI 종료 코드와 API 상태 코드를 함께 낸다. `scripts/dev-cluster.sh`·평가 러너·MCP 통합 테스트는 `helm upgrade --install --server-side=true --force-conflicts`로 데모 앱을 기준 상태로 되돌린다.

**Tech Stack:** Python 3.12, uv 0.11 워크스페이스, mcp 1.30(FastMCP streamable HTTP), langchain-mcp-adapters 0.3.2, kubernetes-asyncio 36.1, FastAPI 0.163 + uvicorn 0.54, httpx 0.28, pytest 9 + anyio, Helm v4.3.2, kubeconform v0.8.0(쿠버네티스 스키마 v1.37.0), kind v0.33.0(노드 v1.37.0), Docker Desktop.

**spec:** `docs/superpowers/specs/2026-11-17-round02a-helm-charts-design.md`

**plan을 쓰며 확인한 것(2026-11-17) — Task 1에서 spec에 반영한다:**
- **Helm**: 최신은 v4.3.2(2026-11-13)다. Helm 4는 새 릴리스를 server-side apply로 올린다(`install`의 `--server-side` 기본값 `true`, `upgrade`는 `auto` = 이전 릴리스의 방식, `upgrade --install`의 첫 설치도 server-side — 소스 `pkg/cmd/install.go`·`upgrade.go` v4.3.2). `kubectl patch`(장애 주입)는 바꾼 필드의 소유자를 가져가므로, 기준 상태로 되돌리는 `helm upgrade`는 그 필드에서 충돌한다. 그래서 설치·복구 명령은 모두 `--server-side=true --force-conflicts`를 준다(`--force-conflicts`는 `--force`와 함께 쓸 수 없다). Task 13에서 충돌과 되찾기를 실제로 확인한다.
- **kubeconform**: 최신은 v0.8.0(2026-06-04)이다. 스키마 저장소(`yannh/kubernetes-json-schema`)에 `v1.37.0-standalone-strict`가 있다. linux-amd64 체크섬 `9bc2bffbf71f261128533edaf912153948b7ff238f9a531ae6d34466ec287883`.
- **Helm 체크섬**: linux-amd64 `d1c0278d46beab79582d7e50f5b3dc206944ba8e577cde618513fd07daa53983`, windows-amd64 zip `77c5c782aaef1abbfafe75b88412d2b6df8e4a36d14522273397f0d02c6ecc29`(릴리스 노트).
- **kind NetworkPolicy**: kind v0.24.0부터 기본 CNI(kindnet)가 NetworkPolicy를 지킨다(kube-network-policies, 릴리스 노트). v0.33.0에서도 그렇다고 보고 Task 16의 통합 테스트로 직접 본다.
- **devcontainer**: `kubectl-helm-minikube` 기능의 `helm` 옵션은 버전 문자열을 받는다(`"4.3.2"` → `v4.3.2`를 받는다).
- **FastMCP(mcp 1.30) HTTP — 스크래치에서 실제로 돌려 확인**:
  - `host`가 localhost일 때만 허용 Host 검사를 저절로 켠다. `0.0.0.0`에 묶으면 꺼진다. `TransportSecuritySettings(allowed_hosts=…)`를 주면 허용 밖 Host에 421을 낸다.
  - 허용 값은 「정확히 같은 문자열」이거나 `<호스트>:*`(Host에 포트가 붙을 때만 맞는다)다. 에이전트는 포트 없는 Service 이름(`hoa-mcp-k8s-read.hoa-system.svc`)으로 부르므로 그 이름을 그대로 적고, 포트포워드는 `127.0.0.1:*`로 받는다.
  - `custom_route("/healthz")`는 Host 검사를 거치지 않는다. kubelet 프로브의 Host는 파드 IP라서 이게 맞다.
  - `stateless_http=True` + `json_response=True`에서 `streamable_http_client(url, http_client=<ASGITransport 클라이언트>)`로 프로세스 안 시험이 된다. 초기화 없는 `tools/list` POST도 200이다.
- **kubernetes-asyncio in-cluster**: `config.load_incluster_config(client_configuration=…)`가 토큰 파일과 CA를 설정에 넣는다. 호출마다 새 설정을 만들면 주기적으로 바뀌는 투영 토큰을 따라간다. 파드 밖에서는 `ConfigException`을 낸다.
- **Helm `required`**: 빈 문자열도 빠진 값으로 본다 — 차트 기본값을 `""`로 두고 티어 값 파일이 채우게 한다.
- **NetworkPolicy**: 파드가 자기가 도는 노드에서 오는 트래픽과 localhost는 막지 못한다(쿠버네티스 문서 「What you can't do」). 그래서 kubelet 프로브와 `kubectl port-forward`는 정책 밖이다.
- **확인 범위**: 위의 FastMCP HTTP 동작만 스크래치에서 실제로 돌렸다. 나머지 코드는 이 plan의 TDD 단계에서 처음 돈다 — 단계의 기대 출력과 다르면 멈추고 원인을 본다.
- **구현 중 바뀐 것(2026-11-18)**: Task 2~4의 코드 품질 리뷰를 반영해(커밋 `e2e02df`) MCP 서버 코드가 아래 Task 2~4의 코드 블록과 다르다 — in-cluster 토큰을 시작할 때 확인(`check_in_cluster`, 실패하면 종료 코드 2), 바인드 주소 `HOA_MCP_HOST`(기본 `127.0.0.1`), `ServerSettings.kube_auth`, 401 안내를 인증 방식별로, 포트 검사 `isdecimal`, 테스트 보강(`tests/test_main.py` 등). Task 11의 MCP 차트는 `HOA_MCP_HOST=0.0.0.0`을 준다. 같은 원칙으로 `hoa serve --host`의 기본값도 `127.0.0.1`이고 Task 12의 에이전트 차트가 `--host 0.0.0.0`을 준다(Task 8·12에 반영). 교본은 실제 파일을 싣는다.

**선행 완료:** 작업 브랜치 `feat/round02a-helm-charts`(`dev` `72a050a`에서 분기, spec 커밋 `d4454f5`, 승인 표시 `5c010b4`, push됨). 개발 PC에 Docker Desktop·kind v0.33.0·kubectl·uv가 있다. 저장소 루트의 `.env`(커밋 안 함)에 `HOA_GEMMA_BASE_URL`·`GEMINI_API_KEY`가 있다. **호스트 helm은 아직 없다 — Task 1에서 사용자가 설치한다.**

모든 Task는 이 브랜치에서 한다. 명령은 Git Bash 기준이고 작업 디렉터리는 저장소 루트다. 코드 블록의 줄바꿈이 ruff와 다르면 `ruff format --check`가 실패한다 — 그때는 `uv run ruff format <경로>`로 맞추고 다시 확인한다(내용은 바꾸지 않는다). Python 명령은 `uv run`으로, LLM을 부르는 명령은 `uv run --env-file .env`로 실행한다. 쿠버네티스 명령은 컨텍스트 `kind-hoa`를 명시한다(`kubectl --context kind-hoa`, `helm --kube-context kind-hoa`).

**커밋 규칙:** `[Type] 한국어 설명` 한 줄. `Co-Authored-By` 트레일러와 "Generated with" 문구는 넣지 않는다(단독 저자). 일반 push는 묻지 않고 하되, 표시한 곳(Task 1·17·18·20·21·22와 머지 Task)에서 한다.

**공개 저장소 규칙:** `.env`의 값, 회사 서버의 주소·호스트명·컨테이너·네트워크 이름은 코드·문서·커밋 메시지·교본 어디에도 쓰지 않는다. 클러스터 안 LLM Secret의 값은 화면에도 출력하지 않는다(키 이름만 본다).

---

## 파일 구조

| 파일 | 책임 |
|---|---|
| `deploy/docker/Dockerfile`·`Dockerfile.dockerignore` | 워크스페이스 멤버 하나를 담는 이미지(`ARG PACKAGE`·`ARG MEMBER`) — 데모 앱·MCP·에이전트 공용 |
| `deploy/helm/demo-app/` | 진단 대상 3서비스의 Deployment·Service(서비스 목록을 values로) |
| `deploy/helm/mcp-k8s-read/` | MCP 서버 Deployment·Service, ServiceAccount, ClusterRole + 대상 네임스페이스 RoleBinding, NetworkPolicy(에이전트만) |
| `deploy/helm/agent/` | 에이전트 API Deployment·Service, NetworkPolicy(인그레스 없음), 기존 Secret 참조 |
| `deploy/values/kind/{demo-app,mcp-k8s-read,agent}.yaml` | 로컬 티어 값 — 이미지 이름·태그, LLM Secret 이름 |
| `deploy/kind/namespaces.yaml` | `demo`·`hoa-system`(restricted 파드 보안 표준) — 차트는 네임스페이스를 만들지 않는다 |
| `deploy/tests/test_charts.py` | 차트 정책 테스트(마커 `charts`) — 렌더 결과를 코딩 표준에 비춰 본다 |
| `mcp_servers/src/hoa_mcp/k8s_read/settings.py` | 전송(stdio·http)·인증(kubeconfig·in-cluster)·포트·허용 Host |
| `mcp_servers/src/hoa_mcp/k8s_read/kube.py` | `ApiKubeReader(None)` = in-cluster 인증 |
| `mcp_servers/src/hoa_mcp/k8s_read/server.py` | HTTP 설정(상태 없음·JSON·허용 Host)·`/healthz`·전송 선택 |
| `agent/src/hoa_agent/failures.py` | 실패 분류 — CLI 종료 코드와 API 상태 코드, 운영자용·공개용 메시지 |
| `agent/src/hoa_agent/api.py` | FastAPI 앱 팩토리 — `POST /investigations`(동시 1건·제한 시간)·`GET /healthz` |
| `agent/src/hoa_agent/cli.py` | `hoa investigate`(분류를 `failures.py`로), `hoa serve` |
| `agent/src/hoa_agent/mcp_tools.py` | `HOA_MCP_URL`이 있으면 streamable HTTP 연결 |
| `agent/src/hoa_agent/investigate.py` | 세션 밖까지 온 `httpx.HTTPError`도 MCP 설정 오류로 |
| `agent/tests/integration/fake_llm.py` | 통합 테스트용 가짜 OpenAI 호환 서버(표준 라이브러리만) |
| `agent/tests/integration/test_agent_api_kind.py` | 에이전트 파드 → 가짜 LLM → MCP 파드 끝-끝, NetworkPolicy, CLI의 HTTP 연결 |
| `mcp_servers/tests/integration/test_in_cluster.py` | 클러스터 안 MCP 서버(포트포워드), Host 검사, ServiceAccount 권한 |
| `scripts/dev-cluster.sh` | 이미지 셋 빌드·LLM Secret·helm 설치·복구 |
| `eval/src/hoa_eval/cluster.py` | `Helm`(컨텍스트 명시)·`baseline_release()`·helm으로 복구 |
| `.github/workflows/ci.yml` | 차트 잡(helm lint·kubeconform·정책 테스트), 통합 잡에 helm |
| 지우는 것 | `demo_app/Dockerfile`·`demo_app/Dockerfile.dockerignore`, `deploy/kind/demo/`, `deploy/kind/rbac/` |

---

### Task 1: 준비 — spec 보정과 호스트 helm

**Files:**
- Modify: `docs/superpowers/specs/2026-11-17-round02a-helm-charts-design.md`

- [ ] **Step 1: spec 보정 — 버전과 helm 복구 방식**

§4의 helm·kubeconform 두 줄을 바꾼다.

전:
```markdown
- **helm**: 개발 PC 호스트에 설치한다. kind와 통합 테스트는 호스트에서 돈다 — devcontainer 안에서는 kind API 주소에 닿지 않는다(`GIT_WORKFLOW.md` §개발 환경). 같은 버전을 devcontainer 기능 옵션, CI 다운로드 URL, 문서에 고정한다(버전은 plan에서 정한다).
- **kubeconform**: CI에만 둔다. 버전을 다운로드 URL에 고정한다.
```
후:
```markdown
- **helm**: 개발 PC 호스트에 설치한다. kind와 통합 테스트는 호스트에서 돈다 — devcontainer 안에서는 kind API 주소에 닿지 않는다(`GIT_WORKFLOW.md` §개발 환경). 같은 버전(v4.3.2)을 devcontainer 기능 옵션, CI 다운로드 URL·체크섬, `scripts/dev-cluster.sh`, 문서에 고정한다. Helm 4는 새 릴리스를 server-side apply로 올린다(§5.5).
- **kubeconform**: CI에만 둔다. 버전(v0.8.0)과 체크섬을 다운로드 단계에 고정하고, 스키마는 쿠버네티스 v1.37.0(kind 노드와 같다)으로 본다.
```

§5.5의 「helm이 장애를 되돌리는지」 항목을 바꾼다.

전:
```markdown
- **helm이 장애를 되돌리는지**: 장애 패치는 이미지 태그·환경변수 값처럼 차트에 이미 있는 필드만 바꾼다(지금 규칙). helm upgrade가 그 필드를 차트 값으로 되돌리는지는 helm 버전과 적용 방식(3-way merge / server-side apply)에 따라 다를 수 있다. plan에서 고정한 버전으로 확인하고, 그 뒤로는 CI의 「스크립트 장애 주입·복구」 단계가 계속 증명한다.
```
후:
```markdown
- **helm이 장애를 되돌리는 방법**: Helm 4는 새 릴리스를 server-side apply로 올린다. `kubectl patch`(장애 주입)는 바꾼 필드의 소유자를 가져가므로, 기준 상태로 되돌리는 `helm upgrade`는 그 필드에서 충돌한다. 그래서 설치·복구 명령은 모두 `--server-side=true --force-conflicts`를 줘서 차트 값으로 그 필드를 되찾는다(plan 작성 중 helm v4.3.2 소스로 확인, 구현 때 실제로 확인). 장애 패치는 지금처럼 차트에 이미 있는 필드(이미지 태그·환경변수 값)만 바꾼다. CI의 「스크립트 장애 주입·복구」 단계가 계속 증명한다.
```

§8 표의 세 행을 바꾼다.

전:
```markdown
| helm 버전에 따라 upgrade가 장애 패치를 되돌리지 않는다(3-way merge와 server-side apply의 차이) | plan에서 고정 버전으로 확인한다. 안 되면 복구를 「장애 패치를 거꾸로 적용」이나 `--force` 같은 방식으로 바꾸고 이유를 남긴다. CI 주입·복구 단계가 계속 지킨다 |
| kind 기본 CNI가 NetworkPolicy를 지키지 않는다 | plan에서 확인한다. 안 지키면 그 통합 확인을 빼고 완료노트에 적은 뒤, k3s(02b)에서 확인한다. 정책 객체 자체는 차트 정책 테스트가 지킨다 |
| kubeconform 스키마 저장소가 쿠버네티스 1.37을 아직 내지 않았다 | plan에서 확인한다. 없으면 가장 가까운 버전으로 고정하고 이유를 남긴다 |
```
후:
```markdown
| 장애 패치가 가져간 필드를 helm upgrade가 되찾지 못한다 | `--server-side=true --force-conflicts`(§5.5). 그래도 안 되면 복구를 「장애 패치를 거꾸로 적용」으로 바꾸고 이유를 남긴다. CI 주입·복구 단계가 계속 지킨다 |
| kind 기본 CNI가 NetworkPolicy를 지키지 않는다 | kind v0.24부터 기본 CNI(kindnet)가 NetworkPolicy를 지킨다(릴리스 노트, 2026-11-17 확인). 통합 테스트가 막히는지 직접 본다. 안 지키면 그 확인을 빼고 완료노트에 적은 뒤 k3s(02b)에서 확인한다. 정책 객체 자체는 차트 정책 테스트가 지킨다 |
| kubeconform 스키마가 쿠버네티스 1.37과 맞지 않는다 | 스키마 저장소에 v1.37.0이 있다(2026-11-17 확인). kind 노드를 올릴 때 `-kubernetes-version`을 같이 올린다 |
```

- [ ] **Step 2: 커밋·push**

```bash
git add docs/superpowers/specs/2026-11-17-round02a-helm-charts-design.md
git commit -m "[Docs] round02a spec 보정 — helm v4.3.2 server-side apply 복구 방식, 버전 확인 결과"
git push
```

- [ ] **Step 3: 호스트 helm 설치(사용자)**

파일을 내려받는 일이라 사용자에게 맡긴다. Windows 개발 PC에서 다음 중 하나로 설치해 달라고 요청하고 끝날 때까지 기다린다.
- 공식 zip: `https://get.helm.sh/helm-v4.3.2-windows-amd64.zip`을 받아 SHA-256이 `77c5c782aaef1abbfafe75b88412d2b6df8e4a36d14522273397f0d02c6ecc29`인지 보고, 안의 `helm.exe`를 PATH에 있는 폴더(예: `%USERPROFILE%\bin`)에 둔다.
- 또는 `winget install --id Helm.Helm --version 4.3.2 --exact`(그 버전이 winget에 있을 때).

Run: `helm version --template '{{.Version}}'; echo`
Expected: `v4.3.2`

---

### Task 2: MCP 설정 — 전송·인증·포트·허용 Host (TDD)

**Files:**
- Modify: `mcp_servers/src/hoa_mcp/k8s_read/settings.py`
- Test: `mcp_servers/tests/test_settings.py`

- [ ] **Step 1: 실패하는 테스트**

`mcp_servers/tests/test_settings.py`의 import를 바꾸고 파일 끝에 테스트를 더한다.

import 전:
```python
from hoa_mcp.k8s_read.settings import SettingsError, load_settings
```
import 후:
```python
from hoa_mcp.k8s_read.settings import KubeAuth, SettingsError, Transport, load_settings
```

파일 끝에 더한다:
```python
def test_defaults_are_stdio_with_a_kubeconfig(tmp_path: Path, kubeconfig_text: str) -> None:
    kubeconfig = write_kubeconfig(tmp_path, kubeconfig_text)
    settings = load_settings({"HOA_MCP_KUBECONFIG": str(kubeconfig)})
    assert settings.transport is Transport.STDIO
    assert settings.port == 8080
    assert settings.allowed_hosts == ()


def test_http_transport_reads_port_and_allowed_hosts(tmp_path: Path, kubeconfig_text: str) -> None:
    kubeconfig = write_kubeconfig(tmp_path, kubeconfig_text)
    settings = load_settings(
        {
            "HOA_MCP_KUBECONFIG": str(kubeconfig),
            "HOA_MCP_TRANSPORT": "http",
            "HOA_MCP_PORT": "9000",
            "HOA_MCP_ALLOWED_HOSTS": "hoa-mcp-k8s-read.hoa-system.svc, 127.0.0.1:*",
        }
    )
    assert settings.transport is Transport.HTTP
    assert settings.port == 9000
    assert settings.allowed_hosts == ("hoa-mcp-k8s-read.hoa-system.svc", "127.0.0.1:*")


def test_http_transport_without_allowed_hosts_is_refused(
    tmp_path: Path, kubeconfig_text: str
) -> None:
    kubeconfig = write_kubeconfig(tmp_path, kubeconfig_text)
    with pytest.raises(SettingsError, match="HOA_MCP_ALLOWED_HOSTS is required"):
        load_settings({"HOA_MCP_KUBECONFIG": str(kubeconfig), "HOA_MCP_TRANSPORT": "http"})


@pytest.mark.parametrize(
    ("name", "value", "message"),
    [
        ("HOA_MCP_TRANSPORT", "sse", "HOA_MCP_TRANSPORT must be one of stdio, http"),
        ("HOA_MCP_KUBE_AUTH", "token", "HOA_MCP_KUBE_AUTH must be one of kubeconfig, in-cluster"),
        ("HOA_MCP_PORT", "eighty", "HOA_MCP_PORT must be a port number"),
        ("HOA_MCP_PORT", "70000", "HOA_MCP_PORT must be a port number"),
    ],
)
def test_bad_choices_are_refused(
    tmp_path: Path, kubeconfig_text: str, name: str, value: str, message: str
) -> None:
    kubeconfig = write_kubeconfig(tmp_path, kubeconfig_text)
    with pytest.raises(SettingsError, match=message):
        load_settings({"HOA_MCP_KUBECONFIG": str(kubeconfig), name: value})


def test_in_cluster_auth_needs_no_kubeconfig() -> None:
    settings = load_settings(
        {"HOA_MCP_KUBE_AUTH": "in-cluster", "KUBERNETES_SERVICE_HOST": "kubernetes.default.svc"}
    )
    assert settings.kubeconfig is None
    assert KubeAuth.IN_CLUSTER.value == "in-cluster"


def test_in_cluster_auth_with_a_kubeconfig_is_refused(tmp_path: Path, kubeconfig_text: str) -> None:
    kubeconfig = write_kubeconfig(tmp_path, kubeconfig_text)
    with pytest.raises(SettingsError, match="must be empty with HOA_MCP_KUBE_AUTH=in-cluster"):
        load_settings(
            {
                "HOA_MCP_KUBE_AUTH": "in-cluster",
                "HOA_MCP_KUBECONFIG": str(kubeconfig),
                "KUBERNETES_SERVICE_HOST": "kubernetes.default.svc",
            }
        )


def test_in_cluster_auth_outside_a_pod_is_refused() -> None:
    with pytest.raises(SettingsError, match="only works inside a pod"):
        load_settings({"HOA_MCP_KUBE_AUTH": "in-cluster"})
```

- [ ] **Step 2: 실패 확인**

Run: `uv run pytest mcp_servers/tests/test_settings.py -q`
Expected: FAIL — `ImportError: cannot import name 'KubeAuth'`

- [ ] **Step 3: 구현**

`mcp_servers/src/hoa_mcp/k8s_read/settings.py` 전체:
```python
from collections.abc import Mapping
from enum import StrEnum
from pathlib import Path

import yaml
from pydantic import BaseModel

DEFAULT_PORT = 8080


class SettingsError(Exception):
    pass


class Transport(StrEnum):
    STDIO = "stdio"
    HTTP = "http"


class KubeAuth(StrEnum):
    KUBECONFIG = "kubeconfig"
    IN_CLUSTER = "in-cluster"


class ServerSettings(BaseModel):
    # None이면 파드의 ServiceAccount 토큰으로 붙는다(in-cluster)
    kubeconfig: Path | None
    allowed_namespaces: tuple[str, ...]
    transport: Transport = Transport.STDIO
    port: int = DEFAULT_PORT
    allowed_hosts: tuple[str, ...] = ()


def context_count(kubeconfig: Path) -> int:
    try:
        data = yaml.safe_load(kubeconfig.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise SettingsError("HOA_MCP_KUBECONFIG is not valid YAML") from exc
    contexts = data.get("contexts") if isinstance(data, dict) else None
    return len(contexts) if isinstance(contexts, list) else 0


def choice[E: StrEnum](env: Mapping[str, str], name: str, kind: type[E], default: E) -> E:
    raw = env.get(name, "").strip() or default.value
    try:
        return kind(raw)
    except ValueError as exc:
        choices = ", ".join(member.value for member in kind)
        raise SettingsError(f"{name} must be one of {choices}, got {raw!r}") from exc


def split_list(raw: str) -> tuple[str, ...]:
    return tuple(item.strip() for item in raw.split(",") if item.strip())


def kubeconfig_path(env: Mapping[str, str], auth: KubeAuth) -> Path | None:
    raw = env.get("HOA_MCP_KUBECONFIG", "").strip()
    if auth is KubeAuth.IN_CLUSTER:
        if raw:
            raise SettingsError(
                "HOA_MCP_KUBECONFIG must be empty with HOA_MCP_KUBE_AUTH=in-cluster — "
                "pick one way to reach the cluster"
            )
        if not env.get("KUBERNETES_SERVICE_HOST", "").strip():
            raise SettingsError(
                "HOA_MCP_KUBE_AUTH=in-cluster only works inside a pod "
                "(KUBERNETES_SERVICE_HOST is not set)"
            )
        return None
    if not raw:
        raise SettingsError("HOA_MCP_KUBECONFIG is not set")
    kubeconfig = Path(raw).expanduser()
    if not kubeconfig.is_file():
        raise SettingsError(f"HOA_MCP_KUBECONFIG file not found: {kubeconfig}")
    # 컨텍스트가 여럿인 관리자 kubeconfig를 가리키면 엉뚱한 클러스터에 관리자 권한으로 붙는다
    contexts = context_count(kubeconfig)
    if contexts != 1:
        raise SettingsError(
            f"HOA_MCP_KUBECONFIG must hold exactly one context, found {contexts} — "
            "use the read-only kubeconfig written by scripts/dev-cluster.sh"
        )
    return kubeconfig


def port_number(env: Mapping[str, str]) -> int:
    raw = env.get("HOA_MCP_PORT", "").strip() or str(DEFAULT_PORT)
    if not raw.isdigit() or not 1 <= int(raw) <= 65535:
        raise SettingsError(f"HOA_MCP_PORT must be a port number, got {raw!r}")
    return int(raw)


def load_settings(env: Mapping[str, str]) -> ServerSettings:
    auth = choice(env, "HOA_MCP_KUBE_AUTH", KubeAuth, KubeAuth.KUBECONFIG)
    transport = choice(env, "HOA_MCP_TRANSPORT", Transport, Transport.STDIO)
    kubeconfig = kubeconfig_path(env, auth)
    namespaces = split_list(env.get("HOA_MCP_ALLOWED_NAMESPACES", "demo"))
    if not namespaces:
        raise SettingsError("HOA_MCP_ALLOWED_NAMESPACES is empty")
    hosts = split_list(env.get("HOA_MCP_ALLOWED_HOSTS", ""))
    # 허용 Host가 비면 HTTP 요청이 모두 421로 거절된다 — 시작할 때 알린다
    if transport is Transport.HTTP and not hosts:
        raise SettingsError("HOA_MCP_ALLOWED_HOSTS is required with HOA_MCP_TRANSPORT=http")
    return ServerSettings(
        kubeconfig=kubeconfig,
        allowed_namespaces=namespaces,
        transport=transport,
        port=port_number(env),
        allowed_hosts=hosts,
    )
```

- [ ] **Step 4: 통과 확인**

Run: `uv run pytest mcp_servers/tests/test_settings.py -q`
Expected: PASS(기존 7 + 새 10)

Run: `uv run pytest mcp_servers -q && uv run ruff check mcp_servers && uv run ruff format --check mcp_servers`
Expected: 모두 통과 — 기존 테스트는 `ServerSettings(kubeconfig=…, allowed_namespaces=…)`로 만들어 새 필드의 기본값을 쓴다.

- [ ] **Step 5: 커밋**

```bash
git add mcp_servers/src/hoa_mcp/k8s_read/settings.py mcp_servers/tests/test_settings.py
git commit -m "[Feat] MCP 설정 — 전송(stdio·http)·인증(kubeconfig·in-cluster)·포트·허용 Host"
```

---

### Task 3: MCP 쿠버네티스 클라이언트 — in-cluster 인증 (TDD)

**Files:**
- Modify: `mcp_servers/src/hoa_mcp/k8s_read/kube.py`
- Test: `mcp_servers/tests/test_kube.py`

- [ ] **Step 1: 실패하는 테스트**

`mcp_servers/tests/test_kube.py` 끝에 더한다(파일은 이미 `kube`·`ApiClient`·`ApiKubeReader`·`KubeError`·`pytest`를 import한다):
```python
@pytest.mark.anyio
async def test_in_cluster_reader_loads_the_pod_token_on_every_call(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    loads: list[kube.client.Configuration] = []

    def fake_load(client_configuration: kube.client.Configuration) -> None:
        loads.append(client_configuration)
        client_configuration.host = "https://kubernetes.default.svc"

    monkeypatch.setattr(kube.config, "load_incluster_config", fake_load)

    async def host(api: ApiClient) -> str:
        return api.configuration.host

    reader = ApiKubeReader(None)
    assert await reader._call(host) == "https://kubernetes.default.svc"
    assert await reader._call(host) == "https://kubernetes.default.svc"
    # 호출마다 토큰 파일을 다시 읽는다 — 투영된 ServiceAccount 토큰은 주기적으로 바뀐다
    assert len(loads) == 2


@pytest.mark.anyio
async def test_in_cluster_reader_outside_a_pod_is_a_kube_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("KUBERNETES_SERVICE_HOST", raising=False)
    monkeypatch.delenv("KUBERNETES_SERVICE_PORT", raising=False)

    async def never(api: ApiClient) -> None:
        raise AssertionError("must not be called")

    with pytest.raises(KubeError, match="in-cluster service account could not be loaded"):
        await ApiKubeReader(None)._call(never)
```

- [ ] **Step 2: 실패 확인**

Run: `uv run pytest mcp_servers/tests/test_kube.py -q`
Expected: FAIL — 두 테스트가 `kubeconfig could not be loaded` 또는 `TypeError`(`str(None)`을 kubeconfig로 읽으려다 실패)로 깨진다.

- [ ] **Step 3: 구현**

`mcp_servers/src/hoa_mcp/k8s_read/kube.py`에서 `ApiKubeReader`의 `__init__`과 `_call` 앞부분을 바꾼다.

전:
```python
class ApiKubeReader:
    def __init__(self, kubeconfig: Path) -> None:
        self._kubeconfig = kubeconfig

    async def _call[T](self, request: Callable[[ApiClient], Awaitable[T]]) -> T:
        try:
            api = await config.new_client_from_config(
                config_file=str(self._kubeconfig), persist_config=False
            )
        except (ConfigException, OSError) as exc:
            raise KubeError(0, "kubeconfig could not be loaded") from exc
```
후:
```python
class ApiKubeReader:
    """kubeconfig가 None이면 파드의 ServiceAccount 토큰(in-cluster)으로 붙는다."""

    def __init__(self, kubeconfig: Path | None) -> None:
        self._kubeconfig = kubeconfig

    async def _client(self) -> ApiClient:
        if self._kubeconfig is None:
            # 호출마다 토큰 파일을 다시 읽는다 — 투영된 토큰은 주기적으로 바뀐다
            configuration = client.Configuration()
            config.load_incluster_config(client_configuration=configuration)
            return ApiClient(configuration)
        return await config.new_client_from_config(
            config_file=str(self._kubeconfig), persist_config=False
        )

    async def _call[T](self, request: Callable[[ApiClient], Awaitable[T]]) -> T:
        try:
            api = await self._client()
        except (ConfigException, OSError) as exc:
            source = "in-cluster service account" if self._kubeconfig is None else "kubeconfig"
            raise KubeError(0, f"{source} could not be loaded") from exc
```
나머지(`try: async with asyncio.timeout(...)` 이하)는 그대로 둔다.

- [ ] **Step 4: 통과 확인**

Run: `uv run pytest mcp_servers -q && uv run ruff check mcp_servers && uv run ruff format --check mcp_servers`
Expected: 모두 통과

- [ ] **Step 5: 커밋**

```bash
git add mcp_servers/src/hoa_mcp/k8s_read/kube.py mcp_servers/tests/test_kube.py
git commit -m "[Feat] MCP 쿠버네티스 클라이언트 — 파드 ServiceAccount 토큰(in-cluster) 인증"
```

---

### Task 4: MCP HTTP 서버 — 상태 없는 streamable HTTP·허용 Host·`/healthz` (TDD)

**Files:**
- Modify: `mcp_servers/src/hoa_mcp/k8s_read/server.py`
- Create: `mcp_servers/tests/test_http.py`
- Modify: `mcp_servers/tests/test_entrypoint.py`

- [ ] **Step 1: 실패하는 테스트**

`mcp_servers/tests/test_http.py`:
```python
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager

import httpx
import pytest
from kubernetes_asyncio.client import V1Pod
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client
from mcp.server.fastmcp import FastMCP

from hoa_mcp.k8s_read.server import build_server
from hoa_mcp.k8s_read.settings import ServerSettings, Transport

pytestmark = pytest.mark.anyio

SERVICE_HOST = "hoa-mcp-k8s-read.hoa-system.svc"
TOOLS_LIST = {"jsonrpc": "2.0", "id": 1, "method": "tools/list"}
MCP_ACCEPT = {"accept": "application/json, text/event-stream"}


class PodsReader:
    """list_pods만 답한다 — 이 테스트는 전송 계층을 본다."""

    def __init__(self, pods: list[V1Pod]) -> None:
        self.pods = pods

    async def list_pods(self, namespace: str) -> list[V1Pod]:
        return self.pods


def http_server(pods: list[V1Pod]) -> FastMCP:
    settings = ServerSettings(
        kubeconfig=None,
        allowed_namespaces=("demo",),
        transport=Transport.HTTP,
        allowed_hosts=(SERVICE_HOST, "127.0.0.1:*"),
    )
    return build_server(PodsReader(pods), settings)


@asynccontextmanager
async def http_client(server: FastMCP, host: str) -> AsyncIterator[httpx.AsyncClient]:
    app = server.streamable_http_app()
    async with (
        server.session_manager.run(),
        httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url=f"http://{host}"
        ) as client,
    ):
        yield client


async def test_tools_answer_over_streamable_http(make_pod: Callable[..., V1Pod]) -> None:
    server = http_server([make_pod("orders-7d9f-abcde")])
    async with (
        http_client(server, SERVICE_HOST) as client,
        streamable_http_client(f"http://{SERVICE_HOST}/mcp", http_client=client) as (
            read,
            write,
            _,
        ),
        ClientSession(read, write) as session,
    ):
        await session.initialize()
        result = await session.call_tool("list_pods", {"namespace": "demo"})
    assert result.isError is False
    assert result.structuredContent["pods"][0]["name"] == "orders-7d9f-abcde"


async def test_unknown_host_header_is_refused() -> None:
    async with http_client(http_server([]), "evil.example") as client:
        response = await client.post("/mcp", json=TOOLS_LIST, headers=MCP_ACCEPT)
    assert response.status_code == 421


async def test_port_forwarded_host_is_allowed() -> None:
    async with http_client(http_server([]), "127.0.0.1:18080") as client:
        response = await client.post("/mcp", json=TOOLS_LIST, headers=MCP_ACCEPT)
    assert response.status_code == 200
    names = {tool["name"] for tool in response.json()["result"]["tools"]}
    assert names == {"list_pods", "get_events", "describe_deployment", "get_pod_logs"}


async def test_health_check_answers_without_touching_the_cluster() -> None:
    async with http_client(http_server([]), "10-244-0-7.pod") as client:
        response = await client.get("/healthz")
    assert response.status_code == 200
    assert response.text == "ok"
```

`mcp_servers/tests/test_entrypoint.py` 끝에 더한다:
```python
def test_http_entrypoint_without_allowed_hosts_exits_2(
    tmp_path: Path, kubeconfig_text: str
) -> None:
    kubeconfig = tmp_path / "read.kubeconfig"
    kubeconfig.write_text(kubeconfig_text, encoding="utf-8")
    env = {
        **{k: v for k, v in os.environ.items() if k != "HOA_MCP_ALLOWED_HOSTS"},
        "HOA_MCP_KUBECONFIG": str(kubeconfig),
        "HOA_MCP_TRANSPORT": "http",
    }
    result = subprocess.run([entrypoint()], env=env, capture_output=True, text=True, timeout=60)
    assert result.returncode == 2
    assert "HOA_MCP_ALLOWED_HOSTS is required" in result.stderr
```

- [ ] **Step 2: 실패 확인**

Run: `uv run pytest mcp_servers/tests/test_http.py mcp_servers/tests/test_entrypoint.py -q`
Expected: FAIL — 지금 서버는 기본 host(127.0.0.1)라 FastMCP가 localhost만 허용한다. 그래서 `test_tools_answer_over_streamable_http`(Service 이름 Host가 421)와 `test_health_check_answers_without_touching_the_cluster`(`/healthz` 404)가 깨진다. 나머지 둘과 엔트리포인트 테스트는 이미 통과할 수 있다(허용 Host 검사는 Task 2에서 들어갔다).

- [ ] **Step 3: 구현**

`mcp_servers/src/hoa_mcp/k8s_read/server.py`에서 import 두 줄을 더하고 바꾼다.

전:
```python
from mcp.server.fastmcp import FastMCP
from mcp.server.fastmcp.exceptions import ToolError
from mcp.types import ToolAnnotations
from pydantic import Field
```
후:
```python
from mcp.server.fastmcp import FastMCP
from mcp.server.fastmcp.exceptions import ToolError
from mcp.server.transport_security import TransportSecuritySettings
from mcp.types import ToolAnnotations
from pydantic import Field
from starlette.requests import Request
from starlette.responses import PlainTextResponse
```

전:
```python
from hoa_mcp.k8s_read.settings import ServerSettings, SettingsError, load_settings
```
후:
```python
from hoa_mcp.k8s_read.settings import ServerSettings, SettingsError, Transport, load_settings
```

`build_server` 첫 부분을 바꾼다.

전:
```python
def build_server(reader: KubeReader, settings: ServerSettings) -> FastMCP:
    # 요청마다 남는 INFO 줄이 hoa investigate의 표준오류를 덮지 않게 경고 이상만 남긴다
    server = FastMCP("hoa-k8s-read", instructions=INSTRUCTIONS, log_level="WARNING")
```
후:
```python
def build_server(reader: KubeReader, settings: ServerSettings) -> FastMCP:
    server = FastMCP(
        "hoa-k8s-read",
        instructions=INSTRUCTIONS,
        # 요청마다 남는 INFO 줄이 hoa investigate의 표준오류를 덮지 않게 경고 이상만 남긴다
        log_level="WARNING",
        # 아래는 HTTP 전송(클러스터 안 파드)에서만 쓰인다
        host="0.0.0.0",
        port=settings.port,
        # 에이전트가 조사마다 연결을 열고 닫는다 — 세션을 쥐지 않아 복제본을 늘려도 된다
        stateless_http=True,
        json_response=True,
        # 0.0.0.0에 묶으면 FastMCP가 Host 검사(DNS 리바인딩 방어)를 저절로 켜지 않는다
        transport_security=TransportSecuritySettings(
            allowed_hosts=list(settings.allowed_hosts), allowed_origins=[]
        ),
    )

    @server.custom_route("/healthz", methods=["GET"])
    async def healthz(request: Request) -> PlainTextResponse:
        """프로브용 — 쿠버네티스 API를 부르지 않는다(kubelet 프로브의 Host는 파드 IP다)."""
        return PlainTextResponse("ok")
```

`main`의 마지막 줄을 바꾼다.

전:
```python
    build_server(ApiKubeReader(settings.kubeconfig), settings).run("stdio")
```
후:
```python
    server = build_server(ApiKubeReader(settings.kubeconfig), settings)
    server.run("streamable-http" if settings.transport is Transport.HTTP else "stdio")
```

- [ ] **Step 4: 통과 확인**

Run: `uv run pytest mcp_servers -q && uv run ruff check mcp_servers && uv run ruff format --check mcp_servers`
Expected: 모두 통과. 허용 밖 Host 테스트는 서버 로그에 `Invalid Host header: evil.example` 경고 한 줄을 남긴다(경고 모듈이 아니라 로그라 `-W error`에 걸리지 않는다).

- [ ] **Step 5: 커밋**

```bash
git add mcp_servers/src/hoa_mcp/k8s_read/server.py mcp_servers/tests/test_http.py mcp_servers/tests/test_entrypoint.py
git commit -m "[Feat] MCP 서버 HTTP 전송 — 상태 없는 streamable HTTP·허용 Host·/healthz"
```

---

### Task 5: 에이전트 실패 분류 — CLI와 API가 함께 쓰는 한 곳 (TDD)

**Files:**
- Create: `agent/src/hoa_agent/failures.py`
- Modify: `agent/src/hoa_agent/cli.py`
- Modify: `agent/tests/conftest.py`
- Modify: `agent/tests/test_cli.py`
- Test: `agent/tests/test_failures.py`

- [ ] **Step 1: 공용 픽스처를 conftest로 옮긴다**

`agent/tests/test_cli.py`의 `result` 픽스처는 API 테스트(Task 7)도 쓴다. conftest로 옮기고, 요청 한도 오류도 픽스처로 둔다.

`agent/tests/conftest.py`의 import 블록에 다음을 알파벳 순서에 맞춰 더한다(서드파티 블록에 `httpx`·`openai`, 프로젝트 블록에 `hoa_agent.result`):
```python
import httpx
import openai
```
```python
from hoa_agent.result import InvestigationResult, ToolStep, Usage
```

`agent/tests/conftest.py` 끝에 더한다:
```python
@pytest.fixture
def result(diagnosis: Diagnosis) -> InvestigationResult:
    return InvestigationResult(
        model="gemini-3.5-flash",
        alert="orders rollout stuck",
        diagnosis=diagnosis,
        stop_reason="answered",
        steps=[
            ToolStep(tool="list_pods", args={}, output="{}", error=False, executed=True),
            ToolStep(tool="get_events", args={}, output="Not run", error=True, executed=False),
        ],
        invalid_tool_calls=0,
        usage=Usage(model_calls=2, input_tokens=1_500, output_tokens=200, total_tokens=1_700),
        elapsed_seconds=4.2,
    )


@pytest.fixture
def rate_limit_error() -> openai.RateLimitError:
    request = httpx.Request("POST", "https://llm.test/v1/chat/completions")
    response = httpx.Response(429, request=request)
    return openai.RateLimitError("quota exceeded", response=response, body=None)
```

`agent/tests/test_cli.py`에서 `result` 픽스처 정의(`@pytest.fixture` 줄부터 `elapsed_seconds=4.2,` 다음의 `    )`까지)를 지우고, 쓰지 않게 된 import를 정리한다.

전:
```python
from hoa_agent.diagnosis import Diagnosis
from hoa_agent.graph import DiagnosisSchemaError
from hoa_agent.llm import LLMConfigError
from hoa_agent.mcp_tools import MCPSetupError
from hoa_agent.result import InvestigationResult, ToolStep, Usage
```
후:
```python
from hoa_agent.graph import DiagnosisSchemaError
from hoa_agent.llm import LLMConfigError
from hoa_agent.mcp_tools import MCPSetupError
from hoa_agent.result import InvestigationResult
```

Run: `uv run pytest agent -q && uv run ruff check agent`
Expected: 통과(테스트 수는 그대로) — 옮기기만 했다.

- [ ] **Step 2: 실패하는 테스트**

`agent/tests/test_failures.py`:
```python
import httpx
import openai
import pytest

from hoa_agent.failures import (
    EXIT_CODES,
    HTTP_STATUSES,
    FailureKind,
    classify,
    operator_message,
    public_message,
)
from hoa_agent.graph import DiagnosisSchemaError
from hoa_agent.llm import LLMConfigError
from hoa_agent.mcp_tools import MCPSetupError


def connection_error() -> openai.APIConnectionError:
    request = httpx.Request("POST", "http://vllm.internal:8000/v1/chat/completions")
    return openai.APIConnectionError(
        message="cannot reach http://vllm.internal:8000/v1", request=request
    )


@pytest.mark.parametrize(
    ("error", "kind", "code", "status"),
    [
        (LLMConfigError("HOA_GEMMA_BASE_URL is not set"), FailureKind.SETUP_ERROR, 2, 503),
        (MCPSetupError("the MCP server stopped"), FailureKind.SETUP_ERROR, 2, 503),
        (
            DiagnosisSchemaError("the model broke the diagnosis schema"),
            FailureKind.INVESTIGATION_FAILED,
            1,
            502,
        ),
        (connection_error(), FailureKind.INVESTIGATION_FAILED, 1, 502),
    ],
)
def test_each_failure_has_one_kind_exit_code_and_status(
    error: Exception, kind: FailureKind, code: int, status: int
) -> None:
    assert classify(error) is kind
    assert EXIT_CODES[kind] == code
    assert HTTP_STATUSES[kind] == status


def test_rate_limit_is_its_own_kind_before_other_openai_errors(
    rate_limit_error: openai.RateLimitError,
) -> None:
    kind = classify(rate_limit_error)
    assert kind is FailureKind.LLM_RATE_LIMITED
    assert (EXIT_CODES[kind], HTTP_STATUSES[kind]) == (3, 503)


def test_operator_message_keeps_the_original_text() -> None:
    error = connection_error()
    assert operator_message(classify(error), error) == (
        "investigation failed — APIConnectionError: cannot reach http://vllm.internal:8000/v1"
    )


def test_public_message_hides_upstream_error_text() -> None:
    error = connection_error()
    assert public_message(classify(error), error) == "investigation failed — APIConnectionError"


def test_public_message_keeps_our_own_setup_hints() -> None:
    error = LLMConfigError("HOA_GEMMA_BASE_URL is not set — put it in .env")
    assert public_message(classify(error), error) == str(error)


def test_public_rate_limit_message_drops_the_provider_text(
    rate_limit_error: openai.RateLimitError,
) -> None:
    message = public_message(classify(rate_limit_error), rate_limit_error)
    assert message == "the LLM rate limit was hit — retry later"
```

- [ ] **Step 3: 실패 확인**

Run: `uv run pytest agent/tests/test_failures.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'hoa_agent.failures'`

- [ ] **Step 4: 구현**

`agent/src/hoa_agent/failures.py`:
```python
from enum import StrEnum

import openai

from hoa_agent.graph import DiagnosisSchemaError
from hoa_agent.llm import LLMConfigError
from hoa_agent.mcp_tools import MCPSetupError

# 조사 함수가 낼 수 있는 실패 — CLI 종료 코드와 API 상태 코드가 같은 분류를 쓴다
KNOWN_FAILURES = (LLMConfigError, MCPSetupError, DiagnosisSchemaError, openai.OpenAIError)


class FailureKind(StrEnum):
    INVESTIGATION_FAILED = "investigation_failed"
    SETUP_ERROR = "setup_error"
    LLM_RATE_LIMITED = "llm_rate_limited"


EXIT_CODES = {
    FailureKind.INVESTIGATION_FAILED: 1,
    FailureKind.SETUP_ERROR: 2,
    FailureKind.LLM_RATE_LIMITED: 3,
}
HTTP_STATUSES = {
    FailureKind.INVESTIGATION_FAILED: 502,
    FailureKind.SETUP_ERROR: 503,
    FailureKind.LLM_RATE_LIMITED: 503,
}


def classify(exc: Exception) -> FailureKind:
    """KNOWN_FAILURES 하나를 분류한다 — 요청 한도는 OpenAIError의 하위라 먼저 본다."""
    if isinstance(exc, LLMConfigError | MCPSetupError):
        return FailureKind.SETUP_ERROR
    if isinstance(exc, openai.RateLimitError):
        return FailureKind.LLM_RATE_LIMITED
    return FailureKind.INVESTIGATION_FAILED


def operator_message(kind: FailureKind, exc: Exception) -> str:
    """운영자(CLI 표준오류)용 — 원문을 그대로 보인다."""
    if kind is FailureKind.SETUP_ERROR:
        return str(exc)
    if kind is FailureKind.LLM_RATE_LIMITED:
        return f"the LLM rate limit was hit — {exc}"
    return f"investigation failed — {type(exc).__name__}: {exc}"


def public_message(kind: FailureKind, exc: Exception) -> str:
    """API 응답용 — LLM·HTTP 오류 원문에는 내부 주소가 섞일 수 있다.
    우리가 쓴 설정 오류 문장만 그대로 보인다."""
    if kind is FailureKind.SETUP_ERROR:
        return str(exc)
    if kind is FailureKind.LLM_RATE_LIMITED:
        return "the LLM rate limit was hit — retry later"
    return f"investigation failed — {type(exc).__name__}"
```

`agent/src/hoa_agent/cli.py`에서 분류를 이 모듈로 옮긴다.

import 전:
```python
import openai

from hoa_agent import __version__
from hoa_agent.graph import DiagnosisSchemaError
from hoa_agent.investigate import run_investigation
from hoa_agent.llm import DEFAULT_MODEL, MODEL_NAMES, LLMConfigError
from hoa_agent.mcp_tools import MCPSetupError
from hoa_agent.result import InvestigationResult

Investigator = Callable[[str, str], Awaitable[InvestigationResult]]
# 평가 러너(hoa_eval.agent.RATE_LIMITED_EXIT)가 이 값으로 남은 회차를 멈춘다
RATE_LIMITED_EXIT = 3
```
import 후:
```python
from hoa_agent import __version__
from hoa_agent.failures import EXIT_CODES, KNOWN_FAILURES, FailureKind, classify, operator_message
from hoa_agent.investigate import run_investigation
from hoa_agent.llm import DEFAULT_MODEL, MODEL_NAMES
from hoa_agent.result import InvestigationResult

Investigator = Callable[[str, str], Awaitable[InvestigationResult]]
# 평가 러너(hoa_eval.agent.RATE_LIMITED_EXIT)가 이 값으로 남은 회차를 멈춘다
RATE_LIMITED_EXIT = EXIT_CODES[FailureKind.LLM_RATE_LIMITED]
```

`investigate_command` 전:
```python
    try:
        result = asyncio.run(investigator(args.alert, args.model))
    except (LLMConfigError, MCPSetupError) as exc:
        print(f"hoa: {exc}", file=sys.stderr)
        return 2
    except openai.RateLimitError as exc:
        print(f"hoa: the LLM rate limit was hit — {exc}", file=sys.stderr)
        return RATE_LIMITED_EXIT
    except (DiagnosisSchemaError, openai.OpenAIError) as exc:
        print(f"hoa: investigation failed — {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1
```
후:
```python
    try:
        result = asyncio.run(investigator(args.alert, args.model))
    except KNOWN_FAILURES as exc:
        kind = classify(exc)
        print(f"hoa: {operator_message(kind, exc)}", file=sys.stderr)
        return EXIT_CODES[kind]
```

- [ ] **Step 5: 통과 확인**

Run: `uv run pytest agent -q && uv run ruff check agent && uv run ruff format --check agent`
Expected: 모두 통과 — 기존 CLI 종료 코드 테스트(0·1·2·3과 메시지)가 그대로 맞는다.

- [ ] **Step 6: 커밋**

```bash
git add agent/src/hoa_agent/failures.py agent/src/hoa_agent/cli.py agent/tests/conftest.py agent/tests/test_cli.py agent/tests/test_failures.py
git commit -m "[Refactor] 에이전트 실패 분류를 한 곳으로 — CLI 종료 코드와 API 상태 코드"
```

---

### Task 6: 에이전트의 MCP HTTP 연결 (TDD)

**Files:**
- Modify: `agent/pyproject.toml`, `uv.lock`
- Modify: `agent/src/hoa_agent/mcp_tools.py`
- Modify: `agent/src/hoa_agent/investigate.py`
- Test: `agent/tests/test_mcp_tools.py`, `agent/tests/test_investigate.py`

- [ ] **Step 1: 의존성 — httpx를 직접 쓴다**

`agent/pyproject.toml`의 `dependencies`에 알파벳 순서로 한 줄 더한다(이미 잠금 파일에 있는 버전이다).

전:
```toml
dependencies = [
    "langchain-core>=1.8.1",
```
후:
```toml
dependencies = [
    "httpx>=0.28.1",
    "langchain-core>=1.8.1",
```

Run: `uv lock && uv sync`
Expected: 새 패키지 없이 잠금 파일의 `hoa-agent` 의존성 목록만 바뀐다(`git diff --stat uv.lock`이 몇 줄).

- [ ] **Step 2: 실패하는 테스트**

`agent/tests/test_mcp_tools.py` 끝에 더한다:
```python
def test_mcp_url_selects_streamable_http_and_needs_no_kubeconfig(tmp_path: Path) -> None:
    connection = k8s_read_connection(
        {
            "HOA_MCP_URL": " http://hoa-mcp-k8s-read.hoa-system.svc/mcp ",
            "HOA_MCP_KUBECONFIG": str(tmp_path / "missing"),
        }
    )

    assert connection == {
        "transport": "streamable_http",
        "url": "http://hoa-mcp-k8s-read.hoa-system.svc/mcp",
    }
```

`agent/tests/test_investigate.py` 맨 위에 `import httpx`를 더하고(서드파티 블록), 끝에 더한다:
```python
def test_an_unreachable_mcp_url_is_a_setup_error_without_the_address() -> None:
    refused = httpx.ConnectError("connection refused: http://hoa-mcp-k8s-read.hoa-system.svc/mcp")

    for raised in (refused, ExceptionGroup("tasks", [refused])):
        error = surfaced(raised)
        assert isinstance(error, MCPSetupError)
        assert "ConnectError" in str(error)
        assert "hoa-system.svc" not in str(error)
```

- [ ] **Step 3: 실패 확인**

Run: `uv run pytest agent/tests/test_mcp_tools.py agent/tests/test_investigate.py -q`
Expected: FAIL — 연결 테스트는 `MCPSetupError`(kubeconfig 없음)로, surfaced 테스트는 `ConnectError`가 그대로 돌아와 `isinstance`에서 깨진다.

- [ ] **Step 4: 구현**

`agent/src/hoa_agent/mcp_tools.py`:

import 전:
```python
from langchain_mcp_adapters.sessions import StdioConnection
```
후:
```python
from langchain_mcp_adapters.sessions import StdioConnection, StreamableHttpConnection
```

`k8s_read_connection` 앞부분 전:
```python
def k8s_read_connection(env: Mapping[str, str]) -> StdioConnection:
    """서버 프로세스에는 자기 설정만 넘긴다 — LLM API 키 같은 다른 환경변수는 물려주지 않는다."""
    kubeconfig = Path(env.get("HOA_MCP_KUBECONFIG", "").strip() or DEFAULT_KUBECONFIG)
```
후:
```python
def k8s_read_connection(env: Mapping[str, str]) -> StdioConnection | StreamableHttpConnection:
    """HOA_MCP_URL이 있으면 클러스터 안 MCP 서버에 HTTP로 붙고(hoa serve, 포트포워드),
    없으면 서버를 stdio 자식 프로세스로 띄운다. 자식 프로세스에는 자기 설정만 넘긴다 —
    LLM API 키 같은 다른 환경변수는 물려주지 않는다."""
    url = env.get("HOA_MCP_URL", "").strip()
    if url:
        return {"transport": "streamable_http", "url": url}
    kubeconfig = Path(env.get("HOA_MCP_KUBECONFIG", "").strip() or DEFAULT_KUBECONFIG)
```

`agent/src/hoa_agent/investigate.py`:

import 전:
```python
import os
import time
from collections.abc import Mapping

from mcp.shared.exceptions import McpError
```
후:
```python
import os
import time
from collections.abc import Mapping

import httpx
from mcp.shared.exceptions import McpError
```

`surfaced` 전:
```python
def surfaced(exc: BaseException) -> BaseException:
    """도구 실패는 ToolNode가 메시지로 바꾸므로 세션 밖까지 온 McpError는 서버 시작 실패다."""
    cause = sole_exception(exc) if isinstance(exc, BaseExceptionGroup) else exc
    if isinstance(cause, McpError):
        return MCPSetupError(f"the MCP server stopped ({cause}) — see its message above")
    return cause
```
후:
```python
def surfaced(exc: BaseException) -> BaseException:
    """도구 실패는 ToolNode가 메시지로 바꾸므로 세션 밖까지 온 MCP·HTTP 오류는 서버 연결 실패다."""
    cause = sole_exception(exc) if isinstance(exc, BaseExceptionGroup) else exc
    if isinstance(cause, McpError):
        return MCPSetupError(f"the MCP server stopped ({cause}) — see its message above")
    if isinstance(cause, httpx.HTTPError):
        # 원문에는 MCP 서버 주소가 들어 있다 — 종류만 알린다(LLM 오류는 openai가 따로 감싼다)
        return MCPSetupError(
            f"the MCP server could not be reached ({type(cause).__name__}) — check HOA_MCP_URL"
        )
    return cause
```

`run_investigation`의 `except` 전:
```python
    except (BaseExceptionGroup, McpError) as exc:
```
후:
```python
    except (BaseExceptionGroup, McpError, httpx.HTTPError) as exc:
```

- [ ] **Step 5: 통과 확인**

Run: `uv run pytest agent -q && uv run ruff check agent && uv run ruff format --check agent`
Expected: 모두 통과

- [ ] **Step 6: 커밋**

```bash
git add agent/pyproject.toml uv.lock agent/src/hoa_agent/mcp_tools.py agent/src/hoa_agent/investigate.py agent/tests/test_mcp_tools.py agent/tests/test_investigate.py
git commit -m "[Feat] 에이전트가 HOA_MCP_URL로 클러스터 안 MCP 서버에 HTTP로 붙는다"
```

---

### Task 7: 에이전트 HTTP API — `POST /investigations` (TDD)

**Files:**
- Modify: `agent/pyproject.toml`, `uv.lock`
- Create: `agent/src/hoa_agent/api.py`
- Test: `agent/tests/test_api.py`

- [ ] **Step 1: 의존성 — FastAPI·uvicorn**

`agent/pyproject.toml`의 `dependencies`에 두 줄을 알파벳 순서로 더한다.

전:
```toml
dependencies = [
    "httpx>=0.28.1",
```
후:
```toml
dependencies = [
    "fastapi>=0.163",
    "httpx>=0.28.1",
```

전:
```toml
    "pydantic>=2.14",
]
```
후:
```toml
    "pydantic>=2.14",
    "uvicorn>=0.54",
]
```

Run: `uv lock && uv sync`
Expected: 새 패키지 없이 `hoa-agent` 의존성 목록만 바뀐다(데모 앱이 이미 같은 패키지를 쓴다).

- [ ] **Step 2: 실패하는 테스트**

`agent/tests/test_api.py`:
```python
import asyncio
from collections.abc import Awaitable, Callable

import httpx
import openai
import pytest

from hoa_agent.api import MAX_ALERT_CHARS, create_app
from hoa_agent.graph import DiagnosisSchemaError
from hoa_agent.llm import LLMConfigError
from hoa_agent.mcp_tools import MCPSetupError
from hoa_agent.result import InvestigationResult

pytestmark = pytest.mark.anyio

Investigate = Callable[[str], Awaitable[InvestigationResult]]
ALERT = "KubeDeploymentRolloutStuck — namespace=demo deployment=orders"


def client_for(investigate: Investigate, *, timeout_seconds: float = 5.0) -> httpx.AsyncClient:
    app = create_app(investigate, timeout_seconds=timeout_seconds)
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://agent")


async def test_investigation_returns_the_same_json_as_the_cli(
    result: InvestigationResult,
) -> None:
    seen: list[str] = []

    async def fake(alert: str) -> InvestigationResult:
        seen.append(alert)
        return result

    async with client_for(fake) as client:
        response = await client.post("/investigations", json={"alert": ALERT})

    assert response.status_code == 200
    assert InvestigationResult.model_validate(response.json()) == result
    assert seen == [ALERT]


@pytest.mark.parametrize("alert", ["", "x" * (MAX_ALERT_CHARS + 1)])
async def test_empty_or_huge_alerts_are_rejected_before_investigating(alert: str) -> None:
    async def never(alert: str) -> InvestigationResult:
        raise AssertionError("must not be called")

    async with client_for(never) as client:
        response = await client.post("/investigations", json={"alert": alert})

    assert response.status_code == 422


async def test_a_second_request_while_busy_gets_429_with_retry_after(
    result: InvestigationResult,
) -> None:
    started = asyncio.Event()
    release = asyncio.Event()

    async def slow(alert: str) -> InvestigationResult:
        started.set()
        await release.wait()
        return result

    async with client_for(slow) as client:
        first = asyncio.create_task(client.post("/investigations", json={"alert": "a"}))
        await started.wait()
        second = await client.post("/investigations", json={"alert": "b"})
        release.set()
        assert (await first).status_code == 200

    assert second.status_code == 429
    assert second.headers["retry-after"] == "30"
    assert second.json() == {
        "error": {"kind": "busy", "message": "an investigation is already running"}
    }


async def test_the_lock_is_released_after_a_failure(result: InvestigationResult) -> None:
    calls: list[str] = []

    async def flaky(alert: str) -> InvestigationResult:
        calls.append(alert)
        if len(calls) == 1:
            raise DiagnosisSchemaError("the model broke the diagnosis schema")
        return result

    async with client_for(flaky) as client:
        failed = await client.post("/investigations", json={"alert": "a"})
        passed = await client.post("/investigations", json={"alert": "b"})

    assert (failed.status_code, passed.status_code) == (502, 200)


@pytest.mark.parametrize(
    ("error", "status", "kind"),
    [
        (LLMConfigError("HOA_GEMMA_BASE_URL is not set"), 503, "setup_error"),
        (MCPSetupError("the MCP server could not be reached (ConnectError)"), 503, "setup_error"),
        (DiagnosisSchemaError("the model broke the diagnosis schema"), 502, "investigation_failed"),
    ],
)
async def test_failures_map_to_status_codes(error: Exception, status: int, kind: str) -> None:
    async def failing(alert: str) -> InvestigationResult:
        raise error

    async with client_for(failing) as client:
        response = await client.post("/investigations", json={"alert": ALERT})

    assert response.status_code == status
    assert response.json()["error"]["kind"] == kind


async def test_rate_limit_is_503_with_its_own_kind(
    rate_limit_error: openai.RateLimitError,
) -> None:
    async def limited(alert: str) -> InvestigationResult:
        raise rate_limit_error

    async with client_for(limited) as client:
        response = await client.post("/investigations", json={"alert": ALERT})

    assert response.status_code == 503
    assert response.json()["error"] == {
        "kind": "llm_rate_limited",
        "message": "the LLM rate limit was hit — retry later",
    }


async def test_upstream_error_text_stays_out_of_the_response() -> None:
    async def unreachable(alert: str) -> InvestigationResult:
        request = httpx.Request("POST", "http://vllm.internal:8000/v1/chat/completions")
        raise openai.APIConnectionError(
            message="cannot reach http://vllm.internal:8000/v1", request=request
        )

    async with client_for(unreachable) as client:
        response = await client.post("/investigations", json={"alert": ALERT})

    assert response.status_code == 502
    assert "vllm.internal" not in response.text


async def test_a_slow_investigation_times_out_with_504() -> None:
    async def hang(alert: str) -> InvestigationResult:
        await asyncio.sleep(10)
        raise AssertionError("must be cancelled")

    async with client_for(hang, timeout_seconds=0.05) as client:
        response = await client.post("/investigations", json={"alert": ALERT})

    assert response.status_code == 504
    assert response.json()["error"]["kind"] == "timeout"


async def test_health_check_does_not_investigate() -> None:
    async def never(alert: str) -> InvestigationResult:
        raise AssertionError("must not be called")

    async with client_for(never) as client:
        response = await client.get("/healthz")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
```

- [ ] **Step 3: 실패 확인**

Run: `uv run pytest agent/tests/test_api.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'hoa_agent.api'`

- [ ] **Step 4: 구현**

`agent/src/hoa_agent/api.py`:
```python
import asyncio
import logging
import time
from collections.abc import Awaitable, Callable

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from hoa_agent.failures import HTTP_STATUSES, KNOWN_FAILURES, classify, public_message
from hoa_agent.result import InvestigationResult

Investigate = Callable[[str], Awaitable[InvestigationResult]]
MAX_ALERT_CHARS = 2_000
RETRY_AFTER_SECONDS = 30

logger = logging.getLogger(__name__)


class InvestigationRequest(BaseModel):
    alert: str = Field(min_length=1, max_length=MAX_ALERT_CHARS)


class ApiError(BaseModel):
    kind: str
    message: str


class ErrorBody(BaseModel):
    error: ApiError


def error_response(
    status: int, kind: str, message: str, *, retry_after: int | None = None
) -> JSONResponse:
    headers = None if retry_after is None else {"Retry-After": str(retry_after)}
    body = ErrorBody(error=ApiError(kind=kind, message=message))
    return JSONResponse(status_code=status, content=body.model_dump(), headers=headers)


def create_app(investigate: Investigate, *, timeout_seconds: float) -> FastAPI:
    """조사 함수를 주입받는다 — 테스트는 가짜를, hoa serve는 run_investigation을 끼운다."""
    app = FastAPI(title="hoa agent", docs_url=None, redoc_url=None, openapi_url=None)
    # 조사 예산(도구 6번·문맥 26K)이 1건 기준이고 GPU를 다른 시스템과 같이 쓴다 —
    # 줄 세우지 않고 바로 429로 돌려보낸다
    busy = asyncio.Lock()

    @app.get("/healthz")
    async def healthz() -> dict[str, str]:
        """프로세스만 본다 — LLM·MCP가 죽어도 재시작하지 않고 조사 요청에 503으로 알린다."""
        return {"status": "ok"}

    @app.post("/investigations", response_model=InvestigationResult)
    async def investigations(request: InvestigationRequest) -> InvestigationResult | JSONResponse:
        if busy.locked():
            return error_response(
                429,
                "busy",
                "an investigation is already running",
                retry_after=RETRY_AFTER_SECONDS,
            )
        async with busy:
            started = time.monotonic()
            try:
                async with asyncio.timeout(timeout_seconds):
                    result = await investigate(request.alert)
            except TimeoutError:
                logger.warning("investigation timed out after %.0fs", timeout_seconds)
                return error_response(
                    504,
                    "timeout",
                    f"the investigation did not finish within {timeout_seconds:.0f}s",
                )
            except KNOWN_FAILURES as exc:
                kind = classify(exc)
                # 원문(내부 주소가 섞일 수 있다)은 운영자 로그에만 남긴다
                logger.warning("investigation failed: %s", kind.value, exc_info=exc)
                return error_response(HTTP_STATUSES[kind], kind.value, public_message(kind, exc))
        logger.info(
            "investigation done: cause=%s stop=%s seconds=%.1f alert=%r",
            result.diagnosis.cause_label.value,
            result.stop_reason,
            time.monotonic() - started,
            request.alert[:80],
        )
        return result

    return app
```

- [ ] **Step 5: 통과 확인**

Run: `uv run pytest agent -q && uv run ruff check agent && uv run ruff format --check agent`
Expected: 모두 통과

- [ ] **Step 6: 커밋**

```bash
git add agent/pyproject.toml uv.lock agent/src/hoa_agent/api.py agent/tests/test_api.py
git commit -m "[Feat] 에이전트 HTTP API — POST /investigations(동시 1건·제한 시간·오류 분류)"
```

---

### Task 8: `hoa serve` — 환경변수로 API를 연다 (TDD)

**Files:**
- Modify: `agent/src/hoa_agent/cli.py`
- Test: `agent/tests/test_cli.py`

- [ ] **Step 1: 실패하는 테스트**

`agent/tests/test_cli.py`의 서드파티 import 블록에 `from fastapi import FastAPI`를 더하고, 끝에 더한다:
```python
def never_serve(app: object, **kwargs: object) -> None:
    raise AssertionError("must not start the server")


def test_serve_needs_the_mcp_url(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["serve"], env={}, run_server=never_serve) == 2
    assert "HOA_MCP_URL is not set" in capsys.readouterr().err


def test_serve_runs_the_api_on_the_given_port() -> None:
    calls: list[tuple[object, dict[str, object]]] = []

    def fake_run(app: object, **kwargs: object) -> None:
        calls.append((app, kwargs))

    env = {"HOA_MCP_URL": "http://hoa-mcp-k8s-read.hoa-system.svc/mcp", "HOA_MODEL": "gemini"}
    assert main(["serve", "--port", "9000"], env=env, run_server=fake_run) == 0

    [(app, kwargs)] = calls
    assert isinstance(app, FastAPI)
    assert kwargs == {"host": "127.0.0.1", "port": 9000}


@pytest.mark.parametrize(
    ("extra", "message"),
    [
        ({"HOA_MODEL": "gpt"}, "HOA_MODEL must be one of gemma, gemini"),
        ({"HOA_INVESTIGATION_TIMEOUT": "soon"}, "HOA_INVESTIGATION_TIMEOUT must be"),
        ({"HOA_INVESTIGATION_TIMEOUT": "0"}, "HOA_INVESTIGATION_TIMEOUT must be"),
        ({"HOA_INVESTIGATION_TIMEOUT": "nan"}, "HOA_INVESTIGATION_TIMEOUT must be"),
    ],
)
def test_serve_refuses_bad_settings(
    capsys: pytest.CaptureFixture[str], extra: dict[str, str], message: str
) -> None:
    env = {"HOA_MCP_URL": "http://hoa-mcp-k8s-read.hoa-system.svc/mcp", **extra}
    assert main(["serve"], env=env, run_server=never_serve) == 2
    assert message in capsys.readouterr().err
```

- [ ] **Step 2: 실패 확인**

Run: `uv run pytest agent/tests/test_cli.py -q`
Expected: FAIL — `TypeError: main() got an unexpected keyword argument 'env'`

- [ ] **Step 3: 구현**

`agent/src/hoa_agent/cli.py`:

import 전:
```python
import argparse
import asyncio
import io
import sys
from collections.abc import Awaitable, Callable, Sequence

from hoa_agent import __version__
```
후:
```python
import argparse
import asyncio
import io
import logging
import math
import os
import sys
from collections.abc import Awaitable, Callable, Mapping, Sequence

import uvicorn

from hoa_agent import __version__
from hoa_agent.api import create_app
```

`RATE_LIMITED_EXIT` 줄 아래에 더한다:
```python
DEFAULT_TIMEOUT_SECONDS = 300.0
ServerRunner = Callable[..., None]
```

`build_parser`에 `serve` 하위 명령을 더한다. 함수 전체(후):
```python
def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="hoa", description="hybrid-ops-agent 명령줄 도구")
    parser.add_argument("--version", action="version", version=f"hoa {__version__}")
    commands = parser.add_subparsers(dest="command")
    investigate = commands.add_parser("investigate", help="경보 하나를 조사해 진단을 낸다")
    investigate.add_argument(
        "--model", choices=MODEL_NAMES, default=DEFAULT_MODEL, help=f"쓸 LLM(기본 {DEFAULT_MODEL})"
    )
    investigate.add_argument(
        "--json", action="store_true", help="표준오류의 사람용 요약 없이 JSON만 낸다"
    )
    investigate.add_argument("alert", help="경보 문장")
    serve = commands.add_parser(
        "serve", help="조사 API를 연다(클러스터 안 — MCP 서버에 HTTP로 붙는다)"
    )
    serve.add_argument(
        "--host", default="127.0.0.1", help="묶을 주소(기본 127.0.0.1 — 차트가 0.0.0.0을 준다)"
    )
    serve.add_argument("--port", type=int, default=8080, help="포트(기본 8080)")
    return parser
```

`investigate_command` 아래에 더한다:
```python
def serve_command(
    args: argparse.Namespace, env: Mapping[str, str], run_server: ServerRunner
) -> int:
    if not env.get("HOA_MCP_URL", "").strip():
        print(
            "hoa: HOA_MCP_URL is not set — hoa serve reaches the MCP server over HTTP "
            "(the agent chart sets it)",
            file=sys.stderr,
        )
        return 2
    model = env.get("HOA_MODEL", "").strip() or DEFAULT_MODEL
    if model not in MODEL_NAMES:
        print(
            f"hoa: HOA_MODEL must be one of {', '.join(MODEL_NAMES)}, got {model!r}",
            file=sys.stderr,
        )
        return 2
    raw_timeout = env.get("HOA_INVESTIGATION_TIMEOUT", "").strip() or str(DEFAULT_TIMEOUT_SECONDS)
    try:
        timeout = float(raw_timeout)
    except ValueError:
        timeout = math.nan
    if not (math.isfinite(timeout) and timeout > 0):
        print(
            "hoa: HOA_INVESTIGATION_TIMEOUT must be a positive number of seconds, "
            f"got {raw_timeout!r}",
            file=sys.stderr,
        )
        return 2

    async def investigate(alert: str) -> InvestigationResult:
        return await run_investigation(alert, model, env)

    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
    )
    run_server(create_app(investigate, timeout_seconds=timeout), host=args.host, port=args.port)
    return 0
```

`main` 전:
```python
def main(
    argv: Sequence[str] | None = None, *, investigator: Investigator = run_investigation
) -> int:
    use_utf8_output()
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command == "investigate":
        return investigate_command(args, investigator)
    parser.print_help()
    return 0
```
후:
```python
def main(
    argv: Sequence[str] | None = None,
    *,
    investigator: Investigator = run_investigation,
    env: Mapping[str, str] | None = None,
    run_server: ServerRunner = uvicorn.run,
) -> int:
    use_utf8_output()
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command == "investigate":
        return investigate_command(args, investigator)
    if args.command == "serve":
        return serve_command(args, os.environ if env is None else env, run_server)
    parser.print_help()
    return 0
```

- [ ] **Step 4: 통과 확인**

Run: `uv run pytest agent -q && uv run ruff check agent && uv run ruff format --check agent`
Expected: 모두 통과

Run: `uv run hoa serve; echo "exit=$?"`
Expected: `hoa: HOA_MCP_URL is not set — …`, `exit=2`(셸에 `HOA_MCP_URL`을 export하지 않았을 때). 기본 바인드 주소는 루프백(`127.0.0.1`)이라 개발 PC에서 띄워도 LAN에 열리지 않는다 — 차트가 파드 안에서 `--host 0.0.0.0`을 준다(MCP 서버의 `HOA_MCP_HOST`와 같은 원칙, 구현 리뷰 반영). 실제 실행은 파드 안에서 본다(Task 13·16).

- [ ] **Step 5: 커밋**

```bash
git add agent/src/hoa_agent/cli.py agent/tests/test_cli.py
git commit -m "[Feat] hoa serve — 환경변수(HOA_MCP_URL·HOA_MODEL·HOA_INVESTIGATION_TIMEOUT)로 조사 API를 연다"
```

---

### Task 9: 이미지 셋 — Dockerfile 하나

**Files:**
- Create: `deploy/docker/Dockerfile`
- Create: `deploy/docker/Dockerfile.dockerignore`
- Delete: `demo_app/Dockerfile`, `demo_app/Dockerfile.dockerignore`
- Modify: `scripts/dev-cluster.sh`(빌드 한 줄 — Task 13에서 전체를 다시 쓴다)
- Modify: `docs/standards/coding-standard.md`(「패키지 경계」의 Dockerfile 경로)

- [ ] **Step 1: Dockerfile**

`deploy/docker/Dockerfile`:
```dockerfile
# 워크스페이스 멤버 하나를 담는 이미지 — 데모 앱·MCP 서버·에이전트가 같은 파일을 쓴다.
# 빌드 컨텍스트는 저장소 루트다(uv 워크스페이스의 잠금 파일과 멤버 pyproject가 루트 기준).
#   docker build -f deploy/docker/Dockerfile --build-arg PACKAGE=hoa-mcp --build-arg MEMBER=mcp_servers -t hoa-mcp:0.1.0 .
# uv sync --locked 는 워크스페이스 모든 멤버의 pyproject를 요구한다 — 멤버가 늘면 아래 COPY 줄과
# Dockerfile.dockerignore 를 같이 늘린다. 실행 명령은 차트가 정한다(이미지에는 CMD가 없다).
FROM ghcr.io/astral-sh/uv:0.11.31 AS uv

FROM python:3.12.16-slim-bookworm AS build
ARG PACKAGE
ARG MEMBER
COPY --from=uv /uv /usr/local/bin/uv
ENV UV_COMPILE_BYTECODE=1 \
    UV_NO_CACHE=1 \
    UV_PYTHON_DOWNLOADS=never
WORKDIR /app
COPY pyproject.toml uv.lock ./
COPY agent/pyproject.toml agent/
COPY demo_app/pyproject.toml demo_app/
COPY eval/pyproject.toml eval/
COPY mcp_servers/pyproject.toml mcp_servers/
# 의존성 레이어를 소스보다 먼저 만든다 — 소스만 바뀌면 이 레이어는 캐시에서 온다
RUN test -n "${PACKAGE}" && test -n "${MEMBER}" \
    && uv sync --locked --package "${PACKAGE}" --no-dev --no-install-workspace
COPY ${MEMBER}/src ${MEMBER}/src
RUN uv sync --locked --package "${PACKAGE}" --no-dev --no-editable

# 실행 이미지에는 가상환경만 옮긴다 — uv·소스·빌드 잔여물을 남기지 않는다.
FROM python:3.12.16-slim-bookworm
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH=/app/.venv/bin:$PATH
COPY --from=build /app/.venv /app/.venv
USER 65532:65532
```

`deploy/docker/Dockerfile.dockerignore`:
```
# deploy/docker/Dockerfile 전용 무시 목록 — 빌드 컨텍스트(저장소 루트)에서 이미지에 필요한 것만 보낸다.
*
!pyproject.toml
!uv.lock
!agent/pyproject.toml
!agent/src
!demo_app/pyproject.toml
!demo_app/src
!eval/pyproject.toml
!mcp_servers/pyproject.toml
!mcp_servers/src
**/__pycache__
```

Run: `git rm -q demo_app/Dockerfile demo_app/Dockerfile.dockerignore`

`scripts/dev-cluster.sh`의 빌드 줄을 새 Dockerfile로 바꾼다(Task 13까지 `up`이 계속 돈다).

전:
```bash
  docker build -f demo_app/Dockerfile -t "${DEMO_IMAGE}" .
```
후:
```bash
  docker build -f deploy/docker/Dockerfile --build-arg PACKAGE=hoa-demo --build-arg MEMBER=demo_app \
    -t "${DEMO_IMAGE}" .
```

`docs/standards/coding-standard.md` 「패키지 경계」 마지막 항목의 한 구절을 바꾼다.

전:
```markdown
멤버 이미지의 Dockerfile(예: `demo_app/Dockerfile`)과 그 옆 `Dockerfile.dockerignore`에도 새 멤버의 `pyproject.toml`을 더한다
```
후:
```markdown
멤버 이미지를 만드는 `deploy/docker/Dockerfile`과 그 옆 `Dockerfile.dockerignore`에도 새 멤버의 `pyproject.toml`을 더한다
```

- [ ] **Step 2: 이미지 셋 빌드**

Run:
```bash
for spec in hoa-demo:hoa-demo:demo_app hoa-mcp:hoa-mcp:mcp_servers hoa-agent:hoa-agent:agent; do
  IFS=: read -r name package member <<<"${spec}"
  docker build -q -f deploy/docker/Dockerfile --build-arg "PACKAGE=${package}" \
    --build-arg "MEMBER=${member}" -t "${name}:0.1.0" . || break
done
```
Expected: 세 이미지 ID(`sha256:…`)가 찍힌다.

- [ ] **Step 3: 이미지마다 자기 멤버만 담겼는지 본다**

Run: `docker run --rm hoa-agent:0.1.0 hoa --version`
Expected: `hoa 0.1.0`

Run: `docker run --rm hoa-mcp:0.1.0 hoa-mcp-k8s-read; echo "exit=$?"`
Expected: `hoa-mcp-k8s-read: HOA_MCP_KUBECONFIG is not set`, `exit=2`

Run: `docker run --rm hoa-demo:0.1.0 python -c "import hoa_demo; print('demo ok')"`
Expected: `demo ok`

Run: `docker run --rm hoa-mcp:0.1.0 python -c "import langgraph" 2>&1 | tail -1; docker run --rm hoa-agent:0.1.0 python -c "import hoa_mcp" 2>&1 | tail -1`
Expected: 두 줄 모두 `ModuleNotFoundError: …` — MCP 이미지에 LangGraph가, 에이전트 이미지에 MCP 서버 패키지가 없다(코딩 표준 「패키지 경계」).

Run: `docker run --rm hoa-agent:0.1.0 id -u`
Expected: `65532`

- [ ] **Step 4: 커밋**

```bash
git add deploy/docker/Dockerfile deploy/docker/Dockerfile.dockerignore scripts/dev-cluster.sh docs/standards/coding-standard.md
git commit -m "[Feat] 이미지 셋을 Dockerfile 하나로 — 데모 앱·MCP 서버·에이전트(ARG PACKAGE·MEMBER)"
```

---

### Task 10: 데모 앱 차트와 차트 정책 테스트

**Files:**
- Modify: `.pre-commit-config.yaml`, `pyproject.toml`
- Create: `deploy/tests/test_charts.py`
- Create: `deploy/helm/demo-app/Chart.yaml`, `values.yaml`, `templates/_helpers.tpl`, `templates/deployment.yaml`, `templates/service.yaml`
- Create: `deploy/values/kind/demo-app.yaml`
- Create: `deploy/kind/namespaces.yaml`

- [ ] **Step 1: 게이트 설정 — check-yaml 제외와 `charts` 마커**

`.pre-commit-config.yaml`의 check-yaml 항목을 바꾼다.

전:
```yaml
      - id: check-yaml
        args: [--allow-multiple-documents]
```
후:
```yaml
      - id: check-yaml
        args: [--allow-multiple-documents]
        # Helm 템플릿은 Go 템플릿이라 YAML 파서가 읽지 못한다 — helm lint·kubeconform(CI 차트 잡)이 대신 본다
        exclude: ^deploy/helm/[^/]+/templates/
```

`pyproject.toml`의 pytest 설정을 바꾼다.

전:
```toml
addopts = '--import-mode=importlib --strict-markers -m "not integration"'
testpaths = ["agent/tests", "demo_app/tests", "eval/tests", "mcp_servers/tests", "scripts/tests"]
filterwarnings = ["error"]
markers = [
    "integration: kind 클러스터가 필요한 통합 테스트 — uv run pytest -m integration 으로 따로 돈다",
]
```
후:
```toml
addopts = '--import-mode=importlib --strict-markers -m "not integration and not charts"'
testpaths = [
    "agent/tests",
    "demo_app/tests",
    "deploy/tests",
    "eval/tests",
    "mcp_servers/tests",
    "scripts/tests",
]
filterwarnings = ["error"]
markers = [
    "integration: kind 클러스터가 필요한 통합 테스트 — uv run pytest -m integration 으로 따로 돈다",
    "charts: helm으로 차트를 렌더하는 정책 테스트 — helm v4.3.2가 필요하다. uv run pytest -m charts 로 따로 돈다",
]
```

- [ ] **Step 2: 실패하는 정책 테스트**

`deploy/tests/test_charts.py`:
```python
"""Helm 차트 정책 — 렌더 결과를 코딩 표준(쿠버네티스·인프라)에 비춰 본다.

helm(v4.3.2)이 필요하다 — CI 차트 잡과 개발 PC 호스트에서 uv run pytest -m charts 로 돈다.
"""

import shutil
import subprocess
from pathlib import Path
from typing import Any

import pytest
import yaml

pytestmark = pytest.mark.charts

ROOT = Path(__file__).resolve().parents[2]
# 차트 → 릴리스 네임스페이스
CHARTS = {"demo-app": "demo"}

Manifest = dict[str, Any]


def helm_template(chart: str, *values: Path) -> subprocess.CompletedProcess[str]:
    helm = shutil.which("helm")
    if helm is None:
        pytest.fail("helm이 없다 — 차트 테스트는 helm v4.3.2가 필요하다")
    args = [
        helm,
        "template",
        chart,
        str(ROOT / "deploy" / "helm" / chart),
        "--namespace",
        CHARTS[chart],
    ]
    for path in values:
        args += ["--values", str(path)]
    return subprocess.run(
        args,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=60,
        check=False,
    )


def render(chart: str) -> list[Manifest]:
    result = helm_template(chart, ROOT / "deploy" / "values" / "kind" / f"{chart}.yaml")
    assert result.returncode == 0, result.stderr
    return [doc for doc in yaml.safe_load_all(result.stdout) if doc]


@pytest.fixture(scope="module")
def manifests() -> list[Manifest]:
    return [doc for chart in CHARTS for doc in render(chart)]


def deployments(manifests: list[Manifest]) -> list[Manifest]:
    return [m for m in manifests if m["kind"] == "Deployment"]


def deployment(manifests: list[Manifest], name: str) -> Manifest:
    [found] = [d for d in deployments(manifests) if d["metadata"]["name"] == name]
    return found


def containers(workload: Manifest) -> list[Manifest]:
    return workload["spec"]["template"]["spec"]["containers"]


def env_of(workload: Manifest) -> dict[str, str]:
    return {var["name"]: var.get("value", "") for var in containers(workload)[0].get("env", [])}


@pytest.mark.parametrize("chart", sorted(CHARTS))
def test_chart_needs_an_image_from_the_tier_values(chart: str) -> None:
    result = helm_template(chart)
    assert result.returncode != 0
    assert "image.repository is required" in result.stderr


def test_every_container_has_cpu_and_memory_requests_and_limits(
    manifests: list[Manifest],
) -> None:
    for workload in deployments(manifests):
        for container in containers(workload):
            resources = container["resources"]
            assert set(resources["requests"]) == {"cpu", "memory"}, workload["metadata"]["name"]
            assert set(resources["limits"]) == {"cpu", "memory"}, workload["metadata"]["name"]


def test_every_container_meets_the_restricted_pod_security_standard(
    manifests: list[Manifest],
) -> None:
    for workload in deployments(manifests):
        for container in containers(workload):
            context = container["securityContext"]
            name = workload["metadata"]["name"]
            assert context["runAsNonRoot"] is True, name
            assert context["allowPrivilegeEscalation"] is False, name
            assert context["readOnlyRootFilesystem"] is True, name
            assert context["capabilities"]["drop"] == ["ALL"], name
            assert context["seccompProfile"]["type"] == "RuntimeDefault", name


def test_images_are_pinned_to_a_tag(manifests: list[Manifest]) -> None:
    for workload in deployments(manifests):
        for container in containers(workload):
            repository, _, tag = container["image"].rpartition(":")
            assert repository and tag and tag != "latest", container["image"]


def test_only_the_mcp_server_mounts_a_service_account_token(manifests: list[Manifest]) -> None:
    mounting = {
        workload["metadata"]["name"]
        for workload in deployments(manifests)
        if workload["spec"]["template"]["spec"].get("automountServiceAccountToken", True)
    }
    assert mounting <= {"hoa-mcp-k8s-read"}


def test_every_hoa_system_deployment_has_a_network_policy(manifests: list[Manifest]) -> None:
    policies = [m for m in manifests if m["kind"] == "NetworkPolicy"]
    for workload in deployments(manifests):
        if workload["metadata"]["namespace"] != "hoa-system":
            continue
        labels = workload["spec"]["template"]["metadata"]["labels"]
        assert any(
            policy["metadata"]["namespace"] == "hoa-system"
            and all(
                labels.get(key) == value
                for key, value in policy["spec"]["podSelector"]["matchLabels"].items()
            )
            for policy in policies
        ), workload["metadata"]["name"]
```

`deployment`·`env_of`는 Task 11·12의 테스트가 쓴다.

- [ ] **Step 3: 실패 확인**

Run: `uv run pytest -m charts -q`
Expected: FAIL — 차트 폴더가 없어 `helm template`이 `path "…/deploy/helm/demo-app" not found`로 실패한다.

Run: `uv run pytest -q`
Expected: 통과 — 기본 실행에서 `charts` 테스트는 빠진다(`deselected`).

- [ ] **Step 4: 데모 앱 차트**

`deploy/helm/demo-app/Chart.yaml`:
```yaml
apiVersion: v2
name: demo-app
description: 진단 대상 데모 앱(gateway → orders → inventory) — 서비스마다 Deployment·Service
type: application
version: 0.1.0
appVersion: "0.1.0"
```

`deploy/helm/demo-app/values.yaml`:
```yaml
# 티어마다 다른 값(이미지)은 deploy/values/<티어>/demo-app.yaml 이 정한다 — 여기에는 기본값을 두지 않는다.
image:
  repository: ""
  tag: ""
  pullPolicy: IfNotPresent
port: 8080
# 장애가 rollout을 멈추면 이 시간 뒤에 Progressing=False가 된다
progressDeadlineSeconds: 120
resources:
  requests:
    cpu: 50m
    memory: 64Mi
  limits:
    cpu: 250m
    memory: 192Mi
securityContext:
  runAsNonRoot: true
  runAsUser: 65532
  runAsGroup: 65532
  allowPrivilegeEscalation: false
  readOnlyRootFilesystem: true
  capabilities:
    drop: [ALL]
  seccompProfile:
    type: RuntimeDefault
# 서비스 이름은 장애 패치(deploy/kind/faults/)와 평가 시나리오가 가리키는 Deployment·컨테이너 이름이다
services:
  - name: inventory
    env: []
  - name: orders
    env:
      - name: HOA_DEMO_INVENTORY_URL
        value: http://inventory
  - name: gateway
    env:
      - name: HOA_DEMO_ORDERS_URL
        value: http://orders
```

`deploy/helm/demo-app/templates/_helpers.tpl`:
```
{{/* 차트가 붙이는 공통 라벨 — 셀렉터에는 쓰지 않는다(Deployment 셀렉터는 바꿀 수 없는 필드다) */}}
{{- define "demo-app.labels" -}}
app.kubernetes.io/part-of: hoa-demo
app.kubernetes.io/instance: {{ .Release.Name }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
helm.sh/chart: {{ printf "%s-%s" .Chart.Name .Chart.Version }}
{{- end }}

{{- define "demo-app.image" -}}
{{ required "image.repository is required — set it in the tier values file" .Values.image.repository }}:{{ required "image.tag is required — set it in the tier values file" .Values.image.tag }}
{{- end }}
```

`deploy/helm/demo-app/templates/deployment.yaml`:
```yaml
{{- range .Values.services }}
---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: {{ .name }}
  namespace: {{ $.Release.Namespace }}
  labels:
    app: {{ .name }}
    app.kubernetes.io/name: {{ .name }}
    {{- include "demo-app.labels" $ | nindent 4 }}
spec:
  replicas: 1
  progressDeadlineSeconds: {{ $.Values.progressDeadlineSeconds }}
  selector:
    matchLabels:
      app: {{ .name }}
  template:
    metadata:
      labels:
        app: {{ .name }}
        app.kubernetes.io/name: {{ .name }}
        app.kubernetes.io/instance: {{ $.Release.Name }}
    spec:
      automountServiceAccountToken: false
      containers:
        - name: {{ .name }}
          image: {{ include "demo-app.image" $ }}
          imagePullPolicy: {{ $.Values.image.pullPolicy }}
          command: ["hoa-demo"]
          env:
            - name: HOA_DEMO_ROLE
              value: {{ .name }}
            - name: HOA_DEMO_PORT
              value: {{ $.Values.port | quote }}
            {{- range .env }}
            - name: {{ .name }}
              value: {{ .value | quote }}
            {{- end }}
          ports:
            - name: http
              containerPort: {{ $.Values.port }}
          readinessProbe:
            httpGet:
              path: /healthz
              port: http
            periodSeconds: 5
          livenessProbe:
            httpGet:
              path: /healthz
              port: http
            periodSeconds: 10
          resources:
            {{- toYaml $.Values.resources | nindent 12 }}
          securityContext:
            {{- toYaml $.Values.securityContext | nindent 12 }}
{{- end }}
```

`deploy/helm/demo-app/templates/service.yaml`:
```yaml
{{- range .Values.services }}
---
apiVersion: v1
kind: Service
metadata:
  name: {{ .name }}
  namespace: {{ $.Release.Namespace }}
  labels:
    app.kubernetes.io/name: {{ .name }}
    {{- include "demo-app.labels" $ | nindent 4 }}
spec:
  selector:
    app: {{ .name }}
  ports:
    - name: http
      port: 80
      targetPort: http
{{- end }}
```

`deploy/values/kind/demo-app.yaml`:
```yaml
# 로컬 티어(kind) — 이미지는 scripts/dev-cluster.sh 가 빌드해 kind load 로 넣는다(레지스트리 없음).
# 장애 image-pull 은 같은 저장소의 없는 태그(hoa-demo:0.1.0-missing)로 바꾼다.
image:
  repository: hoa-demo
  tag: 0.1.0
  pullPolicy: IfNotPresent
```

`deploy/kind/namespaces.yaml`:
```yaml
# 로컬 티어의 네임스페이스 — 차트는 네임스페이스를 만들지 않는다(GPU 티어에서는 Argo CD가 같은 라벨로 만든다).
# 둘 다 restricted 파드 보안 표준을 강제한다 — 비루트·권한 상승 금지·capability 제거·seccomp를 어기는 파드는 거부된다.
apiVersion: v1
kind: Namespace
metadata:
  name: demo
  labels:
    pod-security.kubernetes.io/enforce: restricted
---
apiVersion: v1
kind: Namespace
metadata:
  name: hoa-system
  labels:
    pod-security.kubernetes.io/enforce: restricted
```

- [ ] **Step 5: 통과 확인**

Run: `helm lint deploy/helm/demo-app --values deploy/values/kind/demo-app.yaml`
Expected: `1 chart(s) linted, 0 chart(s) failed`(아이콘 권고 `[INFO]`는 괜찮다)

Run: `uv run pytest -m charts -q`
Expected: PASS(6개)

- [ ] **Step 6: 렌더 결과가 기존 매니페스트와 같은지 한 번 확인**

차트가 붙인 라벨(`app.kubernetes.io/*`·`helm.sh/*`)과 실행 명령(`command` — 이미지에서 CMD를 뺐다)만 빼고 같아야 한다. 장애 패치와 시나리오가 그대로 맞는다는 뜻이다.

Run:
```bash
helm template demo-app deploy/helm/demo-app --namespace demo --values deploy/values/kind/demo-app.yaml | uv run python -c '
import pathlib, sys, yaml
PREFIXES = ("app.kubernetes.io/", "helm.sh/")
def clean(labels):
    return {k: v for k, v in (labels or {}).items() if not k.startswith(PREFIXES)}
def norm(doc):
    doc["metadata"]["labels"] = clean(doc["metadata"].get("labels"))
    if doc["kind"] == "Deployment":
        template = doc["spec"]["template"]
        template["metadata"]["labels"] = clean(template["metadata"]["labels"])
        for container in template["spec"]["containers"]:
            container.pop("command", None)
    return (doc["kind"], doc["metadata"]["name"]), doc
new = dict(norm(d) for d in yaml.safe_load_all(sys.stdin) if d)
files = sorted(pathlib.Path("deploy/kind/demo").glob("[1-9]*.yaml"))
old = dict(norm(d) for f in files for d in yaml.safe_load_all(f.read_text(encoding="utf-8")) if d)
print("same" if new == old else "DIFF")
for key in sorted(set(new) | set(old)):
    if new.get(key) != old.get(key):
        print(key, new.get(key), old.get(key), sep="\n")
'
```
Expected: `same` 한 줄. `DIFF`면 다른 객체가 출력된다 — 차트를 고쳐 `same`이 될 때까지 맞춘다(기존 매니페스트는 Task 13에서 지운다).

- [ ] **Step 7: 커밋**

```bash
git add .pre-commit-config.yaml pyproject.toml deploy/tests/test_charts.py deploy/helm/demo-app deploy/values/kind/demo-app.yaml deploy/kind/namespaces.yaml
git commit -m "[Feat] 데모 앱 Helm 차트와 차트 정책 테스트(charts 마커), kind 네임스페이스"
```

---

### Task 11: MCP `k8s-read` 차트

**Files:**
- Create: `deploy/helm/mcp-k8s-read/Chart.yaml`, `values.yaml`, `templates/_helpers.tpl`, `templates/serviceaccount.yaml`, `templates/rbac.yaml`, `templates/deployment.yaml`, `templates/service.yaml`, `templates/networkpolicy.yaml`
- Create: `deploy/values/kind/mcp-k8s-read.yaml`
- Modify: `deploy/tests/test_charts.py`

- [ ] **Step 1: 실패하는 테스트**

`deploy/tests/test_charts.py`의 `CHARTS`에 MCP 차트를 더한다.

전:
```python
CHARTS = {"demo-app": "demo"}
```
후:
```python
CHARTS = {"demo-app": "demo", "mcp-k8s-read": "hoa-system"}
```

파일 끝에 더한다:
```python
def test_mcp_role_bindings_match_the_servers_namespace_allowlist(
    manifests: list[Manifest],
) -> None:
    server = deployment(manifests, "hoa-mcp-k8s-read")
    allowed = set(env_of(server)["HOA_MCP_ALLOWED_NAMESPACES"].split(","))
    bound = {
        m["metadata"]["namespace"]
        for m in manifests
        if m["kind"] == "RoleBinding" and m["roleRef"]["name"] == "hoa-k8s-read"
    }
    assert bound == allowed == {"demo"}


def test_mcp_cluster_role_reads_only_what_the_tools_need(manifests: list[Manifest]) -> None:
    [role] = [m for m in manifests if m["kind"] == "ClusterRole"]
    resources = {resource for rule in role["rules"] for resource in rule["resources"]}
    verbs = {verb for rule in role["rules"] for verb in rule["verbs"]}
    assert resources == {"pods", "events", "pods/log", "deployments", "replicasets"}
    assert verbs == {"get", "list"}


def test_mcp_server_accepts_only_its_service_name_and_port_forwards(
    manifests: list[Manifest],
) -> None:
    server = deployment(manifests, "hoa-mcp-k8s-read")
    assert env_of(server)["HOA_MCP_ALLOWED_HOSTS"].split(",") == [
        "hoa-mcp-k8s-read.hoa-system.svc",
        "hoa-mcp-k8s-read.hoa-system.svc.cluster.local",
        "127.0.0.1:*",
        "localhost:*",
    ]
    assert env_of(server)["HOA_MCP_KUBE_AUTH"] == "in-cluster"
    assert env_of(server)["HOA_MCP_TRANSPORT"] == "http"
    assert env_of(server)["HOA_MCP_HOST"] == "0.0.0.0"
```

- [ ] **Step 2: 실패 확인**

Run: `uv run pytest -m charts -q`
Expected: FAIL — `path "…/deploy/helm/mcp-k8s-read" not found`

- [ ] **Step 3: MCP 차트**

`deploy/helm/mcp-k8s-read/Chart.yaml`:
```yaml
apiVersion: v2
name: mcp-k8s-read
description: MCP k8s-read 서버 — 읽기 전용 ServiceAccount로 클러스터를 읽는 도구 4개(streamable HTTP)
type: application
version: 0.1.0
appVersion: "0.1.0"
```

`deploy/helm/mcp-k8s-read/values.yaml`:
```yaml
# 티어마다 다른 값(이미지)은 deploy/values/<티어>/mcp-k8s-read.yaml 이 정한다 — 여기에는 기본값을 두지 않는다.
image:
  repository: ""
  tag: ""
  pullPolicy: IfNotPresent
# 이 서버가 읽을 수 있는 네임스페이스 — RoleBinding과 서버의 허용 목록(HOA_MCP_ALLOWED_NAMESPACES)이 같은 값에서 나온다
targetNamespaces:
  - demo
port: 8080
# 이 라벨을 단 파드(같은 네임스페이스)만 MCP 포트에 닿는다 — 에이전트 차트의 파드 라벨이다
allowedClientLabels:
  app.kubernetes.io/name: hoa-agent
resources:
  requests:
    cpu: 50m
    memory: 128Mi
  limits:
    cpu: 500m
    memory: 256Mi
securityContext:
  runAsNonRoot: true
  runAsUser: 65532
  runAsGroup: 65532
  allowPrivilegeEscalation: false
  readOnlyRootFilesystem: true
  capabilities:
    drop: [ALL]
  seccompProfile:
    type: RuntimeDefault
```

`deploy/helm/mcp-k8s-read/templates/_helpers.tpl`:
```
{{/* 리소스 이름 — 에이전트 차트의 mcpUrl과 통합 테스트가 이 이름을 쓴다 */}}
{{- define "mcp-k8s-read.name" -}}
hoa-mcp-k8s-read
{{- end }}

{{- define "mcp-k8s-read.selectorLabels" -}}
app.kubernetes.io/name: {{ include "mcp-k8s-read.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end }}

{{- define "mcp-k8s-read.labels" -}}
{{ include "mcp-k8s-read.selectorLabels" . }}
app.kubernetes.io/part-of: hoa
app.kubernetes.io/managed-by: {{ .Release.Service }}
helm.sh/chart: {{ printf "%s-%s" .Chart.Name .Chart.Version }}
{{- end }}

{{/* 클러스터 안 Service 이름 — 포트(80)를 붙이지 않고 부르므로 Host 헤더가 이 값 그대로다 */}}
{{- define "mcp-k8s-read.serviceHost" -}}
{{ include "mcp-k8s-read.name" . }}.{{ .Release.Namespace }}.svc
{{- end }}

{{- define "mcp-k8s-read.image" -}}
{{ required "image.repository is required — set it in the tier values file" .Values.image.repository }}:{{ required "image.tag is required — set it in the tier values file" .Values.image.tag }}
{{- end }}
```

`deploy/helm/mcp-k8s-read/templates/serviceaccount.yaml`:
```yaml
# 읽기 전용 계정 — 이름은 scripts/dev-cluster.sh mcp-kubeconfig(개발 PC stdio용 토큰)와 통합 테스트가 쓴다
apiVersion: v1
kind: ServiceAccount
metadata:
  name: hoa-mcp-read
  namespace: {{ .Release.Namespace }}
  labels:
    {{- include "mcp-k8s-read.labels" . | nindent 4 }}
```

`deploy/helm/mcp-k8s-read/templates/rbac.yaml`:
```yaml
# 권한 정의는 ClusterRole 한 번, 범위는 대상 네임스페이스마다 RoleBinding으로 좁힌다.
# 도구가 실제로 읽는 리소스와 동사만 넣는다(watch는 쓰지 않는다). Secret·ConfigMap은 넣지 않는다.
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRole
metadata:
  name: hoa-k8s-read
  labels:
    {{- include "mcp-k8s-read.labels" . | nindent 4 }}
rules:
  - apiGroups: [""]
    resources: [pods, events]
    verbs: [get, list]
  - apiGroups: [""]
    resources: [pods/log]
    verbs: [get]
  - apiGroups: [apps]
    resources: [deployments, replicasets]
    verbs: [get, list]
{{- range .Values.targetNamespaces }}
---
apiVersion: rbac.authorization.k8s.io/v1
kind: RoleBinding
metadata:
  name: hoa-mcp-read
  namespace: {{ . }}
  labels:
    {{- include "mcp-k8s-read.labels" $ | nindent 4 }}
roleRef:
  apiGroup: rbac.authorization.k8s.io
  kind: ClusterRole
  name: hoa-k8s-read
subjects:
  - kind: ServiceAccount
    name: hoa-mcp-read
    namespace: {{ $.Release.Namespace }}
{{- end }}
```

`deploy/helm/mcp-k8s-read/templates/deployment.yaml`:
```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: {{ include "mcp-k8s-read.name" . }}
  namespace: {{ .Release.Namespace }}
  labels:
    {{- include "mcp-k8s-read.labels" . | nindent 4 }}
spec:
  replicas: 1
  selector:
    matchLabels:
      {{- include "mcp-k8s-read.selectorLabels" . | nindent 6 }}
  template:
    metadata:
      labels:
        {{- include "mcp-k8s-read.selectorLabels" . | nindent 8 }}
    spec:
      serviceAccountName: hoa-mcp-read
      # 이 서버만 쿠버네티스 API를 부른다 — 읽기 전용 ServiceAccount 토큰을 마운트한다
      automountServiceAccountToken: true
      containers:
        - name: mcp
          image: {{ include "mcp-k8s-read.image" . }}
          imagePullPolicy: {{ .Values.image.pullPolicy }}
          command: ["hoa-mcp-k8s-read"]
          env:
            - name: HOA_MCP_TRANSPORT
              value: http
            - name: HOA_MCP_KUBE_AUTH
              value: in-cluster
            # 파드 밖(에이전트 파드)에서 오는 연결을 받으려면 모든 인터페이스에 묶는다 — 서버 기본값은 127.0.0.1
            - name: HOA_MCP_HOST
              value: "0.0.0.0"
            - name: HOA_MCP_PORT
              value: {{ .Values.port | quote }}
            # RoleBinding과 같은 값에서 나온다 — RBAC과 서버의 허용 목록이 어긋나지 않게
            - name: HOA_MCP_ALLOWED_NAMESPACES
              value: {{ join "," .Values.targetNamespaces | quote }}
            # 클러스터 안 이름과 포트포워드(127.0.0.1·localhost)만 받는다 — DNS 리바인딩 방어
            - name: HOA_MCP_ALLOWED_HOSTS
              value: {{ printf "%s,%s.cluster.local,127.0.0.1:*,localhost:*" (include "mcp-k8s-read.serviceHost" .) (include "mcp-k8s-read.serviceHost" .) | quote }}
          ports:
            - name: http
              containerPort: {{ .Values.port }}
          readinessProbe:
            httpGet:
              path: /healthz
              port: http
            periodSeconds: 5
          livenessProbe:
            httpGet:
              path: /healthz
              port: http
            periodSeconds: 10
          resources:
            {{- toYaml .Values.resources | nindent 12 }}
          securityContext:
            {{- toYaml .Values.securityContext | nindent 12 }}
          volumeMounts:
            - name: tmp
              mountPath: /tmp
      # 루트 파일시스템이 읽기 전용이라 임시 파일을 쓰는 라이브러리를 위해 /tmp만 쓰게 둔다
      volumes:
        - name: tmp
          emptyDir: {}
```

`deploy/helm/mcp-k8s-read/templates/service.yaml`:
```yaml
apiVersion: v1
kind: Service
metadata:
  name: {{ include "mcp-k8s-read.name" . }}
  namespace: {{ .Release.Namespace }}
  labels:
    {{- include "mcp-k8s-read.labels" . | nindent 4 }}
spec:
  selector:
    {{- include "mcp-k8s-read.selectorLabels" . | nindent 4 }}
  ports:
    - name: http
      port: 80
      targetPort: http
```

`deploy/helm/mcp-k8s-read/templates/networkpolicy.yaml`:
```yaml
# MCP 포트에는 같은 네임스페이스의 에이전트 파드만 닿는다.
# 파드가 도는 노드에서 오는 트래픽(kubelet 프로브)과 kubectl port-forward는 NetworkPolicy가 막지 못한다.
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: {{ include "mcp-k8s-read.name" . }}
  namespace: {{ .Release.Namespace }}
  labels:
    {{- include "mcp-k8s-read.labels" . | nindent 4 }}
spec:
  podSelector:
    matchLabels:
      {{- include "mcp-k8s-read.selectorLabels" . | nindent 6 }}
  policyTypes:
    - Ingress
  ingress:
    - from:
        - podSelector:
            matchLabels:
              {{- toYaml .Values.allowedClientLabels | nindent 14 }}
      ports:
        - protocol: TCP
          port: {{ .Values.port }}
```

`deploy/values/kind/mcp-k8s-read.yaml`:
```yaml
# 로컬 티어(kind) — 이미지는 scripts/dev-cluster.sh 가 빌드해 kind load 로 넣는다(레지스트리 없음).
image:
  repository: hoa-mcp
  tag: 0.1.0
  pullPolicy: IfNotPresent
```

- [ ] **Step 4: 통과 확인**

Run: `helm lint deploy/helm/mcp-k8s-read --values deploy/values/kind/mcp-k8s-read.yaml`
Expected: `1 chart(s) linted, 0 chart(s) failed`

Run: `uv run pytest -m charts -q`
Expected: PASS(10개)

Run: `helm template mcp-k8s-read deploy/helm/mcp-k8s-read --namespace hoa-system --values deploy/values/kind/mcp-k8s-read.yaml | grep -A1 "HOA_MCP_ALLOWED_HOSTS"`
Expected: `value: "hoa-mcp-k8s-read.hoa-system.svc,hoa-mcp-k8s-read.hoa-system.svc.cluster.local,127.0.0.1:*,localhost:*"`

- [ ] **Step 5: 커밋**

```bash
git add deploy/helm/mcp-k8s-read deploy/values/kind/mcp-k8s-read.yaml deploy/tests/test_charts.py
git commit -m "[Feat] MCP k8s-read 차트 — ServiceAccount·읽기 RBAC·HTTP 서버·NetworkPolicy(에이전트만)"
```

---

### Task 12: 에이전트 차트

**Files:**
- Create: `deploy/helm/agent/Chart.yaml`, `values.yaml`, `templates/_helpers.tpl`, `templates/deployment.yaml`, `templates/service.yaml`, `templates/networkpolicy.yaml`
- Create: `deploy/values/kind/agent.yaml`
- Modify: `deploy/tests/test_charts.py`

- [ ] **Step 1: 실패하는 테스트**

`deploy/tests/test_charts.py`의 `CHARTS`에 에이전트 차트를 더한다.

전:
```python
CHARTS = {"demo-app": "demo", "mcp-k8s-read": "hoa-system"}
```
후:
```python
CHARTS = {"demo-app": "demo", "mcp-k8s-read": "hoa-system", "agent": "hoa-system"}
```

파일 끝에 더한다:
```python
def test_agent_reads_llm_settings_only_from_the_existing_secret(
    manifests: list[Manifest],
) -> None:
    agent = deployment(manifests, "hoa-agent")
    [container] = containers(agent)
    assert container["envFrom"] == [{"secretRef": {"name": "hoa-agent-llm"}}]
    assert not [name for name in env_of(agent) if "KEY" in name or "BASE_URL" in name]


def test_agent_calls_the_mcp_service_name_the_mcp_chart_accepts(
    manifests: list[Manifest],
) -> None:
    url = env_of(deployment(manifests, "hoa-agent"))["HOA_MCP_URL"]
    allowed = env_of(deployment(manifests, "hoa-mcp-k8s-read"))["HOA_MCP_ALLOWED_HOSTS"]
    assert url == "http://hoa-mcp-k8s-read.hoa-system.svc/mcp"
    assert url.split("/")[2] in allowed.split(",")


def test_agent_pods_are_the_clients_the_mcp_network_policy_lets_in(
    manifests: list[Manifest],
) -> None:
    [policy] = [
        m
        for m in manifests
        if m["kind"] == "NetworkPolicy" and m["metadata"]["name"] == "hoa-mcp-k8s-read"
    ]
    allowed = policy["spec"]["ingress"][0]["from"][0]["podSelector"]["matchLabels"]
    labels = deployment(manifests, "hoa-agent")["spec"]["template"]["metadata"]["labels"]
    assert all(labels.get(key) == value for key, value in allowed.items())


def test_servers_bind_all_interfaces_only_inside_the_pod(manifests: list[Manifest]) -> None:
    [agent] = containers(deployment(manifests, "hoa-agent"))
    assert agent["command"][agent["command"].index("--host") + 1] == "0.0.0.0"
    assert env_of(deployment(manifests, "hoa-mcp-k8s-read"))["HOA_MCP_HOST"] == "0.0.0.0"


def test_nothing_in_the_cluster_may_call_the_agent_yet(manifests: list[Manifest]) -> None:
    [policy] = [
        m
        for m in manifests
        if m["kind"] == "NetworkPolicy" and m["metadata"]["name"] == "hoa-agent"
    ]
    assert policy["spec"]["policyTypes"] == ["Ingress"]
    assert policy["spec"].get("ingress", []) == []
```

- [ ] **Step 2: 실패 확인**

Run: `uv run pytest -m charts -q`
Expected: FAIL — `path "…/deploy/helm/agent" not found`

- [ ] **Step 3: 에이전트 차트**

`deploy/helm/agent/Chart.yaml`:
```yaml
apiVersion: v2
name: agent
description: 운영 에이전트 조사 API(hoa serve) — 경보 문장을 받아 MCP 도구로 조사하고 진단 JSON을 돌려준다
type: application
version: 0.1.0
appVersion: "0.1.0"
```

`deploy/helm/agent/values.yaml`:
```yaml
# 티어마다 다른 값(이미지·LLM Secret 이름)은 deploy/values/<티어>/agent.yaml 이 정한다 — 여기에는 기본값을 두지 않는다.
image:
  repository: ""
  tag: ""
  pullPolicy: IfNotPresent
# gemma(기본, 회사 GPU의 vLLM) 또는 gemini — hoa_agent/llm.py 의 설정 묶음 이름
model: gemma
investigationTimeoutSeconds: 300
# LLM 설정(HOA_GEMMA_BASE_URL·GEMINI_API_KEY·HOA_GEMINI_MODEL)을 담은 Secret의 이름 — 차트 밖에서 만든다
# (kind: scripts/dev-cluster.sh 가 .env 에서, GPU 티어: SOPS — round02b)
existingSecret: ""
mcpUrl: http://hoa-mcp-k8s-read.hoa-system.svc/mcp
port: 8080
resources:
  requests:
    cpu: 100m
    memory: 256Mi
  limits:
    cpu: "1"
    memory: 768Mi
securityContext:
  runAsNonRoot: true
  runAsUser: 65532
  runAsGroup: 65532
  allowPrivilegeEscalation: false
  readOnlyRootFilesystem: true
  capabilities:
    drop: [ALL]
  seccompProfile:
    type: RuntimeDefault
```

`deploy/helm/agent/templates/_helpers.tpl`:
```
{{/* 리소스 이름 — MCP 차트의 allowedClientLabels와 통합 테스트가 이 이름을 쓴다 */}}
{{- define "agent.name" -}}
hoa-agent
{{- end }}

{{- define "agent.selectorLabels" -}}
app.kubernetes.io/name: {{ include "agent.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end }}

{{- define "agent.labels" -}}
{{ include "agent.selectorLabels" . }}
app.kubernetes.io/part-of: hoa
app.kubernetes.io/managed-by: {{ .Release.Service }}
helm.sh/chart: {{ printf "%s-%s" .Chart.Name .Chart.Version }}
{{- end }}

{{- define "agent.image" -}}
{{ required "image.repository is required — set it in the tier values file" .Values.image.repository }}:{{ required "image.tag is required — set it in the tier values file" .Values.image.tag }}
{{- end }}
```

`deploy/helm/agent/templates/deployment.yaml`:
```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: {{ include "agent.name" . }}
  namespace: {{ .Release.Namespace }}
  labels:
    {{- include "agent.labels" . | nindent 4 }}
spec:
  # API가 동시에 1건만 조사한다 — 복제본을 늘리면 그만큼 동시에 조사한다
  replicas: 1
  selector:
    matchLabels:
      {{- include "agent.selectorLabels" . | nindent 6 }}
  template:
    metadata:
      labels:
        {{- include "agent.selectorLabels" . | nindent 8 }}
    spec:
      # 쿠버네티스 API를 부르지 않는다 — 클러스터는 MCP 도구로만 본다
      automountServiceAccountToken: false
      containers:
        - name: agent
          image: {{ include "agent.image" . }}
          imagePullPolicy: {{ .Values.image.pullPolicy }}
          # Service·kubelet 프로브가 파드 IP로 들어오므로 모든 인터페이스에 묶는다 — hoa serve 기본값은 127.0.0.1
          command:
            - hoa
            - serve
            - --host
            - "0.0.0.0"
            - --port
            - {{ .Values.port | quote }}
          env:
            - name: HOA_MODEL
              value: {{ .Values.model | quote }}
            - name: HOA_MCP_URL
              value: {{ .Values.mcpUrl | quote }}
            - name: HOA_INVESTIGATION_TIMEOUT
              value: {{ .Values.investigationTimeoutSeconds | quote }}
          # 비밀값은 차트·values에 두지 않는다 — 이름으로만 참조한다
          envFrom:
            - secretRef:
                name: {{ required "existingSecret is required — the LLM settings live in a Secret made outside the chart" .Values.existingSecret }}
          ports:
            - name: http
              containerPort: {{ .Values.port }}
          # 프로세스만 본다 — LLM·MCP가 죽어도 재시작하지 않고 조사 요청에 503으로 알린다
          readinessProbe:
            httpGet:
              path: /healthz
              port: http
            periodSeconds: 5
          livenessProbe:
            httpGet:
              path: /healthz
              port: http
            periodSeconds: 10
          resources:
            {{- toYaml .Values.resources | nindent 12 }}
          securityContext:
            {{- toYaml .Values.securityContext | nindent 12 }}
          volumeMounts:
            - name: tmp
              mountPath: /tmp
      # 루트 파일시스템이 읽기 전용이라 임시 파일을 쓰는 라이브러리를 위해 /tmp만 쓰게 둔다
      volumes:
        - name: tmp
          emptyDir: {}
```

`deploy/helm/agent/templates/service.yaml`:
```yaml
apiVersion: v1
kind: Service
metadata:
  name: {{ include "agent.name" . }}
  namespace: {{ .Release.Namespace }}
  labels:
    {{- include "agent.labels" . | nindent 4 }}
spec:
  selector:
    {{- include "agent.selectorLabels" . | nindent 4 }}
  ports:
    - name: http
      port: 80
      targetPort: http
```

`deploy/helm/agent/templates/networkpolicy.yaml`:
```yaml
# round02a에서 이 API를 부르는 쪽은 kubectl port-forward뿐이다(NetworkPolicy 밖) — 인그레스를 모두 막는다.
# Alertmanager 웹훅이 들어오는 round04에 그 파드만 연다.
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: {{ include "agent.name" . }}
  namespace: {{ .Release.Namespace }}
  labels:
    {{- include "agent.labels" . | nindent 4 }}
spec:
  podSelector:
    matchLabels:
      {{- include "agent.selectorLabels" . | nindent 6 }}
  policyTypes:
    - Ingress
  ingress: []
```

`deploy/values/kind/agent.yaml`:
```yaml
# 로컬 티어(kind) — 이미지는 scripts/dev-cluster.sh 가 빌드해 kind load 로 넣는다(레지스트리 없음).
image:
  repository: hoa-agent
  tag: 0.1.0
  pullPolicy: IfNotPresent
# scripts/dev-cluster.sh up 이 .env 의 LLM 변수로 만든다 — .env 가 없으면 빈 Secret이라 조사 요청이 503(setup_error)으로 알린다
existingSecret: hoa-agent-llm
```

- [ ] **Step 4: 통과 확인**

Run: `helm lint deploy/helm/agent --values deploy/values/kind/agent.yaml`
Expected: `1 chart(s) linted, 0 chart(s) failed`

Run: `uv run pytest -m charts -q`
Expected: PASS(16개)

- [ ] **Step 5: 커밋**

```bash
git add deploy/helm/agent deploy/values/kind/agent.yaml deploy/tests/test_charts.py
git commit -m "[Feat] 에이전트 차트 — hoa serve Deployment·Service·NetworkPolicy(인그레스 없음)·LLM Secret 참조"
```

---

### Task 13: 로컬 티어 스크립트 — 이미지 셋·LLM Secret·helm 설치·복구

**Files:**
- Modify: `scripts/dev-cluster.sh`(전체)
- Delete: `deploy/kind/demo/`, `deploy/kind/rbac/`

이 Task에서 kind 클러스터를 지우고 다시 만든다(로컬 개발 클러스터다). 기존 매니페스트로 올린 리소스에는 Helm 소유 표시가 없어 `helm install`이 거절하기 때문이다.

- [ ] **Step 1: 스크립트 전체를 바꾼다**

`scripts/dev-cluster.sh`:
```bash
#!/usr/bin/env bash
# 로컬 티어 kind 개발 클러스터 — 만들기·지우기·장애 주입·복구·MCP용 읽기 전용 kubeconfig.
# 사용: bash scripts/dev-cluster.sh <up|down|fault <image-pull|bad-config>|reset|mcp-kubeconfig>
# 모든 kubectl·helm 호출은 컨텍스트 kind-hoa 를 명시한다 — 다른 클러스터(회사 서버 등)를 건드리지 않는다.
# Windows Git Bash는 '/'로 시작하는 인자를 Windows 경로로 바꾸므로, 저장소 루트로 옮겨 가서 상대 경로만 쓴다.
set -euo pipefail

CLUSTER=hoa
CONTEXT="kind-${CLUSTER}"
KIND_VERSION=v0.33.0
# Helm 4 — 새 릴리스를 server-side apply로 올린다(release 함수의 --force-conflicts 참고)
HELM_VERSION=v4.3.2
NODE_IMAGE="kindest/node:v1.37.0@sha256:a1ed56cfb0e7b93589bdf97c8cd566405a265939e3620fc4f5de89adff580ae5"
IMAGE_TAG=0.1.0
# 이미지 이름:워크스페이스 패키지:멤버 폴더 — 모두 deploy/docker/Dockerfile 하나로 만든다
IMAGES=(hoa-demo:hoa-demo:demo_app hoa-mcp:hoa-mcp:mcp_servers hoa-agent:hoa-agent:agent)
DEMO_DEPLOYMENTS=(inventory orders gateway)
SYSTEM_DEPLOYMENTS=(hoa-mcp-k8s-read hoa-agent)
LLM_SECRET=hoa-agent-llm
# .env 에서 클러스터 안 에이전트에 넘기는 변수 — 이것만 Secret에 담는다
LLM_KEYS=(HOA_GEMMA_BASE_URL GEMINI_API_KEY HOA_GEMINI_MODEL)
MCP_KUBECONFIG="${HOA_MCP_KUBECONFIG:-${HOME}/.kube/hoa-kind-mcp-read.kubeconfig}"

cd "$(dirname "${BASH_SOURCE[0]}")/.."

k() {
  kubectl --context "${CONTEXT}" "$@"
}

usage() {
  echo "사용: bash scripts/dev-cluster.sh <up|down|fault <image-pull|bad-config>|reset|mcp-kubeconfig>" >&2
}

check_kind_version() {
  local installed
  installed="$(kind version | awk '{print $2}')"
  if [[ "${installed}" != "${KIND_VERSION}" ]]; then
    echo "kind ${KIND_VERSION}이 필요하다(설치된 버전: ${installed})" >&2
    exit 1
  fi
}

check_helm_version() {
  local installed
  installed="$(helm version --template '{{.Version}}')"
  if [[ "${installed}" != "${HELM_VERSION}" ]]; then
    echo "helm ${HELM_VERSION}이 필요하다(설치된 버전: ${installed})" >&2
    exit 1
  fi
}

# round02a 전(kubectl apply)에 만든 클러스터는 Helm 소유 표시가 없어 helm 설치가 거절된다
check_helm_owned() {
  local found owner
  found="$(k -n demo get deployment inventory --ignore-not-found -o name)"
  owner="$(k -n demo get deployment inventory --ignore-not-found \
    -o jsonpath='{.metadata.labels.app\.kubernetes\.io/managed-by}')"
  if [[ -n "${found}" && "${owner}" != Helm ]]; then
    echo "이 클러스터의 데모 앱은 Helm 차트 전(kubectl apply)에 올린 것이다 — bash scripts/dev-cluster.sh down 뒤에 up 한다" >&2
    exit 1
  fi
}

# 차트 하나를 kind 값으로 설치하거나 차트의 기준 상태로 되돌린다.
# Helm 4는 새 릴리스를 server-side apply로 올린다. kubectl patch(장애 주입)가 가져간 필드는
# --force-conflicts 가 있어야 차트 값으로 되찾는다(평가 러너 hoa_eval.cluster.baseline_release 와 같은 인자).
release() {
  local chart="$1" namespace="$2"
  helm --kube-context "${CONTEXT}" upgrade --install "${chart}" "deploy/helm/${chart}" \
    --namespace "${namespace}" --values "deploy/values/kind/${chart}.yaml" \
    --server-side=true --force-conflicts
}

build_images() {
  local entry name package member
  for entry in "${IMAGES[@]}"; do
    IFS=: read -r name package member <<<"${entry}"
    docker build -f deploy/docker/Dockerfile --build-arg "PACKAGE=${package}" \
      --build-arg "MEMBER=${member}" -t "${name}:${IMAGE_TAG}" .
    kind load docker-image "${name}:${IMAGE_TAG}" --name "${CLUSTER}"
  done
}

# .env 에서 LLM_KEYS 만 골라 Secret 매니페스트를 표준출력으로 낸다 — 값이 파일·명령 인자·화면에 남지 않는다.
# .env 가 없거나 값이 비면 빈 Secret이다(조사 요청이 503 setup_error로 무엇이 없는지 알린다).
llm_secret_manifest() {
  local line key value wanted
  printf 'apiVersion: v1\nkind: Secret\nmetadata:\n  name: %s\n  namespace: hoa-system\ntype: Opaque\ndata:\n' \
    "${LLM_SECRET}"
  [[ -f .env ]] || return 0
  while IFS= read -r line || [[ -n "${line}" ]]; do
    line="${line%$'\r'}"
    [[ "${line}" == *=* ]] || continue
    key="${line%%=*}"
    value="${line#*=}"
    if [[ "${value}" == \"*\" || "${value}" == \'*\' ]]; then
      value="${value:1:${#value}-2}"
    fi
    for wanted in "${LLM_KEYS[@]}"; do
      if [[ "${key}" == "${wanted}" && -n "${value}" ]]; then
        printf '  %s: %s\n' "${key}" "$(printf '%s' "${value}" | base64 | tr -d '\n')"
      fi
    done
  done <.env
}

wait_rollouts() {
  local name
  for name in "${DEMO_DEPLOYMENTS[@]}"; do
    k -n demo rollout status "deployment/${name}" --timeout=180s
  done
}

wait_system_rollouts() {
  local name
  for name in "${SYSTEM_DEPLOYMENTS[@]}"; do
    k -n hoa-system rollout status "deployment/${name}" --timeout=180s
  done
}

# rollout status는 새 파드만 기다린다 — 종료 중인 옛 파드가 남으면 바로 뒤의 장애 주입·조사에 섞인다
wait_settled() {
  local left="" i
  for ((i = 0; i < 40; i++)); do
    left="$(k -n demo get pods -o jsonpath='{range .items[?(@.metadata.deletionTimestamp)]}{.metadata.name}{" "}{end}')"
    if [[ -z "${left}" ]]; then
      return 0
    fi
    sleep 3
  done
  echo "복구 뒤에도 종료 중인 파드가 남았다: ${left}" >&2
  return 1
}

cmd_up() {
  local existed=true clusters
  check_kind_version
  check_helm_version
  # 목록을 먼저 받아 둔다 — kind get clusters | grep -q 는 pipefail 아래에서 SIGPIPE로 실패할 수 있다
  clusters="$(kind get clusters)"
  if grep -qx "${CLUSTER}" <<<"${clusters}"; then
    # 클러스터는 있는데 kubeconfig에 컨텍스트가 없을 때를 대비해 다시 써 둔다
    kind export kubeconfig --name "${CLUSTER}"
    check_helm_owned
  else
    existed=false
    # 새로 만들면 사용자 kubeconfig의 current-context가 kind-hoa로 바뀐다(이 스크립트는 컨텍스트를 명시해서 쓴다)
    kind create cluster --name "${CLUSTER}" --image "${NODE_IMAGE}" \
      --config deploy/kind/kind-config.yaml --wait 120s
  fi
  k apply -f deploy/kind/namespaces.yaml
  build_images
  llm_secret_manifest | k apply -f -
  release demo-app demo
  release mcp-k8s-read hoa-system
  release agent hoa-system
  if [[ "${existed}" == true ]]; then
    # 태그가 같아 helm만으로는 새로 넣은 이미지·바뀐 Secret으로 파드가 바뀌지 않는다
    k -n demo rollout restart deployment
    k -n hoa-system rollout restart deployment
  fi
  wait_rollouts
  wait_system_rollouts
  cmd_mcp_kubeconfig
}

cmd_down() {
  kind delete cluster --name "${CLUSTER}"
}

cmd_fault() {
  local name="${1:-}" target
  case "${name}" in
    image-pull) target=orders ;;
    bad-config) target=inventory ;;
    *)
      usage
      exit 2
      ;;
  esac
  k -n demo patch "deployment/${target}" --type strategic \
    --patch-file "deploy/kind/faults/${name}.yaml"
  echo "장애 ${name}을(를) deployment/${target}에 넣었다 — 되돌리기: bash scripts/dev-cluster.sh reset"
}

# 데모 앱을 차트의 기준 상태로 되돌린다 — 장애 패치는 차트에 이미 있는 필드(이미지 태그·환경변수 값)만 바꾸고,
# helm이 그 필드를 차트 값으로 되찾는다.
cmd_reset() {
  check_helm_version
  release demo-app demo
  # 진행 기한(progressDeadlineSeconds)을 넘긴 장애도 rollout status가 실패하지 않게 새 ReplicaSet으로 다시 시작한다
  k -n demo rollout restart deployment
  wait_rollouts
  wait_settled
}

cmd_mcp_kubeconfig() {
  local server ca token
  server="$(k config view --minify --raw -o jsonpath='{.clusters[0].cluster.server}')"
  ca="$(k config view --minify --raw -o jsonpath='{.clusters[0].cluster.certificate-authority-data}')"
  token="$(k -n hoa-system create token hoa-mcp-read --duration=12h)"
  local tmp
  mkdir -p "$(dirname "${MCP_KUBECONFIG}")"
  tmp="${MCP_KUBECONFIG}.tmp"
  (
    umask 077
    cat >"${tmp}" <<EOF
apiVersion: v1
kind: Config
clusters:
  - name: ${CONTEXT}
    cluster:
      server: ${server}
      certificate-authority-data: ${ca}
users:
  - name: hoa-mcp-read
    user:
      token: ${token}
contexts:
  - name: hoa-mcp-read@${CONTEXT}
    context:
      cluster: ${CONTEXT}
      user: hoa-mcp-read
      namespace: demo
current-context: hoa-mcp-read@${CONTEXT}
EOF
  )
  # 이미 있던 파일을 덮어써도 권한이 600이 되도록 새 파일에 쓰고 옮긴다
  chmod 600 "${tmp}"
  mv -f "${tmp}" "${MCP_KUBECONFIG}"
  echo "MCP용 읽기 전용 kubeconfig: ${MCP_KUBECONFIG} (토큰 12시간 유효)"
}

case "${1:-}" in
  up) cmd_up ;;
  down) cmd_down ;;
  fault)
    shift
    cmd_fault "$@"
    ;;
  reset) cmd_reset ;;
  mcp-kubeconfig) cmd_mcp_kubeconfig ;;
  *)
    usage
    exit 2
    ;;
esac
```

Run: `git rm -r -q deploy/kind/demo deploy/kind/rbac && uv run pre-commit run shellcheck --files scripts/dev-cluster.sh`
Expected: `shellcheck....Passed`

- [ ] **Step 2: 예전 클러스터 안내 확인 → 다시 만들기**

Run: `bash scripts/dev-cluster.sh up; echo "exit=$?"`
Expected(round01b 때 만든 클러스터가 있을 때): `이 클러스터의 데모 앱은 Helm 차트 전(kubectl apply)에 올린 것이다 — …`, `exit=1`. 클러스터가 없으면 이 단계는 바로 Step 3의 결과가 된다.

Run: `bash scripts/dev-cluster.sh down && bash scripts/dev-cluster.sh up`
Expected: 세 이미지 빌드·`kind load`, `secret/hoa-agent-llm created`, 릴리스 셋 `STATUS: deployed`, 다섯 Deployment `successfully rolled out`, `MCP용 읽기 전용 kubeconfig: …`.

Run: `kubectl --context kind-hoa get pods -n demo && kubectl --context kind-hoa get pods -n hoa-system`
Expected: 다섯 파드 모두 `1/1 Running`.

Run: `kubectl --context kind-hoa -n hoa-system get secret hoa-agent-llm -o go-template='{{range $k, $v := .data}}{{$k}}{{"\n"}}{{end}}'`
Expected: 키 이름만(`.env`에 값이 있는 것 — 예: `GEMINI_API_KEY`, `HOA_GEMMA_BASE_URL`). 값은 출력하지 않는다.

- [ ] **Step 3: server-side apply 충돌을 직접 보고, `--force-conflicts`로 되찾는다**

교본과 반복 함정에 쓸 실제 근거다. 먼저 `--force-conflicts` 없이 되돌려 본다.

Run:
```bash
bash scripts/dev-cluster.sh fault image-pull
helm --kube-context kind-hoa upgrade --install demo-app deploy/helm/demo-app --namespace demo \
  --values deploy/values/kind/demo-app.yaml --server-side=true; echo "exit=$?"
```
Expected: `exit=1`과 충돌 오류 — 필드 관리자 `kubectl-patch`가 `.spec.template.spec.containers[name="orders"].image`를 갖고 있다는 내용. **오류 문장을 그대로 적어 둔다**(Task 18의 반복 함정 12번). 오류 없이 이미지가 `hoa-demo:0.1.0`으로 돌아왔다면 그 사실을 적고 계속한다 — `--force-conflicts`는 그때도 해가 없다.

Run: `bash scripts/dev-cluster.sh reset && kubectl --context kind-hoa -n demo get deployment orders -o jsonpath='{.spec.template.spec.containers[0].image}'; echo`
Expected: 세 Deployment `successfully rolled out`, 마지막 줄 `hoa-demo:0.1.0`

Run: `bash scripts/dev-cluster.sh fault bad-config && bash scripts/dev-cluster.sh reset && kubectl --context kind-hoa -n demo get deployment inventory -o jsonpath='{.spec.template.spec.containers[0].env[?(@.name=="HOA_DEMO_PORT")].value}'; echo`
Expected: 마지막 줄 `8080`

- [ ] **Step 4: 클러스터 안 두 서버의 헬스 체크**

Run:
```bash
kubectl --context kind-hoa -n hoa-system port-forward service/hoa-agent 18080:80 >/dev/null 2>&1 &
agent_pf=$!
kubectl --context kind-hoa -n hoa-system port-forward service/hoa-mcp-k8s-read 18081:80 >/dev/null 2>&1 &
mcp_pf=$!
sleep 3
curl -s http://127.0.0.1:18080/healthz; echo
curl -s http://127.0.0.1:18081/healthz; echo
kill "${agent_pf}" "${mcp_pf}"
```
Expected: `{"status":"ok"}`와 `ok`

Run: `kubectl --context kind-hoa -n hoa-system logs deployment/hoa-mcp-k8s-read --tail=20`
Expected: Traceback이 없다.

- [ ] **Step 5: 커밋**

```bash
git add scripts/dev-cluster.sh deploy/kind
git commit -m "[Feat] dev-cluster.sh — 이미지 셋·.env의 LLM Secret·helm 설치와 복구(--force-conflicts), 일반 매니페스트 제거"
```

---

### Task 14: 평가 러너와 MCP 통합 테스트의 복구를 helm으로 (TDD)

**Files:**
- Modify: `eval/src/hoa_eval/cluster.py`
- Modify: `eval/tests/test_cluster.py`, `eval/tests/test_cli.py`, `eval/tests/test_scenario.py`
- Modify: `mcp_servers/tests/integration/test_kind_cluster.py`

- [ ] **Step 1: 실패하는 테스트**

`eval/tests/test_cluster.py`의 import를 바꾼다.

전:
```python
import json
import subprocess

import pytest

from hoa_eval import cluster
from hoa_eval.cluster import (
    ClusterError,
    ContainerStatus,
    DemoCluster,
    Kubectl,
    SymptomTimeout,
    container_statuses,
    symptom_met,
)
```
후:
```python
import json
import subprocess
from pathlib import Path

import pytest

from hoa_eval import cluster
from hoa_eval.cluster import (
    ClusterError,
    ContainerStatus,
    DemoCluster,
    Helm,
    Kubectl,
    SymptomTimeout,
    baseline_release,
    container_statuses,
    symptom_met,
)
```

`FakeKubectl` 클래스 아래에 더한다:
```python
class FakeHelm:
    def __init__(self) -> None:
        self.calls: list[tuple[str, ...]] = []

    def __call__(self, *args: str) -> str:
        self.calls.append(args)
        return ""
```

`test_reset_reapplies_restarts_waits_for_old_pods_and_clears_events` 전체를 바꾼다.

전:
```python
def test_reset_reapplies_restarts_waits_for_old_pods_and_clears_events() -> None:
    clock = FakeClock()
    kubectl = FakeKubectl([pod_list(False, True), pod_list(False)])

    DemoCluster(kubectl, sleep=clock.sleep, clock=clock).reset()

    assert kubectl.calls[0][0] == "apply"
    assert kubectl.calls[1] == ("-n", "demo", "rollout", "restart", "deployment")
    assert [c[4] for c in kubectl.calls[2:5]] == [
        "deployment/inventory",
        "deployment/orders",
        "deployment/gateway",
    ]
    assert kubectl.calls[-1] == ("-n", "demo", "delete", "events", "--all")
    assert len(kubectl.calls) == 8
    assert clock.now == 3.0
```
후:
```python
def test_reset_restores_the_chart_baseline_restarts_and_clears_events() -> None:
    clock = FakeClock()
    kubectl = FakeKubectl([pod_list(False, True), pod_list(False)])
    helm = FakeHelm()

    DemoCluster(kubectl, helm=helm, sleep=clock.sleep, clock=clock).reset()

    assert helm.calls == [baseline_release()]
    assert kubectl.calls[0] == ("-n", "demo", "rollout", "restart", "deployment")
    assert [c[4] for c in kubectl.calls[1:4]] == [
        "deployment/inventory",
        "deployment/orders",
        "deployment/gateway",
    ]
    assert kubectl.calls[-1] == ("-n", "demo", "delete", "events", "--all")
    assert len(kubectl.calls) == 7
    assert clock.now == 3.0
```

`test_reset_fails_when_old_pods_never_leave`의 생성 줄을 바꾼다.

전:
```python
        DemoCluster(kubectl, sleep=clock.sleep, clock=clock).reset()
```
후:
```python
        DemoCluster(kubectl, helm=FakeHelm(), sleep=clock.sleep, clock=clock).reset()
```

파일 끝에 더한다:
```python
def test_helm_names_the_kind_context(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: list[list[str]] = []

    def fake_run(argv: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        seen.append(argv)
        return subprocess.CompletedProcess(argv, 0, stdout="ok", stderr="")

    monkeypatch.setattr(cluster.subprocess, "run", fake_run)

    assert Helm()("list") == "ok"
    assert seen == [["helm", "--kube-context", "kind-hoa", "list"]]


def test_helm_failures_become_cluster_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_run(argv: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(argv, 1, stdout="", stderr="conflict")

    monkeypatch.setattr(cluster.subprocess, "run", fake_run)

    with pytest.raises(ClusterError, match="helm list failed: conflict"):
        Helm()("list")


def test_baseline_release_takes_back_the_fields_a_fault_patch_changed() -> None:
    args = baseline_release()

    assert args[:3] == ("upgrade", "--install", "demo-app")
    assert Path(args[3]).is_dir()
    assert Path(args[args.index("--values") + 1]).is_file()
    assert args[args.index("--namespace") + 1] == "demo"
    assert args[-2:] == ("--server-side=true", "--force-conflicts")
```

`eval/tests/test_cli.py`의 `quiet_cluster` 마지막 줄을 바꾼다(가짜 helm — CI 단위 테스트 잡에는 helm이 없다).

전:
```python
    return DemoCluster(kubectl, sleep=sleep, clock=lambda: now[0])
```
후:
```python
    return DemoCluster(kubectl, helm=lambda *args: "", sleep=sleep, clock=lambda: now[0])
```

`eval/tests/test_scenario.py`의 예시 경로를 지워지지 않는 파일로 바꾼다(`deploy/kind/demo/`는 Task 13에서 지웠다 — 「faults 밖의 실제 파일」이라는 뜻을 지킨다).

전:
```text
        ({"patch": "deploy/kind/demo/20-orders.yaml"}, "under deploy/kind/faults"),
```
후:
```text
        ({"patch": "deploy/kind/kind-config.yaml"}, "under deploy/kind/faults"),
```

- [ ] **Step 2: 실패 확인**

Run: `uv run pytest eval -q`
Expected: FAIL — `ImportError: cannot import name 'Helm'`

- [ ] **Step 3: 구현**

`eval/src/hoa_eval/cluster.py`의 상수와 `Kubectl` 클래스를 바꾼다.

전:
```python
CONTEXT = "kind-hoa"
DEMO_MANIFESTS = REPO_ROOT / "deploy" / "kind" / "demo"
DEMO_DEPLOYMENTS = ("inventory", "orders", "gateway")
KUBECTL_TIMEOUT_SECONDS = 240
```
후:
```python
CONTEXT = "kind-hoa"
DEMO_RELEASE = "demo-app"
DEMO_CHART = REPO_ROOT / "deploy" / "helm" / "demo-app"
DEMO_VALUES = REPO_ROOT / "deploy" / "values" / "kind" / "demo-app.yaml"
DEMO_DEPLOYMENTS = ("inventory", "orders", "gateway")
KUBECTL_TIMEOUT_SECONDS = 240
HELM_TIMEOUT_SECONDS = 240
```

전:
```python
class Kubectl:
    """관리자 컨텍스트를 늘 명시한다 — 개발 PC의 다른 클러스터를 건드리지 않게."""

    def __init__(self, context: str = CONTEXT) -> None:
        self.context = context

    def __call__(self, *args: str) -> str:
        try:
            result = subprocess.run(
                ["kubectl", "--context", self.context, *args],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=KUBECTL_TIMEOUT_SECONDS,
                check=False,
            )
        except (subprocess.TimeoutExpired, FileNotFoundError) as exc:
            raise ClusterError(f"kubectl {' '.join(args)} failed: {exc}") from exc
        if result.returncode != 0:
            raise ClusterError(f"kubectl {' '.join(args)} failed: {result.stderr.strip()}")
        return result.stdout
```
후:
```python
def run_admin(
    tool: str, context_flag: str, context: str, args: tuple[str, ...], timeout: int
) -> str:
    """관리자 도구(kubectl·helm)를 컨텍스트를 명시해 부른다 — 실패는 ClusterError로."""
    try:
        result = subprocess.run(
            [tool, context_flag, context, *args],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            check=False,
        )
    except (subprocess.TimeoutExpired, FileNotFoundError) as exc:
        raise ClusterError(f"{tool} {' '.join(args)} failed: {exc}") from exc
    if result.returncode != 0:
        raise ClusterError(f"{tool} {' '.join(args)} failed: {result.stderr.strip()}")
    return result.stdout


class Kubectl:
    """관리자 컨텍스트를 늘 명시한다 — 개발 PC의 다른 클러스터를 건드리지 않게."""

    def __init__(self, context: str = CONTEXT) -> None:
        self.context = context

    def __call__(self, *args: str) -> str:
        return run_admin("kubectl", "--context", self.context, args, KUBECTL_TIMEOUT_SECONDS)


class Helm:
    """kubectl과 같이 컨텍스트를 명시한다(--kube-context)."""

    def __init__(self, context: str = CONTEXT) -> None:
        self.context = context

    def __call__(self, *args: str) -> str:
        return run_admin("helm", "--kube-context", self.context, args, HELM_TIMEOUT_SECONDS)


def baseline_release() -> tuple[str, ...]:
    """데모 앱을 차트의 기준 상태로 되돌리는 helm 인자 — scripts/dev-cluster.sh 의 release와 같다.
    Helm 4의 server-side apply에서 kubectl patch(장애 주입)가 가져간 필드를 되찾으려면
    --force-conflicts가 필요하다."""
    return (
        "upgrade",
        "--install",
        DEMO_RELEASE,
        str(DEMO_CHART),
        "--namespace",
        DEMO_NAMESPACE,
        "--values",
        str(DEMO_VALUES),
        "--server-side=true",
        "--force-conflicts",
    )
```

`DemoCluster`의 생성자와 `reset`을 바꾼다.

전:
```python
class DemoCluster:
    def __init__(
        self,
        kubectl: Callable[..., str],
        *,
        sleep: Callable[[float], None] = time.sleep,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.kubectl = kubectl
        self.sleep = sleep
        self.clock = clock
```
후:
```python
class DemoCluster:
    def __init__(
        self,
        kubectl: Callable[..., str],
        *,
        helm: Callable[..., str] | None = None,
        sleep: Callable[[float], None] = time.sleep,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.kubectl = kubectl
        self.helm = Helm() if helm is None else helm
        self.sleep = sleep
        self.clock = clock
```

전:
```python
    def reset(self) -> None:
        self.kubectl("apply", "-f", str(DEMO_MANIFESTS))
```
후:
```python
    def reset(self) -> None:
        self.helm(*baseline_release())
```

- [ ] **Step 4: 통과 확인**

Run: `uv run pytest -q && uv run ruff check . && uv run ruff format --check .`
Expected: 모두 통과

- [ ] **Step 5: MCP 통합 테스트의 복구도 helm으로**

`mcp_servers/tests/integration/test_kind_cluster.py`:

전:
```python
CONTEXT = "kind-hoa"
ROOT = Path(__file__).resolve().parents[3]
DEMO_DIR = ROOT / "deploy" / "kind" / "demo"
```
후:
```python
CONTEXT = "kind-hoa"
ROOT = Path(__file__).resolve().parents[3]
DEMO_CHART = ROOT / "deploy" / "helm" / "demo-app"
DEMO_VALUES = ROOT / "deploy" / "values" / "kind" / "demo-app.yaml"
```

`read_only_kubectl` 함수 위에 더한다:
```python
def helm(*args: str) -> str:
    result = subprocess.run(
        ["helm", "--kube-context", CONTEXT, *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=240,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    return result.stdout
```

`injected`의 `finally` 첫 줄을 바꾼다.

전:
```python
        kubectl("apply", "-f", str(DEMO_DIR))
```
후:
```python
        # 차트의 기준 상태로 — dev-cluster.sh reset·평가 러너와 같은 인자
        helm(
            "upgrade",
            "--install",
            "demo-app",
            str(DEMO_CHART),
            "--namespace",
            "demo",
            "--values",
            str(DEMO_VALUES),
            "--server-side=true",
            "--force-conflicts",
        )
```

- [ ] **Step 6: 통합 테스트(기존 8개)**

Run: `uv run pytest -m integration -q`
Expected: PASS(8개) — 차트로 올린 kind에서 기존 MCP·에이전트 배선·러너 테스트가 그대로 돈다. 러너 테스트가 helm으로 복구한다.

- [ ] **Step 7: 커밋**

```bash
git add eval mcp_servers/tests/integration/test_kind_cluster.py
git commit -m "[Feat] 평가 러너·MCP 통합 테스트의 복구를 데모 앱 차트로(helm --force-conflicts)"
```

---

### Task 15: 통합 테스트 — 클러스터 안 MCP 서버 (kind)

**Files:**
- Create: `mcp_servers/tests/integration/test_in_cluster.py`

- [ ] **Step 1: 테스트**

`mcp_servers/tests/integration/test_in_cluster.py`:
```python
import re
import subprocess
import threading
from collections.abc import Iterator
from contextlib import contextmanager

import httpx
import pytest
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client
from mcp.types import CallToolResult

pytestmark = pytest.mark.integration

CONTEXT = "kind-hoa"
SYSTEM_NAMESPACE = "hoa-system"
SERVICE = "hoa-mcp-k8s-read"
SERVICE_ACCOUNT = f"system:serviceaccount:{SYSTEM_NAMESPACE}:hoa-mcp-read"
TOOLS_LIST = {"jsonrpc": "2.0", "id": 1, "method": "tools/list"}


@contextmanager
def port_forward(namespace: str, service: str, port: int) -> Iterator[int]:
    """kubectl port-forward를 띄우고 고른 로컬 포트를 돌려준다 — NetworkPolicy 밖이다."""
    process = subprocess.Popen(
        [
            "kubectl",
            "--context",
            CONTEXT,
            "-n",
            namespace,
            "port-forward",
            f"service/{service}",
            f":{port}",
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    assert process.stdout is not None
    output = process.stdout
    drain: threading.Thread | None = None
    try:
        first = output.readline()
        match = re.search(r"127\.0\.0\.1:(\d+)", first)
        if match is None:
            pytest.fail(f"kubectl port-forward did not start: {first}{output.read()}")
        # 연결마다 찍히는 "Handling connection for …" 줄이 파이프를 채우면 kubectl이 멈춘다
        # — 끝날 때까지 계속 읽어 버린다
        drain = threading.Thread(target=output.read, daemon=True)
        drain.start()
        yield int(match.group(1))
    finally:
        process.terminate()
        process.wait(timeout=10)
        if drain is not None:
            drain.join(timeout=10)
        output.close()


@pytest.fixture(scope="module")
def mcp_port() -> Iterator[int]:
    with port_forward(SYSTEM_NAMESPACE, SERVICE, 80) as port:
        yield port


async def call(port: int, tool: str, arguments: dict[str, object]) -> CallToolResult:
    async with (
        httpx.AsyncClient(timeout=30) as client,
        streamable_http_client(f"http://127.0.0.1:{port}/mcp", http_client=client) as (
            read,
            write,
            _,
        ),
        ClientSession(read, write) as session,
    ):
        await session.initialize()
        return await session.call_tool(tool, arguments)


@pytest.mark.anyio
async def test_in_cluster_server_lists_demo_pods_with_its_service_account(mcp_port: int) -> None:
    result = await call(mcp_port, "list_pods", {"namespace": "demo"})
    assert result.isError is False
    names = {pod["name"].rsplit("-", 2)[0] for pod in result.structuredContent["pods"]}
    assert names == {"gateway", "orders", "inventory"}


@pytest.mark.anyio
async def test_in_cluster_server_refuses_namespaces_outside_its_allowlist(mcp_port: int) -> None:
    result = await call(mcp_port, "list_pods", {"namespace": "kube-system"})
    assert result.isError is True


def test_in_cluster_server_rejects_unknown_host_headers(mcp_port: int) -> None:
    response = httpx.post(
        f"http://127.0.0.1:{mcp_port}/mcp",
        json=TOOLS_LIST,
        headers={"Host": "evil.example", "Accept": "application/json, text/event-stream"},
        timeout=30,
    )
    assert response.status_code == 421


@pytest.mark.parametrize(
    ("verb", "resource", "namespace", "allowed"),
    [
        ("list", "pods", "demo", "yes"),
        ("get", "pods/log", "demo", "yes"),
        ("list", "replicasets", "demo", "yes"),
        ("get", "secrets", "demo", "no"),
        ("list", "configmaps", "demo", "no"),
        ("delete", "pods", "demo", "no"),
        ("list", "pods", "kube-system", "no"),
    ],
)
def test_service_account_reads_only_what_the_tools_need(
    verb: str, resource: str, namespace: str, allowed: str
) -> None:
    result = subprocess.run(
        [
            "kubectl",
            "--context",
            CONTEXT,
            "auth",
            "can-i",
            verb,
            resource,
            "-n",
            namespace,
            "--as",
            SERVICE_ACCOUNT,
        ],
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    assert result.stdout.strip() == allowed
```

- [ ] **Step 2: 실행**

Run: `uv run ruff check mcp_servers && uv run ruff format --check mcp_servers && uv run pytest -m integration mcp_servers/tests/integration/test_in_cluster.py -q`
Expected: PASS(10개)

- [ ] **Step 3: 커밋**

```bash
git add mcp_servers/tests/integration/test_in_cluster.py
git commit -m "[Test] 통합 — 클러스터 안 MCP 서버(포트포워드·Host 검사·ServiceAccount 권한)"
```

---

### Task 16: 통합 테스트 — 에이전트 파드 → 가짜 LLM → MCP 파드, NetworkPolicy (kind)

**Files:**
- Create: `agent/tests/integration/fake_llm.py`
- Create: `agent/tests/integration/test_agent_api_kind.py`

- [ ] **Step 1: 가짜 OpenAI 호환 서버**

`agent/tests/integration/fake_llm.py`:
```python
"""통합 테스트용 가짜 OpenAI 호환 서버 — 표준 라이브러리만 쓴다.

ConfigMap으로 넣어 에이전트 이미지의 Python으로 돌린다(이미지를 따로 받지 않는다).
대본: 도구 결과가 없으면 list_pods, 하나면 get_events, 둘이면 글로 답한다.
구조화 출력 요청(response_format)에는 진단 JSON을 낸다.
"""

import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

PORT = 8080
DIAGNOSIS = {
    "cause_label": "unknown",
    "target": "demo/gateway",
    "evidence": [{"tool": "list_pods", "quote": "gateway"}],
    "confidence": 0.1,
    "summary_ko": "가짜 LLM의 대본 진단이다. 배선만 확인한다.",
}


def tool_call(name: str, arguments: dict[str, str], call_id: str) -> dict[str, object]:
    return {
        "id": call_id,
        "type": "function",
        "function": {"name": name, "arguments": json.dumps(arguments)},
    }


def answer(body: dict[str, object]) -> dict[str, object]:
    if body.get("response_format"):
        return {"role": "assistant", "content": json.dumps(DIAGNOSIS)}
    messages = body.get("messages")
    done = 0
    if isinstance(messages, list):
        done = sum(1 for m in messages if isinstance(m, dict) and m.get("role") == "tool")
    if done == 0:
        call = tool_call("list_pods", {"namespace": "demo"}, "call-1")
        return {"role": "assistant", "content": None, "tool_calls": [call]}
    if done == 1:
        call = tool_call("get_events", {"namespace": "demo"}, "call-2")
        return {"role": "assistant", "content": None, "tool_calls": [call]}
    return {"role": "assistant", "content": "The demo pods were listed and their events read."}


def completion(body: dict[str, object]) -> dict[str, object]:
    message = answer(body)
    return {
        "id": "chatcmpl-fake",
        "object": "chat.completion",
        "created": 0,
        "model": str(body.get("model", "fake")),
        "choices": [
            {
                "index": 0,
                "message": message,
                "finish_reason": "tool_calls" if "tool_calls" in message else "stop",
            }
        ],
        "usage": {"prompt_tokens": 1000, "completion_tokens": 20, "total_tokens": 1020},
    }


class Handler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        if self.path == "/healthz":
            self.reply(200, {"status": "ok"})
        else:
            self.reply(404, {"error": "not found"})

    def do_POST(self) -> None:
        if not self.path.endswith("/chat/completions"):
            self.reply(404, {"error": "not found"})
            return
        length = int(self.headers.get("Content-Length", "0"))
        body = json.loads(self.rfile.read(length) or b"{}")
        self.reply(200, completion(body))

    def reply(self, status: int, payload: dict[str, object]) -> None:
        data = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


if __name__ == "__main__":
    ThreadingHTTPServer(("0.0.0.0", PORT), Handler).serve_forever()
```

- [ ] **Step 2: 테스트**

`agent/tests/integration/test_agent_api_kind.py`:
```python
import base64
import json
import re
import subprocess
import threading
import time
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

import httpx
import pytest

from hoa_agent.mcp_tools import k8s_read_tools

pytestmark = pytest.mark.integration

CONTEXT = "kind-hoa"
SYSTEM_NAMESPACE = "hoa-system"
TEST_NAMESPACE = "hoa-test"
LLM_SECRET = "hoa-agent-llm"
FAKE_LLM_SCRIPT = Path(__file__).with_name("fake_llm.py")
FAKE_LLM_URL = f"http://fake-llm.{TEST_NAMESPACE}.svc/v1"
MCP_HEALTH = f"http://hoa-mcp-k8s-read.{SYSTEM_NAMESPACE}.svc/healthz"
AGENT_HEALTH = f"http://hoa-agent.{SYSTEM_NAMESPACE}.svc/healthz"
ALERT = "KubeDeploymentRolloutStuck — namespace=demo deployment=orders: rollout has not progressed"
# 가짜 LLM은 에이전트 이미지의 Python으로 돈다 — 시험용 네임스페이스도 restricted 표준을 지킨다
FAKE_LLM = f"""
apiVersion: v1
kind: Namespace
metadata:
  name: {TEST_NAMESPACE}
  labels:
    pod-security.kubernetes.io/enforce: restricted
---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: fake-llm
  namespace: {TEST_NAMESPACE}
spec:
  replicas: 1
  selector:
    matchLabels:
      app: fake-llm
  template:
    metadata:
      labels:
        app: fake-llm
    spec:
      automountServiceAccountToken: false
      containers:
        - name: fake-llm
          image: hoa-agent:0.1.0
          imagePullPolicy: IfNotPresent
          command: ["python", "/fake/fake_llm.py"]
          ports:
            - name: http
              containerPort: 8080
          readinessProbe:
            httpGet:
              path: /healthz
              port: http
            periodSeconds: 2
          resources:
            requests:
              cpu: 10m
              memory: 32Mi
            limits:
              cpu: 200m
              memory: 128Mi
          securityContext:
            runAsNonRoot: true
            runAsUser: 65532
            runAsGroup: 65532
            allowPrivilegeEscalation: false
            readOnlyRootFilesystem: true
            capabilities:
              drop: [ALL]
            seccompProfile:
              type: RuntimeDefault
          volumeMounts:
            - name: script
              mountPath: /fake
      volumes:
        - name: script
          configMap:
            name: fake-llm
---
apiVersion: v1
kind: Service
metadata:
  name: fake-llm
  namespace: {TEST_NAMESPACE}
spec:
  selector:
    app: fake-llm
  ports:
    - name: http
      port: 80
      targetPort: http
"""


def kubectl(
    *args: str, stdin: str | None = None, check: bool = True
) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        ["kubectl", "--context", CONTEXT, *args],
        input=stdin,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=240,
        check=False,
    )
    if check:
        assert result.returncode == 0, result.stderr
    return result


@contextmanager
def port_forward(namespace: str, service: str, port: int) -> Iterator[int]:
    """kubectl port-forward를 띄우고 고른 로컬 포트를 돌려준다 — NetworkPolicy 밖이다."""
    process = subprocess.Popen(
        [
            "kubectl",
            "--context",
            CONTEXT,
            "-n",
            namespace,
            "port-forward",
            f"service/{service}",
            f":{port}",
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    assert process.stdout is not None
    output = process.stdout
    drain: threading.Thread | None = None
    try:
        first = output.readline()
        match = re.search(r"127\.0\.0\.1:(\d+)", first)
        if match is None:
            pytest.fail(f"kubectl port-forward did not start: {first}{output.read()}")
        # 연결마다 찍히는 "Handling connection for …" 줄이 파이프를 채우면 kubectl이 멈춘다
        # — 끝날 때까지 계속 읽어 버린다
        drain = threading.Thread(target=output.read, daemon=True)
        drain.start()
        yield int(match.group(1))
    finally:
        process.terminate()
        process.wait(timeout=10)
        if drain is not None:
            drain.join(timeout=10)
        output.close()


def wait_settled(namespace: str) -> None:
    """rollout status는 새 파드만 본다 — 종료 중인 옛 파드로 포트포워드가 붙지 않게 기다린다."""
    deadline = time.monotonic() + 120
    while time.monotonic() < deadline:
        pods = json.loads(kubectl("-n", namespace, "get", "pods", "-o", "json").stdout)["items"]
        if not [p for p in pods if p["metadata"].get("deletionTimestamp")]:
            return
        time.sleep(3)
    pytest.fail(f"{namespace}에 종료 중인 파드가 120초 넘게 남았다")


def restart_agent() -> None:
    kubectl("-n", SYSTEM_NAMESPACE, "rollout", "restart", "deployment/hoa-agent")
    kubectl("-n", SYSTEM_NAMESPACE, "rollout", "status", "deployment/hoa-agent", "--timeout=180s")
    wait_settled(SYSTEM_NAMESPACE)


def apply_llm_secret(data: dict[str, str]) -> None:
    manifest = {
        "apiVersion": "v1",
        "kind": "Secret",
        "metadata": {"name": LLM_SECRET, "namespace": SYSTEM_NAMESPACE},
        "type": "Opaque",
        "data": data,
    }
    kubectl("apply", "-f", "-", stdin=json.dumps(manifest))


def in_pod(namespace: str, deployment: str, url: str) -> subprocess.CompletedProcess[str]:
    code = f"import urllib.request; print(urllib.request.urlopen('{url}', timeout=5).status)"
    return kubectl(
        "-n", namespace, "exec", f"deployment/{deployment}", "--", "python", "-c", code, check=False
    )


@pytest.fixture(scope="module")
def fake_llm() -> Iterator[None]:
    kubectl("apply", "-f", "-", stdin=FAKE_LLM)
    configmap = kubectl(
        "-n",
        TEST_NAMESPACE,
        "create",
        "configmap",
        "fake-llm",
        f"--from-file=fake_llm.py={FAKE_LLM_SCRIPT}",
        "--dry-run=client",
        "-o",
        "yaml",
    ).stdout
    kubectl("apply", "-f", "-", stdin=configmap)
    kubectl("-n", TEST_NAMESPACE, "rollout", "status", "deployment/fake-llm", "--timeout=180s")
    try:
        yield
    finally:
        kubectl("delete", "namespace", TEST_NAMESPACE, "--timeout=120s", check=False)


@pytest.fixture(scope="module")
def agent_on_fake_llm(fake_llm: None) -> Iterator[None]:
    """에이전트의 LLM Secret을 가짜 LLM으로 바꿨다가 끝나면 원래 값으로 되돌린다."""
    secret = kubectl("-n", SYSTEM_NAMESPACE, "get", "secret", LLM_SECRET, "-o", "json").stdout
    saved = json.loads(secret).get("data") or {}
    apply_llm_secret({"HOA_GEMMA_BASE_URL": base64.b64encode(FAKE_LLM_URL.encode()).decode()})
    restart_agent()
    try:
        yield
    finally:
        apply_llm_secret(saved)
        restart_agent()


def test_agent_api_investigates_through_the_in_cluster_mcp_server(
    agent_on_fake_llm: None,
) -> None:
    with port_forward(SYSTEM_NAMESPACE, "hoa-agent", 80) as port:
        response = httpx.post(
            f"http://127.0.0.1:{port}/investigations", json={"alert": ALERT}, timeout=120
        )

    assert response.status_code == 200, response.text
    body = response.json()
    assert [step["tool"] for step in body["steps"]] == ["list_pods", "get_events"]
    assert not [step for step in body["steps"] if step["error"]]
    # 진짜 MCP 파드가 쿠버네티스 API에서 읽은 파드 이름이 도구 출력에 있다
    assert "gateway-" in body["steps"][0]["output"]
    assert body["diagnosis"]["cause_label"] == "unknown"
    assert body["model"] == "gemma4-26b-a4b"
    assert body["stop_reason"] == "answered"


def test_only_the_agent_reaches_the_mcp_server(fake_llm: None) -> None:
    assert in_pod(SYSTEM_NAMESPACE, "hoa-agent", MCP_HEALTH).stdout.strip() == "200"
    assert in_pod(TEST_NAMESPACE, "fake-llm", MCP_HEALTH).returncode != 0


def test_nothing_in_the_cluster_reaches_the_agent_api(fake_llm: None) -> None:
    assert in_pod(TEST_NAMESPACE, "fake-llm", AGENT_HEALTH).returncode != 0


@pytest.mark.anyio
async def test_cli_tools_reach_the_in_cluster_mcp_server_over_http() -> None:
    with port_forward(SYSTEM_NAMESPACE, "hoa-mcp-k8s-read", 80) as port:
        async with k8s_read_tools({"HOA_MCP_URL": f"http://127.0.0.1:{port}/mcp"}) as tools:
            names = {tool.name for tool in tools}
            list_pods = next(tool for tool in tools if tool.name == "list_pods")
            pods = await list_pods.ainvoke({"namespace": "demo"})

    assert names == {"list_pods", "get_events", "describe_deployment", "get_pod_logs"}
    assert "gateway-" in str(pods)
```

- [ ] **Step 3: 실행**

Run: `uv run ruff check agent && uv run ruff format --check agent && uv run pytest -m integration agent/tests/integration/test_agent_api_kind.py -q`
Expected: PASS(4개).
- 끝-끝 테스트가 실패하면 `kubectl --context kind-hoa -n hoa-system logs deployment/hoa-agent`와 `-n hoa-test logs deployment/fake-llm`을 본다(가짜 LLM은 요청마다 접근 로그를 남긴다).
- NetworkPolicy 두 테스트가 실패해(다른 네임스페이스 파드가 MCP·에이전트에 닿으면) kind의 CNI가 정책을 지키지 않는 것이다. 멈추고 사용자에게 알린다 — spec §8대로 이 두 테스트를 빼고 완료노트에 적을지 정한다.

Run: `uv run pytest -m integration -q`
Expected: PASS(22개 — 기존 8 + MCP 클러스터 안 10 + 에이전트 4)

- [ ] **Step 4: 커밋**

```bash
git add agent/tests/integration/fake_llm.py agent/tests/integration/test_agent_api_kind.py
git commit -m "[Test] 통합 — 에이전트 파드→가짜 LLM→MCP 파드 끝-끝, NetworkPolicy, CLI의 HTTP 연결"
```

---

### Task 17: CI — 차트 잡과 통합 잡의 helm, devcontainer helm 고정

**Files:**
- Modify: `.github/workflows/ci.yml`
- Modify: `.devcontainer/devcontainer.json`

- [ ] **Step 1: 차트 잡을 더한다**

`.github/workflows/ci.yml`의 `python` 잡과 `secrets` 잡 사이에 더한다(들여쓰기는 `jobs:` 아래 두 칸):
```yaml
  charts:
    name: 차트(helm lint·kubeconform·정책)
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v7
      - uses: astral-sh/setup-uv@v10.3.3
        with:
          enable-cache: true
      - name: helm·kubeconform 설치(버전·체크섬 고정 — scripts/dev-cluster.sh·devcontainer·문서와 같이 올린다)
        run: |
          mkdir -p "$RUNNER_TEMP/bin" "$RUNNER_TEMP/dl"
          cd "$RUNNER_TEMP/dl"
          curl -sSfLO https://get.helm.sh/helm-v4.3.2-linux-amd64.tar.gz
          echo "d1c0278d46beab79582d7e50f5b3dc206944ba8e577cde618513fd07daa53983  helm-v4.3.2-linux-amd64.tar.gz" | sha256sum -c -
          tar -xzf helm-v4.3.2-linux-amd64.tar.gz
          mv linux-amd64/helm "$RUNNER_TEMP/bin/helm"
          curl -sSfLO https://github.com/yannh/kubeconform/releases/download/v0.8.0/kubeconform-linux-amd64.tar.gz
          echo "9bc2bffbf71f261128533edaf912153948b7ff238f9a531ae6d34466ec287883  kubeconform-linux-amd64.tar.gz" | sha256sum -c -
          tar -xzf kubeconform-linux-amd64.tar.gz -C "$RUNNER_TEMP/bin" kubeconform
          echo "$RUNNER_TEMP/bin" >> "$GITHUB_PATH"
      - name: 의존성 설치(잠금 파일 그대로)
        run: uv sync --locked
      - name: helm lint(kind 값)
        run: |
          for chart in demo-app mcp-k8s-read agent; do
            helm lint "deploy/helm/${chart}" --values "deploy/values/kind/${chart}.yaml"
          done
      - name: kubeconform(쿠버네티스 v1.37.0 스키마 — kind 노드와 같다, 모르는 필드 거부)
        run: |
          set -o pipefail
          for pair in demo-app:demo mcp-k8s-read:hoa-system agent:hoa-system; do
            chart="${pair%%:*}"
            helm template "${chart}" "deploy/helm/${chart}" --namespace "${pair#*:}" \
              --values "deploy/values/kind/${chart}.yaml"
          done | kubeconform -strict -summary -kubernetes-version 1.37.0
      - name: 차트 정책 테스트
        run: uv run pytest -m charts
```

- [ ] **Step 2: 통합 잡에 helm**

`integration` 잡의 「kind·kubectl 설치」 단계 바로 뒤에 더한다:
```yaml
      - name: helm 설치(버전·체크섬 고정 — 차트 잡과 같이 올린다)
        run: |
          mkdir -p "$RUNNER_TEMP/helm"
          cd "$RUNNER_TEMP/helm"
          curl -sSfLO https://get.helm.sh/helm-v4.3.2-linux-amd64.tar.gz
          echo "d1c0278d46beab79582d7e50f5b3dc206944ba8e577cde618513fd07daa53983  helm-v4.3.2-linux-amd64.tar.gz" | sha256sum -c -
          tar -xzf helm-v4.3.2-linux-amd64.tar.gz
          mv linux-amd64/helm "$RUNNER_TEMP/bin/helm"
```

「실패 진단」 단계를 바꾼다.

전:
```yaml
      - name: 실패 진단
        if: failure() || cancelled()
        run: |
          kubectl --context kind-hoa get pods,events -A || true
          kind export logs "$RUNNER_TEMP/kind-logs" --name hoa || true
```
후:
```yaml
      - name: 실패 진단
        if: failure() || cancelled()
        run: |
          kubectl --context kind-hoa get pods,events -A || true
          helm --kube-context kind-hoa list -A || true
          kubectl --context kind-hoa -n hoa-system logs deployment/hoa-agent --tail=100 || true
          kubectl --context kind-hoa -n hoa-system logs deployment/hoa-mcp-k8s-read --tail=100 || true
          kind export logs "$RUNNER_TEMP/kind-logs" --name hoa || true
```

- [ ] **Step 3: devcontainer의 helm 고정**

`.devcontainer/devcontainer.json`:

전:
```json
    "ghcr.io/devcontainers/features/kubectl-helm-minikube:1": { "version": "1.37.0", "minikube": "none" },
```
후:
```json
    "ghcr.io/devcontainers/features/kubectl-helm-minikube:1": { "version": "1.37.0", "helm": "4.3.2", "minikube": "none" },
```

Run: `uv run pre-commit run --all-files`
Expected: 모두 Passed(check-yaml은 `deploy/helm/*/templates/`를 건너뛴다)

- [ ] **Step 4: 커밋·push·CI**

```bash
git add .github/workflows/ci.yml .devcontainer/devcontainer.json
git commit -m "[Chore] CI 차트 잡(helm lint·kubeconform·정책 테스트)과 통합 잡 helm, devcontainer helm v4.3.2"
git push
```

Run: `gh run list --branch feat/round02a-helm-charts --limit 1 --json databaseId,headSha` 후 그 실행을 `gh run watch <databaseId> --exit-status`
Expected: 네 잡(린트·테스트, 차트, 비밀값 검사, 통합 테스트) success. 통합 잡은 이미지 셋 빌드로 round01b보다 몇 분 길다(제한 20분). 넘으면 멈추고 사용자에게 알린다 — 빌드 캐시(`docker/build-push-action`의 GHA 캐시)를 더할지 정한다.

---

### Task 18: 문서 — 운영 문서·전체 설계·코딩 표준·반복 함정

**Files:**
- Modify: `GIT_WORKFLOW.md`, `README.md`, `.env.example`
- Modify: `docs/superpowers/specs/2026-11-09-hybrid-ops-agent-design.md`
- Modify: `docs/standards/coding-standard.md`
- Modify: `docs/ops/recurring-gotchas.md`
- Modify: `.claude/skills/round-finish/SKILL.md`

`CLAUDE.md`는 바꾸지 않는다(spec §7).

- [ ] **Step 1: `GIT_WORKFLOW.md`**

브랜치 모델 표 `main` 행 — 「round02부터 Argo CD가」 → 「round02b부터 Argo CD가」.

흐름 그림 끝 — 「(round02부터 = 배포)」 → 「(round02b부터 = 배포)」.

머지 승인 규칙 — 「round02부터는 `main` push가 곧 배포다.」 → 「round02b부터는 `main` push가 곧 배포다.」

품질 게이트 표:

전:
```markdown
| helm lint · kubeconform | CI | round02 |
```
후:
```markdown
| helm lint · kubeconform · 차트 정책 테스트(`pytest -m charts`) | CI(차트 잡) | round02a |
```

버전을 같이 올리는 문단 끝 문장 뒤에 더한다.

전:
```markdown
kubectl은 `ci.yml`의 다운로드 버전과 `.devcontainer/devcontainer.json`의 kubectl 버전을 같이 올린다(kind 노드 이미지와 같은 마이너).
```
후:
```markdown
kubectl은 `ci.yml`의 다운로드 버전과 `.devcontainer/devcontainer.json`의 kubectl 버전을 같이 올린다(kind 노드 이미지와 같은 마이너). helm은 `ci.yml`의 다운로드 URL·체크섬(차트·통합 잡 두 곳), `scripts/dev-cluster.sh`의 `HELM_VERSION`, `.devcontainer/devcontainer.json`의 `helm`, 이 문서·`README.md`의 helm 버전을, kubeconform은 `ci.yml`의 다운로드 URL·체크섬을 같이 올린다. kubeconform의 `-kubernetes-version`은 kind 노드 이미지와 같은 버전으로 둔다.
```

개발 환경 표 두 행:

전:
```markdown
| 개발 PC: kind (로컬 티어) | GPU 없이 도는 개발 클러스터, 데모 앱·MCP 통합 테스트 | round01a |
| 회사 GPU 서버: k3s + GPU Operator (GPU 티어) | 상시 클러스터(모델·데이터·관측·Argo CD) | round02 |
```
후:
```markdown
| 개발 PC: kind (로컬 티어) | GPU 없이 도는 개발 클러스터 — 데모 앱·MCP 서버·에이전트를 Helm 차트로 올린다(round02a), 통합 테스트 | round01a |
| 회사 GPU 서버: k3s + GPU Operator (GPU 티어) | 상시 클러스터(모델·데이터·관측·Argo CD) | round02b |
```

kind 항목(「- kind(로컬 티어, round01a): …」로 시작하는 한 줄) 전체를 바꾼다:
```markdown
- kind(로컬 티어, round01a·round02a): Docker Desktop, kind v0.33.0, kubectl(노드 v1.37과 ±1 마이너 — Docker Desktop에 들어 있다), helm v4.3.2(공식 zip `helm-v4.3.2-windows-amd64.zip`의 `helm.exe`를 PATH에 둔다)를 호스트에 둔다. 처음 `up`하면 사용자 kubeconfig의 current-context가 `kind-hoa`로 바뀐다(스크립트와 테스트는 컨텍스트를 명시해서 쓴다). `bash scripts/dev-cluster.sh up`이 클러스터 `hoa`를 만들고, 이미지 셋(`hoa-demo`·`hoa-mcp`·`hoa-agent` — `deploy/docker/Dockerfile`)을 빌드·적재하고, `.env`의 LLM 변수로 클러스터 안 Secret `hoa-agent-llm`을 만들고(값은 화면에 내지 않는다), 차트 셋(`deploy/helm/` + `deploy/values/kind/`)을 helm으로 설치한 뒤 개발 PC의 stdio MCP용 읽기 전용 kubeconfig(`~/.kube/hoa-kind-mcp-read.kubeconfig`, 토큰 12시간)를 쓴다. 설치·복구는 `--server-side=true --force-conflicts`로 한다 — Helm 4는 server-side apply로 올리고, 장애 주입(`kubectl patch`)이 가져간 필드를 되찾으려면 충돌을 넘어서야 한다(`docs/ops/recurring-gotchas.md` 12번). round02a 전에 만든 클러스터는 Helm 소유 표시가 없어 `up`이 거절한다 — 한 번 `down` → `up`한다. 그 밖의 명령은 `down`·`fault <image-pull|bad-config>`·`reset`·`mcp-kubeconfig`이고, 통합 테스트는 `uv run pytest -m integration`, 차트 정책 테스트는 `uv run pytest -m charts`(helm 필요)다. kind와 통합 테스트는 호스트에서 돌린다 — devcontainer 안에서는 kind API 주소(`127.0.0.1`)에 닿지 않는다. Windows에서는 Git Bash로 실행한다.
```

LLM 항목(「- LLM(round01b): …」) 바로 아래에 더한다:
```markdown
- 클러스터 안 에이전트(round02a): 한 터미널에서 `kubectl --context kind-hoa -n hoa-system port-forward service/hoa-agent 8080:80`을 띄우고, 다른 터미널에서 `curl --max-time 330 -s -X POST http://127.0.0.1:8080/investigations -H 'content-type: application/json' -d '{"alert": "<경보 문장>"}'`을 보낸다. 진단 JSON(`hoa investigate --json`과 같은 모양)이 돌아온다. 조사 중에 또 보내면 429(`busy`), LLM 설정이 없으면 503(`setup_error`), 300초를 넘기면 504(`timeout`)다. `.env`를 바꾸면 `up`을 다시 돌린다(Secret을 다시 만들고 에이전트를 다시 시작한다). 개발 PC의 `hoa investigate`도 `HOA_MCP_URL=http://127.0.0.1:<포트>/mcp`를 주면 포트포워드한 클러스터 안 MCP 서버를 쓴다.
```

- [ ] **Step 2: `README.md`**

전:
```markdown
로컬 티어 개발 클러스터에는 Docker Desktop, [kind](https://kind.sigs.k8s.io/) v0.33.0, kubectl(Docker Desktop에 들어 있다)이 필요하다(Windows는 Git Bash에서 실행한다).

```bash
bash scripts/dev-cluster.sh up
uv run pytest -m integration
```

`up`은 kind 클러스터 `hoa`에 데모 앱(gateway·orders·inventory)을 띄우고 MCP 서버용 읽기 전용 kubeconfig를 만든다. `fault image-pull`·`fault bad-config`로 장애를 심고 `reset`으로 되돌린다. 클러스터를 지울 때는 `down`.
```
후:
```markdown
로컬 티어 개발 클러스터에는 Docker Desktop, [kind](https://kind.sigs.k8s.io/) v0.33.0, kubectl(Docker Desktop에 들어 있다), [helm](https://helm.sh/) v4.3.2가 필요하다(Windows는 Git Bash에서 실행한다).

```bash
bash scripts/dev-cluster.sh up
uv run pytest -m integration
uv run pytest -m charts
```

`up`은 kind 클러스터 `hoa`에 이미지 셋을 빌드해 넣고, Helm 차트 셋(`deploy/helm/`)으로 데모 앱(gateway·orders·inventory)·MCP `k8s-read` 서버·에이전트 API를 올린 뒤 개발 PC용 읽기 전용 kubeconfig를 만든다. `.env`가 있으면 그 LLM 변수로 클러스터 안 Secret을 만든다. `fault image-pull`·`fault bad-config`로 장애를 심고 `reset`으로 되돌린다. 클러스터를 지울 때는 `down`(round02a 전에 만든 클러스터는 한 번 `down` → `up`).
```

`hoa investigate`·`hoa-eval run` 설명 문단(「`hoa investigate`는 진단 JSON을 표준출력에, …」) 바로 뒤에 더한다:
````markdown
클러스터 안 에이전트 API는 포트포워드로 부른다(한 터미널에서 포트포워드, 다른 터미널에서 요청).

```bash
kubectl --context kind-hoa -n hoa-system port-forward service/hoa-agent 8080:80
curl --max-time 330 -s -X POST http://127.0.0.1:8080/investigations -H 'content-type: application/json' -d '{"alert": "KubeDeploymentRolloutStuck — namespace=demo deployment=orders: rollout has not progressed"}'
```
````

- [ ] **Step 3: `.env.example`**

첫 줄 아래에 한 줄 더한다.

전:
```
# 루트의 .env로 복사해 값을 채운다(.env는 커밋하지 않는다). 실행: uv run --env-file .env <명령>
```
후:
```
# 루트의 .env로 복사해 값을 채운다(.env는 커밋하지 않는다). 실행: uv run --env-file .env <명령>
# bash scripts/dev-cluster.sh up 이 아래 LLM 변수(값이 있는 것만)로 kind 클러스터 안 Secret hoa-agent-llm 을 만든다 — 클러스터 안 에이전트(hoa serve)가 쓴다
```

- [ ] **Step 4: 전체 설계**

`docs/superpowers/specs/2026-11-09-hybrid-ops-agent-design.md`:

바뀐 이력(5번째 줄) 끝:

전:
```markdown
근거: `docs/superpowers/specs/2026-11-16-round01b-agent-llm-eval-design.md`.
```
후:
```markdown
근거: `docs/superpowers/specs/2026-11-16-round01b-agent-llm-eval-design.md`. 2026-11-17(round02a) — round02를 02a(Helm 차트·클러스터 안 MCP 서버·에이전트 API, 로컬 티어)와 02b(GPU 티어)로 나눔, 서빙은 02a에서 동기 HTTP API로 시작. 근거: `docs/superpowers/specs/2026-11-17-round02a-helm-charts-design.md`.
```

§2 결정 요약 온프레미스 LLM 행 — 「+ 임베딩 모델(round02)」 → 「+ 임베딩 모델(round02b)」.

§4 서빙 줄:

전:
```markdown
- **서빙**: FastAPI + SSE 스트리밍. 웹 UI는 학습 대상이 아니므로 Nuxt로 채팅·조사 타임라인·승인 버튼만 최소로 만든다(round06).
```
후:
```markdown
- **서빙**: FastAPI. round02a는 동기 조사 API(`hoa serve` — `POST /investigations`, 동시 1건, 제한 시간)로 시작하고, SSE 스트리밍과 웹 UI는 round06에 더한다. 웹 UI는 학습 대상이 아니므로 Nuxt로 채팅·조사 타임라인·승인 버튼만 최소로 만든다.
```

§7 로드맵 round02 행을 두 행으로:

전:
```markdown
| round02 | 온프레미스(GPU 티어): 회사 GPU 서버의 k3s·GPU Operator·vLLM(기존 Gemma 인스턴스를 k3s 관리로 옮김)·임베딩 모델, Argo CD, Helm 차트(로컬 티어는 같은 차트를 로컬 값으로), SOPS | git push만으로 회사 GPU 서버의 k3s에 에이전트·데모 앱이 배포되고, 온프레미스 LLM(Gemma) triage가 동작 |
```
후:
```markdown
| round02a | 배포 패키징(로컬 티어): 이미지 셋, Helm 차트 셋(데모 앱·MCP `k8s-read`·에이전트) + kind 값, MCP streamable HTTP·클러스터 안 ServiceAccount 인증, 에이전트 HTTP API(`hoa serve`), CI 차트 잡(helm lint·kubeconform·정책 테스트) | kind가 차트로 돌고, 클러스터 안 에이전트 API가 Gemma로 장애 2종을 맞히고, CI가 클러스터 안 배선(가짜 LLM 끝-끝)을 증명 |
| round02b | 온프레미스(GPU 티어): 회사 GPU 서버의 k3s·GPU Operator·vLLM(기존 Gemma 인스턴스를 k3s 관리로 옮김)·임베딩 모델, Argo CD, SOPS, 02a 차트를 GPU 티어 값으로 | git push만으로 회사 GPU 서버의 k3s에 에이전트·데모 앱이 배포되고, 클러스터 안 에이전트가 온프레미스 Gemma로 조사를 끝낸다 |
```

§7 저장소 구조 — 「├─ deploy/           kind/ · helm/ · argocd/」 → 「├─ deploy/           kind/ · helm/ · values/ · docker/ · argocd/」.

§8 CI 게이트 줄 — 「`helm lint`·kubeconform(round02)」 → 「`helm lint`·kubeconform(round02a)」.

§10 표 — 「| 임베딩 모델·서빙 방식(vLLM / TEI) | round02 |」 → 「| 임베딩 모델·서빙 방식(vLLM / TEI) | round02b |」.

§11 표 — 「requests/limits를 두고 round02에서 실측해」 → 「requests/limits를 두고 round02b에서 실측해」, 「round02 spec에서 사내 대역을 확인해」 → 「round02b spec에서 사내 대역을 확인해」. Postgres 백업 「(round02)」은 그대로 둔다 — round02b spec에서 맞춘다(round02a spec §9).

- [ ] **Step 5: 코딩 표준**

「외부 호출 격리」의 예외 문장:

전:
```markdown
`eval` 러너의 장애 주입·복구(데모 네임스페이스 한정).
```
후:
```markdown
`eval` 러너의 장애 주입·복구(데모 네임스페이스 한정 — kubectl·helm).
```

「에러 처리」의 CLI 종료 코드 항목 끝에 더한다.

전:
```markdown
평가 러너는 에이전트가 2·3으로 끝나면 남은 회차를 멈추고 같은 코드로 끝난다.
```
후:
```markdown
평가 러너는 에이전트가 2·3으로 끝나면 남은 회차를 멈추고 같은 코드로 끝난다. 에이전트 API(`hoa serve`)는 같은 분류(`hoa_agent/failures.py`)로 502(조사 실패)·503(설정 오류·LLM 요청 한도)을 내고, 응답에는 내부 주소가 섞일 수 있는 예외 원문을 싣지 않는다(운영자 로그에만 남긴다).
```

「쿠버네티스·인프라」의 마지막 항목(「- 배포 리소스 이름은 kebab-case(`hoa-agent`).」) 아래에 더한다:
```markdown
- Helm 차트(`deploy/helm/<컴포넌트>`)는 티어마다 다른 값(이미지 저장소·태그, Secret 이름)을 `deploy/values/<티어>/`에 두고 차트 기본값에는 두지 않는다 — 템플릿의 `required`가 빠뜨림을 막는다. 네임스페이스는 차트가 만들지 않는다(kind는 `deploy/kind/namespaces.yaml`, GPU 티어는 Argo CD). `hoa-system`의 Deployment마다 NetworkPolicy를 둔다. 비밀값은 `existingSecret`처럼 이름으로만 참조한다. 렌더 결과가 이 표준을 지키는지는 차트 정책 테스트(`deploy/tests/test_charts.py`, `uv run pytest -m charts`)가 본다.
```

- [ ] **Step 6: 반복 함정 12·13번**

`docs/ops/recurring-gotchas.md` 끝에 더한다. 12번의 증상 줄에는 Task 13 Step 3에서 적어 둔 오류 문장을 그대로 넣는다(그때 충돌 없이 되돌아갔다면 증상·원인을 실제로 본 대로 고쳐 쓴다).
```markdown
## 12. Helm 4로 올린 차트를 `kubectl patch` 뒤에 되돌리면 server-side apply 충돌

- **날짜**: 2026-11-17 (round02a)
- **증상**: `kubectl patch`로 장애를 심은 데모 앱을 같은 값의 `helm upgrade --install --server-side=true`로 되돌리면 충돌 오류로 실패한다 — (Task 13 Step 3에서 본 오류 문장).
- **원인**: Helm 4는 새 릴리스를 server-side apply로 올린다(`install`의 `--server-side` 기본값 `true`, `upgrade`는 이전 릴리스의 방식). server-side apply는 필드마다 관리자(field manager)를 기록한다. `kubectl patch`는 바꾼 필드(이미지·환경변수 값)의 관리자를 `kubectl-patch`로 가져가고, 그 필드를 다른 값으로 apply하려는 helm은 충돌로 멈춘다. Helm 3의 클라이언트 3-way merge에는 이 충돌이 없었다.
- **해결**: 기준 상태로 되돌리는 helm 명령은 모두 `--server-side=true --force-conflicts`를 준다 — `scripts/dev-cluster.sh`의 `release`, 평가 러너의 `hoa_eval.cluster.baseline_release`, MCP 통합 테스트의 `injected`. `--force-conflicts`는 `--force`와 같이 쓸 수 없다.
- **재발 방지**: 차트로 올린 리소스를 kubectl로 바꾸는 도구(장애 주입 등)를 새로 만들면, 되돌리는 쪽이 충돌을 넘어서는지 CI의 「스크립트 장애 주입·복구」 단계로 확인한다. round02b의 Argo CD도 server-side apply로 동기화하면 같은 충돌을 만난다 — 데모 앱 Application의 동기화 옵션을 정할 때 본다.

## 13. FastMCP를 `0.0.0.0`에 묶으면 Host 검사(DNS 리바인딩 방어)가 꺼진다

- **날짜**: 2026-11-17 (round02a, plan을 쓰며 스크래치에서 확인)
- **증상**: 클러스터 안 MCP 서버를 `host="0.0.0.0"`으로 열면 아무 Host 헤더나 받는다. 반대로 기본값(`127.0.0.1`)으로 두면 Service 이름(`hoa-mcp-k8s-read.hoa-system.svc`)으로 온 요청이 `421 Invalid Host header`로 거절된다.
- **원인**: FastMCP(mcp 1.30)는 `host`가 localhost일 때만 허용 Host(`127.0.0.1:*`·`localhost:*`)를 저절로 설정한다. 허용 값은 정확히 같은 문자열이거나 `<호스트>:*`(Host에 포트가 붙을 때만 맞는다)라서, 포트 없이 부르는 Service 이름은 `:*` 패턴에 걸리지 않는다.
- **해결**: `transport_security=TransportSecuritySettings(allowed_hosts=…)`를 명시하고, 차트가 Service 이름(포트 없이)과 포트포워드용 `127.0.0.1:*`·`localhost:*`를 `HOA_MCP_ALLOWED_HOSTS`로 넘긴다. 비어 있으면 서버가 시작하지 않는다. `/healthz`(`custom_route`)는 이 검사를 거치지 않는다 — kubelet 프로브의 Host는 파드 IP다. 허용 Host는 접근 제어가 아니다(LAN의 누구나 `Host: 127.0.0.1:1`을 보낼 수 있다) — 그래서 바인드 주소는 `HOA_MCP_HOST`(기본 `127.0.0.1`)로 따로 두고, 차트가 파드 안에서만 `0.0.0.0`을 준다.
- **재발 방지**: `mcp_servers/tests/test_http.py`(허용 밖 Host 421)와 통합 테스트 `test_in_cluster.py`가 지킨다. Service 이름이나 포트를 바꾸면 차트 정책 테스트가 에이전트의 `HOA_MCP_URL` Host가 허용 목록에 있는지 본다.
```

- [ ] **Step 7: round-finish 스킬의 라운드 번호**

`.claude/skills/round-finish/SKILL.md`에서 Argo CD가 들어오는 라운드를 02b로 바꾼다(세 곳).
- 「round02부터는 `main` push가 Argo CD 배포를 일으킨다.」 → 「round02b부터는 `main` push가 Argo CD 배포를 일으킨다.」
- 「(round02부터는 배포가 이미 시작됐을 수 있다)」 → 「(round02b부터는 배포가 이미 시작됐을 수 있다)」
- 「round02에서 Argo CD가 들어오면」 → 「round02b에서 Argo CD가 들어오면」

- [ ] **Step 8: 확인·커밋·push**

Run: `git grep -n "round02[^ab]" -- GIT_WORKFLOW.md README.md docs/standards .claude/skills docs/superpowers/specs/2026-11-09-hybrid-ops-agent-design.md`
Expected: 남은 것은 설계 §7의 접미 설명 문장(「`round02a`·`round02b`처럼」)과 §11 Postgres 백업 「(round02)」뿐이다.

```bash
git add GIT_WORKFLOW.md README.md .env.example docs/superpowers/specs/2026-11-09-hybrid-ops-agent-design.md docs/standards/coding-standard.md docs/ops/recurring-gotchas.md .claude/skills/round-finish/SKILL.md
git commit -m "[Docs] round02a — 운영 문서(helm·클러스터 안 에이전트), 전체 설계 02a·02b, 코딩 표준(차트), 반복 함정 12·13"
git push
```

---

### Task 19: 수동 스모크 — 클러스터 안 에이전트(Gemma)와 회귀 평가

**Files:** 없음(확인만 — 결과는 완료노트 「수치」에 옮긴다)

LLM을 실제로 부르는 단계다. 응답 JSON을 읽는 Python은 `-X utf8`로 돌린다 — 한국어 요약이 든 파이프를 cp949로 읽으면 깨진다(반복 함정 8번).

- [ ] **Step 1: kind 파드에서 회사 vLLM에 닿는지**

Run: `kubectl --context kind-hoa -n hoa-system exec deployment/hoa-agent -- python -c "import os, urllib.request; print(urllib.request.urlopen(os.environ['HOA_GEMMA_BASE_URL'].rstrip('/') + '/models', timeout=10).status)"`
Expected: `200`. 주소는 화면에 나오지 않는다.

`URLError`·시간 초과면 kind 파드(Docker Desktop NAT)가 회사 vLLM에 닿지 않는 것이다. 멈추고 사용자에게 알린다. 사용자가 동의하면 Gemini로 스모크를 한다(spec §8).
- 바꾸기: `helm --kube-context kind-hoa upgrade --install agent deploy/helm/agent --namespace hoa-system --values deploy/values/kind/agent.yaml --set model=gemini --server-side=true --force-conflicts`
- 되돌리기: 같은 명령에서 `--set model=gemini`를 빼고 돌린다.
- 완료노트에 「클러스터 안 Gemma 확인은 round02b로」라고 적는다.

- [ ] **Step 2: image-pull — 클러스터 안 에이전트 API로 조사**

Run:
```bash
bash scripts/dev-cluster.sh fault image-pull
sleep 20 && kubectl --context kind-hoa -n demo get pods
kubectl --context kind-hoa -n hoa-system port-forward service/hoa-agent 18080:80 >/dev/null 2>&1 &
pf=$!
sleep 3
curl -s --max-time 330 -X POST http://127.0.0.1:18080/investigations \
  -H 'content-type: application/json' \
  -d '{"alert": "KubeDeploymentRolloutStuck — namespace=demo deployment=orders: rollout has not progressed"}' \
  | uv run python -X utf8 -c "import json, sys; d = json.load(sys.stdin); print(d['model'], d['diagnosis']['cause_label'], d['diagnosis']['target'], d['stop_reason'], len(d['steps']), round(d['elapsed_seconds'], 1)); print(d['diagnosis']['summary_ko'])"
kill "${pf}"
bash scripts/dev-cluster.sh reset
```
Expected: 새 orders 파드가 `ErrImagePull`/`ImagePullBackOff`. 결과 첫 줄 `gemma4-26b-a4b image_pull_error demo/orders answered <도구 수> <초>`, 둘째 줄 한국어 요약. 복구 뒤 세 Deployment `successfully rolled out`.

- [ ] **Step 3: bad-config — 클러스터 안 에이전트 API로 조사**

Run:
```bash
bash scripts/dev-cluster.sh fault bad-config
sleep 30 && kubectl --context kind-hoa -n demo get pods
kubectl --context kind-hoa -n hoa-system port-forward service/hoa-agent 18080:80 >/dev/null 2>&1 &
pf=$!
sleep 3
curl -s --max-time 330 -X POST http://127.0.0.1:18080/investigations \
  -H 'content-type: application/json' \
  -d '{"alert": "KubePodCrashLooping — namespace=demo deployment=inventory: a pod keeps restarting"}' \
  | uv run python -X utf8 -c "import json, sys; d = json.load(sys.stdin); print(d['model'], d['diagnosis']['cause_label'], d['diagnosis']['target'], d['stop_reason'], len(d['steps']), round(d['elapsed_seconds'], 1)); print(d['diagnosis']['summary_ko'])"
kill "${pf}"
bash scripts/dev-cluster.sh reset
```
Expected: 새 inventory 파드의 재시작 수가 1 이상. 결과 첫 줄 `gemma4-26b-a4b bad_config demo/inventory answered <도구 수> <초>`.

틀리면 멈추고 사용자에게 보고한다 — round01b에서 같은 모델·같은 시나리오가 3/3이었으므로 배선(MCP HTTP·도구 출력)부터 의심한다. 에이전트 로그(`kubectl --context kind-hoa -n hoa-system logs deployment/hoa-agent`)를 본다.

- [ ] **Step 4: 회귀 평가 — 차트로 올린 kind에서 1회씩**

Run: `bash scripts/dev-cluster.sh mcp-kubeconfig && uv run --env-file .env hoa-eval run --repeat 1`
Expected: 회차마다 `<시나리오> #1: 맞음`, 요약 표, `결과: eval/results/<시각>-gemma.jsonl`, 종료 코드 0.

Run: `uv run hoa-eval report eval/results/<이번 결과 파일>.jsonl`
Expected: 두 시나리오 모두 「원인 정답」 1/1. 표를 완료노트 「수치」에 옮긴다.

---

### Task 20: 리뷰 — 공개 저장소 점검과 code-reviewer 정적 리뷰

**Files:** (리뷰 발견을 고치는 파일)

- [ ] **Step 1: 공개 저장소 점검**

Run: `git ls-files .env eval/results`
Expected: 출력 없음

Run: `git diff dev --name-only | grep -v '^uv.lock$' | xargs grep -nE '([0-9]{1,3}\.){3}[0-9]{1,3}' -- 2>/dev/null`
Expected: `0.0.0.0`·`127.0.0.1`과 버전 번호 말고는 IP 주소가 없다. 회사 서버의 주소·호스트명·컨테이너·네트워크 이름과 다른 시스템의 모델 이름이 없는지 사람 눈으로도 본다(gitleaks는 내부 주소를 잡지 못한다 — `CLAUDE.md` §2).

Run: `git grep -nE '[A-Za-z]:\\\\Users\\\\|/c/Users/' -- ':!docs/superpowers/plans/2026-11-09-round00-scaffold.md'`
Expected: 출력 없음

- [ ] **Step 2: code-reviewer 정적 리뷰 — 세 영역을 병렬로**

`.claude/agents/code-reviewer.md` 에이전트를 영역마다 하나씩 동시에 띄운다. 리뷰어는 git을 실행하지 않으므로 파일 목록과 기준 문서를 프롬프트로 넘긴다. 기준: spec `docs/superpowers/specs/2026-11-17-round02a-helm-charts-design.md`, 이 plan, 코딩 표준, 반복 함정.
- 영역 A(MCP 서버·에이전트 코드): `mcp_servers/src/hoa_mcp/k8s_read/{settings,kube,server}.py`, `agent/src/hoa_agent/{failures,api,cli,mcp_tools,investigate}.py`와 그 테스트. 특히 Host 검사 설정, in-cluster 인증의 실패 처리, API 응답의 원문 누출, 동시성 잠금과 제한 시간(취소 뒤 잠금 해제), `KNOWN_FAILURES` 밖 예외의 처리, CLI 종료 코드 호환.
- 영역 B(차트·스크립트·CI): `deploy/**`, `scripts/dev-cluster.sh`, `eval/src/hoa_eval/cluster.py`, `mcp_servers/tests/integration/*`, `agent/tests/integration/*`, `.github/workflows/ci.yml`, `.devcontainer/devcontainer.json`, `.pre-commit-config.yaml`, `pyproject.toml`. 특히 RBAC 최소 권한, NetworkPolicy, securityContext, Secret 처리(값이 화면·명령 인자·파일에 남는지), 이미지 태그 고정, `--force-conflicts`의 범위, 다운로드 체크섬, 컨텍스트 명시, 테스트가 클러스터 상태(Secret·네임스페이스)를 되돌리는지.
- 영역 C(문서): `GIT_WORKFLOW.md`, `README.md`, `.env.example`, 전체 설계, round02a spec, 코딩 표준, 반복 함정, `.claude/skills/round-finish/SKILL.md`. 특히 문서 간 어휘(차트·릴리스 이름, 환경변수, 상태 코드, helm 버전)와 회사 정보 노출.

- [ ] **Step 3: 발견 처리**

high·medium은 모두 고친다. low는 고치거나, 고치지 않는 이유를 완료노트 「결정」에 한 줄로 적는다(Task 22). 고친 뒤 `uv run pytest -q`, `uv run ruff check .`, `uv run ruff format --check .`, `uv run pre-commit run --all-files`, `uv run pytest -m charts -q`, 필요하면 `uv run pytest -m integration -q`를 다시 돌리고, 고친 영역은 같은 리뷰어로 다시 본다.

- [ ] **Step 4: 커밋·push·CI**

```bash
git add -A
git commit -m "[Fix] round02a — 정적 리뷰 반영: <고친 내용 요약>"
git push
```

Run: 이 커밋의 실행을 `gh run watch <databaseId> --exit-status`
Expected: 네 잡 success

---

### Task 21: 교본 — `docs/guides/round02a/`

**Files:**
- Create: `docs/guides/round02a/00-개요.md`
- Create: `docs/guides/round02a/01-이미지와-차트.md`
- Create: `docs/guides/round02a/02-MCP-HTTP와-에이전트-API.md`
- Create: `docs/guides/round02a/03-스크립트-통합테스트-CI.md`
- Create: `docs/guides/round02a/04-운영문서.md`

템플릿(`docs/guides/_TEMPLATE.md`)의 절 구성을 따르되, 수록할 파일이 많아 「3. 구현」을 네 파일로 나눈다. 각 파일은 `**파일**: \`경로\`` 줄 다음에 그 파일 전문을 코드블록으로 싣는다(발췌·플레이스홀더 금지). 담을 내용에 백틱 3개가 들어 있으면 바깥 펜스를 백틱 4개로 쓴다. 생성물(`uv.lock`)과 기록 문서(spec·plan·완료노트·`00_status.md`)는 싣지 않는다.

- [ ] **Step 1: `00-개요.md`**

절 구성:
- 「0. 사용자 프롬프트 (paraphrase)」 — round02의 앞쪽이다. 회사 서버 작업(k3s·GPU Operator·vLLM 이전)과 배포 패키징을 나눠, 서버 없이 할 수 있는 패키징을 먼저 한다. 에이전트는 작은 HTTP API로, 차트는 컴포넌트마다 하나로(사용자 결정 2026-11-17).
- 「1. 설계 요약」 — 그림 하나(개발 PC → 포트포워드 → 에이전트 파드 → MCP 파드 → 쿠버네티스 API, 에이전트 파드 → LLM)와 표 둘(차트 셋이 만드는 객체, 상태 코드 분류). 결정과 이유(spec §3), 버린 안.
- 「2. 개념 입문」 — 이 라운드에 처음 나온 개념을 기초부터. 절마다 「무엇인가 → 왜 여기서 쓰나 → 이 저장소의 어디」 순서.
  - 컨테이너 이미지: 다단계 빌드, 레이어 캐시(의존성 레이어를 소스보다 먼저), 비루트 실행, uv 워크스페이스에서 멤버 하나만 담기, `.dockerignore`.
  - Helm: 차트·템플릿·values·릴리스, `upgrade --install`, `required`, `helm template`·`helm lint`, rollback.
  - server-side apply와 필드 관리자: 3-way merge(클라이언트)와의 차이, 충돌, `--force-conflicts`(Task 13 Step 3의 실제 오류 문장을 인용).
  - 클러스터 안 인증: ServiceAccount와 투영된 토큰(주기적 교체), in-cluster 설정, ClusterRole + RoleBinding으로 범위 좁히기, `kubectl auth can-i --as`.
  - 네트워크: Service와 클러스터 DNS(`<서비스>.<네임스페이스>.svc`), NetworkPolicy(선택되지 않은 파드는 모두 허용 → 선택되면 규칙 밖 거부, 노드·localhost 트래픽은 막지 못한다), `kubectl port-forward`.
  - 운영 객체: 프로브(readiness·liveness, 의존 대상을 부르지 않는 이유), Secret과 `envFrom`, 파드 보안 표준(restricted), `emptyDir`.
  - MCP 전송: stdio와 streamable HTTP, 세션과 상태 없는 모드, JSON 응답, DNS 리바인딩과 허용 Host.
  - 동기 HTTP API 설계: 동시성 제한(429와 `Retry-After`), 제한 시간과 취소, 상태 코드 고르기(502·503·504), 예외 원문을 응답에 싣지 않는 이유.
  - 검사 도구: lint와 스키마 검사(kubeconform), 정책을 테스트로 쓰기(차트 정책 테스트), 가짜 LLM으로 끝-끝 배선 시험.
- 「4. 검증」 — 단위·차트·통합 테스트 수, CI 실행 번호, 스모크 결과(Task 19), 회귀 평가 표.
- 「5. 면접식 Q&A」 15문항 안팎. 예:
  - 왜 server-side apply에서 `kubectl patch` 뒤 helm upgrade가 충돌하나?
  - MCP 서버를 클러스터 안에 둘 때 stdio를 그대로 쓰지 않은 이유는?
  - 상태 없는 streamable HTTP를 고른 이유와 대가는?
  - DNS 리바인딩이란, 클러스터 안 서비스에도 Host 검사가 필요한가?
  - NetworkPolicy가 포트포워드와 kubelet 프로브를 막지 않는 이유는?
  - 헬스 체크가 LLM·MCP를 부르지 않게 한 이유는?
  - 동시 1건 제한을 큐가 아니라 429로 한 이유는?
  - LLM 오류 원문을 API 응답에 싣지 않는 이유와 그래도 운영자가 원인을 보는 방법은?
  - 차트 기본값에 이미지를 두지 않고 `required`를 쓴 이유는?
  - 네임스페이스를 차트가 만들지 않는 이유는?
  - CI가 LLM 없이 클러스터 안 배선을 증명하는 방법은?
  - ServiceAccount 토큰을 MCP 파드에만 마운트한 이유는?
  - 이미지 셋을 Dockerfile 하나로 만든 이유와 멤버 격리를 지키는 방법은?
  - `.env`의 값을 Secret으로 옮길 때 값이 새지 않게 한 방법은?
  - round02b에서 Argo CD가 장애 주입과 부딪히는 지점은?

- [ ] **Step 2: 구현 파일 넷**

| 교본 파일 | 싣는 파일(전문) |
|---|---|
| `01-이미지와-차트.md` | `deploy/docker/Dockerfile`, `Dockerfile.dockerignore`, `deploy/helm/**`(차트 셋의 모든 파일), `deploy/values/kind/*.yaml`, `deploy/kind/namespaces.yaml`, `deploy/tests/test_charts.py` |
| `02-MCP-HTTP와-에이전트-API.md` | `mcp_servers/src/hoa_mcp/k8s_read/{settings,kube,server}.py`, `agent/src/hoa_agent/{failures,api,cli,mcp_tools,investigate}.py`, `agent/pyproject.toml`, 이 라운드에서 바꾼 단위 테스트(`mcp_servers/tests/{test_settings,test_kube,test_http,test_entrypoint}.py`, `agent/tests/{conftest,test_failures,test_api,test_cli,test_mcp_tools,test_investigate}.py`) |
| `03-스크립트-통합테스트-CI.md` | `scripts/dev-cluster.sh`, `eval/src/hoa_eval/cluster.py`, `eval/tests/{test_cluster,test_cli,test_scenario}.py`, `mcp_servers/tests/integration/{test_kind_cluster,test_in_cluster}.py`, `agent/tests/integration/{fake_llm,test_agent_api_kind}.py`, `.github/workflows/ci.yml`, `.devcontainer/devcontainer.json`, `.pre-commit-config.yaml`, `pyproject.toml` |
| `04-운영문서.md` | 이 라운드에서 바꾼 운영 문서 전문: `GIT_WORKFLOW.md`, `README.md`, `.env.example`, `docs/standards/coding-standard.md`, `docs/ops/recurring-gotchas.md`, `.claude/skills/round-finish/SKILL.md`. 전체 설계는 바꾼 절(§2 행·§4 서빙·§7 표와 구조·§8·§10·§11 행)만 「전/후」로 싣는다(기록 문서라 전문 수록 대상이 아니다) |

각 구현 파일의 절은 「무엇을 왜 바꿨나(두세 줄) → **파일** 전문」 순서로 쓴다.

- [ ] **Step 3: 교본 대조**

Run: `git add docs/guides/round02a && uv run python scripts/check_guide.py docs/guides/round02a/`
Expected: 모든 「**파일**:」 코드블록이 실제 파일과 같다(차이 0).

그다음 code-reviewer로 교본을 한 번 더 본다 — 개념 입문의 사실 오류, 실제 파일과 다른 설명, 회사 정보. 리뷰어에게 교본 파일 다섯과 대조할 실제 파일 목록을 넘긴다.

- [ ] **Step 4: 커밋·push**

```bash
git add docs/guides/round02a
git commit -m "[Docs] round02a 교본 — 이미지·Helm 차트·server-side apply·클러스터 안 인증·NetworkPolicy·MCP HTTP·조사 API"
git push
```

---

### Task 22: 완료노트와 현재 상태

**Files:**
- Create: `docs/roadmap/round02a-완료노트.md`
- Modify: `docs/roadmap/00_status.md`

- [ ] **Step 1: 완료노트**

템플릿(`docs/roadmap/_ROUND_COMPLETE_TEMPLATE.md`) 구성 그대로 쓰고, 실제 값을 채운다. 날짜는 완료노트를 쓰는 날이다.
- 「한 일」: 이미지 셋, 차트 셋, MCP HTTP·in-cluster, 에이전트 API·`hoa serve`, 실패 분류, 스크립트·러너 복구, 통합 테스트(클러스터 안 MCP·끝-끝·NetworkPolicy), CI 차트 잡, 문서.
- 「결정」: 라운드 분할·에이전트 형태·차트 구성(사용자 결정), Helm 4 `--force-conflicts`(Task 13 Step 3의 실제 결과), 상태 없는 HTTP·허용 Host, 헬스 체크가 의존 대상을 부르지 않음, 리뷰에서 고치지 않은 low와 이유.
- 「수치」: 스모크 표(시나리오·모델·원인·대상·도구 수·시간 — Task 19 Step 2·3), 회귀 평가 표(`hoa-eval report`), 테스트 수(단위·차트·통합), CI 통합 잡 시간.
- 「클라우드 비용」: 사용 안 함(Gemini를 쓴 경우 무료 등급 키만).
- 「이월」: round02b(spec §9 목록 전체), round04(Alertmanager 문 열기·비동기 조사), round03(MCP HTTP 인증).
- 「다음 라운드 진입점」: round02b — spec부터. 회사 서버의 기존 시스템·서버 설정을 바꾸는 작업이라 사용자 승인과 일정 조율 뒤에 한다.
- 「상태」 체크리스트는 템플릿 그대로 두고, 사실이 된 것만 체크한다 — 정적 리뷰(Task 20·21), CI green(이 Task의 push 뒤, 실행 번호와 커밋을 덧붙인다), 수동 스모크(Task 19), 문서 갱신, 클라우드 정지(「해당 없음」).

- [ ] **Step 2: `00_status.md`**

- 「최종 갱신」을 round02a로 바꾼다.
- 「현재 상태」에 round02a 한 줄(차트 셋·클러스터 안 MCP·에이전트 API, 스모크 결과 한 줄, 완료노트 링크)을 더한다.
- 「다음 할 일」을 round02b(GPU 티어 — k3s·GPU Operator·vLLM 이전·임베딩·Argo CD·SOPS, 착수 전 사용자 승인과 일정 조율)로 바꾼다.
- 라운드 이력에 행을 더한다.

```markdown
| round02a | [Helm 차트·클러스터 안 MCP 서버·에이전트 API](round02a-완료노트.md) · [교본](../guides/round02a/00-개요.md) | 리뷰·검증 중 |
```

- [ ] **Step 3: 커밋·push·CI**

```bash
git add docs/roadmap/round02a-완료노트.md docs/roadmap/00_status.md
git commit -m "[Docs] round02a — 완료노트(스모크·회귀 평가)와 현재 상태"
git push
```

Run: 이 커밋의 실행을 `gh run watch <databaseId> --exit-status`
Expected: 네 잡 success. 그 실행 번호를 완료노트 CI 줄에 적어 커밋·push한다(그 커밋의 CI도 green인지 본다).

---

### Task 23: `dev` 머지 (사용자 승인)

- [ ] **Step 1: 브리핑과 승인 요청**

머지 전에 이번 라운드에서 만든 것과 개념을 사용자가 익힐 수 있게 브리핑한다.
- 교본 「개념 입문」 요약 — server-side apply 충돌, NetworkPolicy, ServiceAccount 토큰, 상태 없는 MCP HTTP, 동기 API의 상태 코드.
- 직접 해 볼 명령: `bash scripts/dev-cluster.sh fault image-pull` → 포트포워드 + `curl POST /investigations` → `reset`, `kubectl --context kind-hoa auth can-i get secrets -n demo --as system:serviceaccount:hoa-system:hoa-mcp-read`, `helm --kube-context kind-hoa list -A`.

그다음 `dev` 머지 승인을 받는다. 승인 전 머지 금지.

- [ ] **Step 2: 머지·push**

```bash
git checkout dev
git pull --ff-only
git merge --no-ff feat/round02a-helm-charts -m "Merge feat/round02a-helm-charts into dev — round02a (Helm 차트·클러스터 안 MCP 서버·에이전트 API)"
git push
```

Run: `dev` 머지 커밋의 실행을 `gh run watch <databaseId> --exit-status`
Expected: 네 잡 success

- [ ] **Step 3: 상태 체크(`dev`에서)**

완료노트 「상태」의 `dev` 머지 승인 줄을 체크하고 머지 커밋을 덧붙인다. `00_status.md` 라운드 이력의 round02a 상태를 `dev 머지, main 대기`로 바꾼다.

```bash
git add docs/roadmap/round02a-완료노트.md docs/roadmap/00_status.md
git commit -m "[Docs] round02a — 완료노트 상태: dev 머지 승인 체크"
git push
```

---

### Task 24: 라운드 종료 (사용자 승인)

- [ ] **Step 1: 승인 받기**

`dev` CI green을 확인하고 사용자에게 라운드 종료(`dev → main` 머지 + push) 승인을 받는다. round02a에는 Argo CD가 아직 없어 `main` push가 배포를 일으키지 않는다.

- [ ] **Step 2: `/round-finish`**

`round-finish` 스킬 절차대로 한다(머지 전 확인 → `main` 머지 `Merge dev into main — round02a (Helm 차트·클러스터 안 MCP 서버·에이전트 API)` → push → `main` CI 확인 → `dev`로 돌아오기).

- [ ] **Step 3: 마지막 줄 체크(`dev`에만 push)**

완료노트 「상태」의 `dev→main` 줄을 체크하고 `main` 머지 커밋과 CI 실행 번호를 덧붙인다. `00_status.md` 라운드 이력의 round02a 상태를 `완료 (main 머지·push)`로 바꾼다.

```bash
git add docs/roadmap/round02a-완료노트.md docs/roadmap/00_status.md
git commit -m "[Docs] round02a — 완료노트 상태: main 머지·push 완료 체크"
git push
```

`main`은 다시 머지하지 않는다(다음 라운드 머지 때 함께 올라간다).
