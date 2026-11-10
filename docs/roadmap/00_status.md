# 현재 상태 · 다음 할 일

최종 갱신: 2026-11-10 (round00 종료 — 저장소 골격·라운드 방식 이식)

## 현재 상태
- 전체 설계 확정: `docs/superpowers/specs/2026-11-09-hybrid-ops-agent-design.md`.
- round00 종료 — uv 워크스페이스(`agent` 멤버, `hoa` CLI), pre-commit(ruff·gitleaks), GitHub Actions CI, devcontainer, 라운드 운영 문서(CLAUDE.md·GIT_WORKFLOW.md·코딩 표준·반복 함정·템플릿·code-reviewer·round-finish). 상세: [round00-완료노트.md](round00-완료노트.md).

## 다음 할 일
- `CLAUDE.md` 후속 수정(사용자 허락 대기) — 목록은 [round00-완료노트.md](round00-완료노트.md) 「이월」.
- round01 — 끝-끝 경로: 개발 PC kind + 데모 앱(gateway·orders·inventory) + 장애 2종 + MCP `k8s-read` + 단일 LangGraph 에이전트 + Azure OpenAI, 평가 러너 v0. 착수 전에 Azure 구독과 Azure OpenAI 배포 모델·리전을 정한다(spec §10).

## 라운드 이력
| 라운드 | 요약 | 상태 |
|---|---|---|
| round00 | [저장소 골격 + 라운드 방식 이식](round00-완료노트.md) · [교본](../guides/round00/00-개요.md) | 완료 (main 머지·push) |
