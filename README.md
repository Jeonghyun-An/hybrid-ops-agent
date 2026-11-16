# hybrid-ops-agent

온프레미스(회사 GPU 서버의 k3s)와 GCP(GKE·Gemini)를 함께 쓰는 **쿠버네티스 운영 에이전트**. 클러스터 장애를 MCP 도구로 조사하고, GraphRAG로 비슷한 과거 장애와 런북을 찾아 원인을 진단하고, 사람 승인을 받아 조치한다. 같은 코드를 GPU 티어(회사 GPU 서버)와 로컬 티어(개발 PC의 kind, GPU 없음)로 돌린다.

> 학습 목적의 개인 프로젝트다. 라운드 단위로 쌓아 가며 라운드마다 설계(spec)·계획(plan)·완료노트·교본을 남긴다.

## 무엇을 해 보나

| 기술 | 이 프로젝트에서의 역할 |
|---|---|
| LangGraph 멀티에이전트 | supervisor + 서브에이전트, 체크포인트(중단·재개), interrupt로 사람 승인 |
| MCP 서버·클라이언트 | 클러스터 조회·조치·관측 도구를 MCP 서버로 직접 만들고 에이전트가 MCP로 호출 |
| GraphRAG | Neo4j에 클러스터 구조 + 장애 지식 그래프, 벡터 RAG와 진단 정확도 비교 |
| 쿠버네티스 + IaC | 온프레미스 k3s + GCP GKE, Terraform, Helm, Argo CD, GitHub Actions |
| 관측·자동 평가 | Prometheus·Loki·Tempo, OpenTelemetry → Langfuse, 장애 시나리오 자동 채점 |

## 어디서 무엇이 도나

| 위치 | 켜짐 | 역할 |
|---|---|---|
| 회사 GPU 서버 (k3s) — GPU 티어 | 상시 | 온프레미스 LLM(vLLM의 Gemma), Neo4j, Postgres, 관측 스택, Argo CD, 데모 앱·에이전트·MCP 서버 |
| 개발 PC (kind) — 로컬 티어 | 개발할 때 | 데모 앱·MCP 서버·에이전트(LLM은 회사망 안이면 GPU 티어의 Gemma, 밖이면 Gemini 무료 등급), 통합 테스트 — GPU 없이 돈다 |
| GCP GKE | 작업할 때만 | 상태 없는 앱(에이전트 API·MCP 서버·웹 UI), 데모 앱 사본 |
| Gemini | 무료 등급 키(round01~02) → Vertex AI(round03~) | 회사 GPU의 Gemma에 닿지 않을 때의 대체, 평가의 비교 기준 |
| Langfuse Cloud | 상시(SaaS) | 에이전트 트레이스·평가 데이터셋 |

자세한 설계와 라운드 로드맵: [전체 설계 spec](docs/superpowers/specs/2026-11-09-hybrid-ops-agent-design.md) · 진행 상황: [docs/roadmap/00_status.md](docs/roadmap/00_status.md)

## 시작하기

[uv](https://docs.astral.sh/uv/) 0.11(0.11.31 이상 — `pyproject.toml`의 `[tool.uv] required-version`)이 필요하다(Python 3.12는 uv가 준비한다). CI 결과 확인과 라운드 종료 절차에는 [GitHub CLI](https://cli.github.com/)(`gh auth login`)를 쓴다.

```bash
uv sync
uv run pre-commit install
uv run pytest
uv run hoa --version
```

로컬 티어 개발 클러스터에는 Docker Desktop, [kind](https://kind.sigs.k8s.io/) v0.33.0, kubectl(Docker Desktop에 들어 있다)이 필요하다(Windows는 Git Bash에서 실행한다).

```bash
bash scripts/dev-cluster.sh up
uv run pytest -m integration
```

`up`은 kind 클러스터 `hoa`에 데모 앱(gateway·orders·inventory)을 띄우고 MCP 서버용 읽기 전용 kubeconfig를 만든다. `fault image-pull`·`fault bad-config`로 장애를 심고 `reset`으로 되돌린다. 클러스터를 지울 때는 `down`.

에이전트의 기본 LLM은 GPU 티어의 Gemma(vLLM)이고, 회사망 밖에서는 Gemini(무료 등급 API 키)를 `--model gemini`로 쓴다. `.env.example`을 `.env`로 복사해 값을 채우고(`.env`는 커밋하지 않는다), 장애를 심은 클러스터에서 조사하거나 평가를 돌린다.

```bash
bash scripts/dev-cluster.sh fault image-pull
uv run --env-file .env hoa investigate "KubeDeploymentRolloutStuck — namespace=demo deployment=orders: rollout has not progressed"
bash scripts/dev-cluster.sh reset
uv run --env-file .env hoa-eval run --repeat 3
```

`hoa investigate`는 진단 JSON을 표준출력에, 한국어 요약을 표준오류에 쓴다. `hoa-eval run`은 장애 주입 → 증상 대기 → 조사 → 채점 → 복구를 시나리오(`eval/scenarios/`)마다 돌리고 결과를 `eval/results/`에 남긴다.

devcontainer(`.devcontainer/`)를 쓰면 uv·kubectl·helm·terraform이 갖춰진 컨테이너에서 `uv run pytest`·`uv run hoa --version`을 그대로 쓴다(`uv sync`는 컨테이너를 만들 때 끝난다). `pre-commit install`과 커밋, kind 클러스터는 호스트에서 쓴다 — [GIT_WORKFLOW.md](GIT_WORKFLOW.md) §개발 환경.

## 문서

- [CLAUDE.md](CLAUDE.md) — 작업 진입점(어떤 문서를 어디서 보나)
- [GIT_WORKFLOW.md](GIT_WORKFLOW.md) — 브랜치·커밋·품질 게이트·라운드 생애주기
- [docs/standards/coding-standard.md](docs/standards/coding-standard.md) — 코딩 표준
