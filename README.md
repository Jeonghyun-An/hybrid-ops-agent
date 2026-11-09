# hybrid-ops-agent

온프레미스(집 GPU PC의 k3s)와 Azure(AKS·Azure OpenAI)를 함께 쓰는 **쿠버네티스 운영 에이전트**. 클러스터 장애를 MCP 도구로 조사하고, GraphRAG로 비슷한 과거 장애와 런북을 찾아 원인을 진단하고, 사람 승인을 받아 조치한다.

> 학습 목적의 개인 프로젝트다. 라운드 단위로 쌓아 가며 라운드마다 설계(spec)·계획(plan)·완료노트·교본을 남긴다.

## 무엇을 해 보나

| 기술 | 이 프로젝트에서의 역할 |
|---|---|
| LangGraph 멀티에이전트 | supervisor + 서브에이전트, 체크포인트(중단·재개), interrupt로 사람 승인 |
| MCP 서버·클라이언트 | 클러스터 조회·조치·관측 도구를 MCP 서버로 직접 만들고 에이전트가 MCP로 호출 |
| GraphRAG | Neo4j에 클러스터 구조 + 장애 지식 그래프, 벡터 RAG와 진단 정확도 비교 |
| 쿠버네티스 + IaC | 온프레미스 k3s + Azure AKS, Terraform, Helm, Argo CD, GitHub Actions |
| 관측·자동 평가 | Prometheus·Loki·Tempo, OpenTelemetry → Langfuse, 장애 시나리오 자동 채점 |

## 어디서 무엇이 도나

| 위치 | 켜짐 | 역할 |
|---|---|---|
| 집 RTX 3060 PC (Ubuntu + k3s) | 상시 | 로컬 LLM, Neo4j, Postgres, 관측 스택, Argo CD |
| Azure AKS | 작업할 때만 | 상태 없는 앱(에이전트 API·MCP 서버·웹 UI) |
| Azure OpenAI | 사용량 과금 | 계획·진단·그래프 추출 |

자세한 설계와 라운드 로드맵: [전체 설계 spec](docs/superpowers/specs/2026-11-09-hybrid-ops-agent-design.md) · 진행 상황: [docs/roadmap/00_status.md](docs/roadmap/00_status.md)

## 시작하기

[uv](https://docs.astral.sh/uv/)가 필요하다(Python 3.12는 uv가 준비한다).

```bash
uv sync
uv run pre-commit install
uv run pytest
uv run hoa --version
```

devcontainer를 쓰면 uv·kubectl·helm·terraform·az가 갖춰진 컨테이너에서 같은 명령을 쓴다(`.devcontainer/`).

## 문서

- [CLAUDE.md](CLAUDE.md) — 작업 진입점(어떤 문서를 어디서 보나)
- [GIT_WORKFLOW.md](GIT_WORKFLOW.md) — 브랜치·커밋·품질 게이트·라운드 생애주기
- [docs/standards/coding-standard.md](docs/standards/coding-standard.md) — 코딩 표준
