# 현재 상태 · 다음 할 일

최종 갱신: 2026-11-16 (round01b — LangGraph 에이전트·LLM 두 종·평가 러너 v0)

## 현재 상태
- 전체 설계: `docs/superpowers/specs/2026-11-09-hybrid-ops-agent-design.md` — 2026-11-11에 클라우드를 GCP로, 온프레미스를 회사 GPU 서버로 바꾸고 두 실행 티어(GPU 티어·로컬 티어)를 들였다. 2026-11-16에 기본 LLM을 회사 GPU의 Gemma로 바꿨다(Gemini는 회사망 밖의 대체·평가 비교 기준).
- round00 종료 — 저장소 골격·라운드 방식 이식. 상세: [round00-완료노트.md](round00-완료노트.md).
- round01a — 로컬 티어 기반: kind 클러스터 스크립트(`scripts/dev-cluster.sh`), 데모 앱 3서비스(`demo_app`), 장애 2종(image-pull·bad-config), MCP `k8s-read` 서버(`mcp_servers` — 읽기 도구 4개, 읽기 전용 RBAC), kind 통합 테스트 CI, 운영 문서의 GCP·두 티어 전환. 상세: [round01a-완료노트.md](round01a-완료노트.md).
- round01b — 끝-끝 경로: 손으로 짠 LangGraph 에이전트(`agent` — MCP `k8s-read` 도구로 조사 → 구조화 진단, `hoa investigate`), LLM 두 종(기본 회사 GPU의 Gemma, 비교 기준 Gemini 무료 등급 Flash-Lite), 평가 러너 v0(`eval` — 장애 주입·규칙 채점, `hoa-eval`). 평가: Gemma가 장애 2종을 각각 3/3 맞힘(Gemini 기준점 2/2). 상세: [round01b-완료노트.md](round01b-완료노트.md).

## 다음 할 일
- round02 — GPU 티어: 회사 GPU 서버에 k3s(+ GPU Operator)를 세우고, 기존 Gemma vLLM을 k3s 관리로 옮기고, 데모 앱·MCP 서버·에이전트를 Helm 차트로 올리고, 임베딩 모델을 정한다. 회사 서버의 기존 시스템·서버 설정을 바꾸는 작업이라 착수 전에 사용자 승인과 일정 조율이 필요하다(`CLAUDE.md` §4).

## 라운드 이력
| 라운드 | 요약 | 상태 |
|---|---|---|
| round00 | [저장소 골격 + 라운드 방식 이식](round00-완료노트.md) · [교본](../guides/round00/00-개요.md) | 완료 (main 머지·push) |
| round01a | [kind 개발 클러스터·데모 앱·MCP k8s-read](round01a-완료노트.md) · [교본](../guides/round01a/00-개요.md) | 완료 (main 머지·push) |
| round01b | [LangGraph 에이전트·LLM 두 종·평가 러너 v0](round01b-완료노트.md) · [교본](../guides/round01b/00-개요.md) | dev 머지, main 대기 |
