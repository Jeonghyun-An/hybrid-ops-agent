# 현재 상태 · 다음 할 일

최종 갱신: 2026-11-16 (round01a — kind 개발 클러스터·데모 앱·MCP k8s-read)

## 현재 상태
- 전체 설계: `docs/superpowers/specs/2026-11-09-hybrid-ops-agent-design.md` — 2026-11-11에 클라우드를 GCP로, 온프레미스를 회사 GPU 서버로 바꾸고 두 실행 티어(GPU 티어·로컬 티어)를 들였다.
- round00 종료 — 저장소 골격·라운드 방식 이식. 상세: [round00-완료노트.md](round00-완료노트.md).
- round01a — 로컬 티어 기반: kind 클러스터 스크립트(`scripts/dev-cluster.sh`), 데모 앱 3서비스(`demo_app`), 장애 2종(image-pull·bad-config), MCP `k8s-read` 서버(`mcp_servers` — 읽기 도구 4개, 읽기 전용 RBAC), kind 통합 테스트 CI, 운영 문서의 GCP·두 티어 전환. 상세: [round01a-완료노트.md](round01a-완료노트.md).

## 다음 할 일
- round01b — 끝-끝 경로: 단일 LangGraph 에이전트 + LLM 두 종(Gemini 무료 등급·회사 GPU의 Gemma 4 26B, 클러스터는 로컬 티어 kind), 평가 러너 v0. 착수 전에 사용자가 (1) Google AI Studio에서 개인 계정으로 Gemini API 키를 받아 `.env`에 두고(결제 미연결), (2) 회사 GPU의 vLLM에 도구 호출 옵션(`--enable-auto-tool-choice --tool-call-parser gemma4`)을 켠다.

## 라운드 이력
| 라운드 | 요약 | 상태 |
|---|---|---|
| round00 | [저장소 골격 + 라운드 방식 이식](round00-완료노트.md) · [교본](../guides/round00/00-개요.md) | 완료 (main 머지·push) |
| round01a | [kind 개발 클러스터·데모 앱·MCP k8s-read](round01a-완료노트.md) · [교본](../guides/round01a/00-개요.md) | dev 머지, main 대기 |
