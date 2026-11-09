---
name: round-finish
description: hybrid-ops-agent 라운드를 종료할 때 사용 — dev에 머지된 라운드를 검증 확인 후 dev→main 머지 + origin push. "라운드 끝내자/라운드 종료/main 올리고 push" 같은 요청에 활성화. 작업 브랜치→dev 머지에는 쓰지 않는다.
---

# round-finish — 라운드 종료 절차

한 라운드(사용자 프롬프트 1개의 구현)가 검증·리뷰까지 끝나 `main`에 올리고 원격에 동기화하는 절차다. 상세 흐름은 `GIT_WORKFLOW.md` §라운드 생애주기.

## 전제 (확인 후 진행)
- 작업 브랜치가 이미 `dev`에 머지돼 있다(사용자 승인 하).
- `dev`의 최신 CI가 green이다: `gh run list --branch dev --limit 1`의 결론이 `success`.
- 핵심 기능 수동 스모크를 확인했다.
- 사용자가 라운드 종료를 승인했다(이 단계는 `main`을 움직이므로 임의 진행 금지). round02부터는 `main` push가 Argo CD 배포를 일으킨다.
- **`main`·`dev` 체크아웃은 주 저장소 디렉토리에서 한다** — 라운드 작업을 격리 워크트리에서 했다면 그 워크트리 안에서 `main`을 체크아웃하지 않는다(그 라운드의 신규 파일이 아직 `main`에 없어 사라져 보이고, `main`·`dev`가 다른 워크트리에 물려 있으면 체크아웃 자체가 거부된다).

## 절차
1. 검증 재확인 — CI green, 핵심 동작 스모크 확인.
2. 완료노트(`docs/roadmap/round<NN>-완료노트.md`)의 `## 상태` 체크리스트(정적 리뷰·CI·스모크·문서 갱신·Azure 정지·머지 승인) 확인.
3. 라운드 중 라이브에서 새로 겪은 함정이 있으면 `docs/ops/recurring-gotchas.md`에 추가됐는지 확인.
4. `docs/roadmap/00_status.md` 갱신 확인(최종 갱신 날짜·현재 상태·다음 할 일·라운드 이력 — 라운드 이력만 바꾸고 현재 상태를 그대로 두지 않는다).
5. Azure를 쓴 라운드면 AKS가 꺼져 있는지 확인: `az aks show -g <그룹> -n <클러스터> --query powerState.code` → `Stopped`.
6. **머지 전 확인**:
   ```bash
   git rev-list --count main..dev   # 0이면 중단 — dev에 이번 라운드가 없다, 먼저 작업 브랜치→dev 머지부터
   git fetch origin
   git rev-list --count main..origin/main   # 0이 아니면 중단 — 원격 main이 앞서 있다, 먼저 받아서 정리
   ```
7. `dev → main` 머지
   ```bash
   git checkout main
   git merge --no-ff dev -m "Merge dev into main — round<NN> (<요약>)"
   ```
8. origin push
   ```bash
   git push origin main && git push -u origin dev
   ```
   (`dev`가 이미 원격에 있고 추적 중이면 `-u` 없이 `git push origin dev`로 충분.)
9. push 뒤 `main` CI 확인: `gh run list --branch main --limit 1`.
10. 작업 복귀: `git checkout dev`.

## 주의
- 평소 작업은 `dev`에서 분기 → 작업 브랜치. `main` 직접 작업은 이 종료 절차에서만.
- 비밀정보·kubeconfig·Terraform state는 커밋·push 금지(`.gitignore`). public 저장소다.
- round02에서 Argo CD가 들어오면 이 절차에 "push 뒤 Argo CD 동기화 상태 확인" 단계를 더한다.
