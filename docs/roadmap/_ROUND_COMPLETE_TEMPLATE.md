# round<NN> 완료노트

날짜: <YYYY-MM-DD>
브랜치: `<type>/round<NN>-<설명>`
spec: `docs/superpowers/specs/<파일>`
plan: `docs/superpowers/plans/<파일>`
교본: `docs/guides/round<NN>/<파일>`

## 한 일
-

## 결정
-

## 수치
(평가 러너·RAGAS·지연·비용처럼 이 라운드에서 잰 값. 잰 것이 없으면 "없음". 사람 검증 없이 LLM 채점만 거친 수치는 그렇다고 적는다.)
-

## Azure 비용
(이 라운드에서 만들거나 켠 Azure 리소스와 끈 시각. 쓰지 않았으면 "사용 안 함".)
-

## 이월
-

## 다음 라운드 진입점
-

## 상태
- [ ] code-reviewer 정적 리뷰 통과(발견 사항 반영 완료)
- [ ] CI green
- [ ] 수동 스모크 확인
- [ ] 문서 갱신(교본·00_status·라이브에서 새로 겪은 함정을 `docs/ops/recurring-gotchas.md`에 추가)
- [ ] Azure 리소스 정지 확인(AKS를 켠 라운드만 — `az aks show -g <그룹> -n <클러스터> --query powerState.code`가 `Stopped`)
- [ ] `dev` 머지 승인
- [ ] `dev→main` 머지 + push 완료
