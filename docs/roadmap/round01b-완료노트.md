# round01b 완료노트

날짜: 2026-11-16
브랜치: `feat/round01b-agent-eval`
spec: `docs/superpowers/specs/2026-11-16-round01b-agent-llm-eval-design.md`
plan: `docs/superpowers/plans/2026-11-16-round01b-agent-llm-eval.md`
교본: `docs/guides/round01b/00-개요.md`

## 한 일
- 에이전트(`agent`): 손으로 짠 LangGraph `StateGraph`(investigate → tools ↺ → diagnose)를 만들었다.
  - 조사 예산: 도구 6번, 문맥 26K 토큰.
  - 구조화 진단 `Diagnosis`: 원인 라벨 7개·대상·근거 인용·확신도·한국어 요약.
  - 형식이 깨진 도구 호출에는 오류 답을 붙이고 다시 부르게 한다.
  - `hoa investigate` CLI: 진단 JSON·한국어 요약, 종료 코드 0·1·2·3, 기본 모델 `gemma`.
- LLM 두 종(`llm.py`): 기본은 회사 GPU vLLM의 `gemma4-26b-a4b`이고, Gemini 무료 등급 `gemini-3.5-flash-lite`는 회사망 밖의 대체이자 비교 기준이다. 둘 다 같은 OpenAI 호환 클라이언트를 쓴다. Gemini 3의 도구 호출 서명(`thought_signature`)은 `ChatOpenAICompat`이 되돌려 준다.
- MCP 연결: `langchain-mcp-adapters`로 `hoa-mcp-k8s-read`를 stdio로 띄운다. 서버 프로세스에는 자기 설정만 넘긴다. 서버가 시작하다 죽으면 설정 오류(2)로 낸다.
- 평가 러너 v0(새 멤버 `eval`):
  - 시나리오 YAML 2종이 장애 대상의 정본이다. 네임스페이스는 `demo`, 패치는 `deploy/kind/faults/`로 제한한다.
  - 한 회차는 주입 → 증상 대기 → 조사(하위 프로세스) → 복구(종료 파드 대기·이벤트 삭제) → 규칙 채점 순서다.
  - 한도나 설정 오류를 받으면 배치를 멈춘다.
  - `hoa-eval run`·`report`를 만들었다.
- 테스트: 단위 230개(대본 모델·가짜 kubectl·`MockTransport`), kind 통합 8개(에이전트 배선·러너 추가). CI는 바꾸지 않았다 — 새 멤버 테스트가 기존 잡에서 돈다.
- 문서:
  - `CLAUDE.md` 보완 3곳(사용자 승인), `GIT_WORKFLOW.md`·`README.md` 실행법, `.env.example`.
  - 전체 설계: 기본 LLM을 Gemma로 바꾸고 §10의 두 결정을 적었다.
  - 코딩 표준, 반복 함정 7~11번.
  - round00 문서의 로컬 경로와 사내 프로젝트 이름을 일반 표현으로 바꿨다(사용자 결정 — 현재 파일만).
- 교본: `docs/guides/round01b/` — 개념 입문 16절, 파일 51개 전체 수록, 평가 결과, 면접식 Q&A 15문항.

## 결정
- 그래프는 `create_react_agent` 대신 직접 짰다 — 노드·엣지·상태를 손으로 다뤄 보려는 학습 목적(사용자 결정 2026-11-16).
- MCP 연결은 `langchain-mcp-adapters`를 쓴다 — LangChain 생태계를 경험하려는 사용자 결정. 대가로 MCP SDK는 1.x(`mcp<2`)에 묶인다.
- 기본 LLM은 회사 GPU의 Gemma다(사용자 결정, plan 검토 중). 요청 한도가 없고 클러스터 데이터가 회사 밖으로 나가지 않는다. 평가에서 Gemini는 시나리오마다 1회만 비교 기준으로 돌렸다. 전체 설계의 모델 분업도 「기본 Gemma」로 바꿨다(분업 비율은 round07 라우팅 실험).
- Gemini 프로필의 기본 모델은 `gemini-3.5-flash-lite`다. 3.5 Flash는 무료 등급 하루 20회에 조사 1건이 약 200초였다(반복 함정 10번).
- Gemini 3의 `thought_signature`는 `ChatOpenAI` 하위 클래스로 보존했다. `langchain-google-genai`로 바꾸면 클라이언트가 둘이 된다. 비공개 메서드를 재정의하므로 `langchain-openai<1.9`로 묶고 `MockTransport` 테스트로 지킨다.
- 토큰 예산은 「마지막 요청의 입력 토큰」(= 문맥 크기)으로 센다.
- 진단 지시에 원인 라벨 7개의 정의와 「증상이 아니라 근본 원인」 규칙을 넣었다(사용자 결정, 평가 중).
  - 없을 때 Gemma는 bad-config에서 단서를 찾고도 `unknown`으로 피했다(0/3).
  - 모든 라벨에 통하는 정의라서 두 시나리오에 맞춘 과적합으로 보지 않았다. round07에서 시나리오를 늘려 다시 확인한다.
- 채점은 규칙으로만 한다.
  - 인용 확인은 따옴표·백슬래시·공백 차이를 무시하되, 8자 미만과 단어 중간 일치는 인정하지 않는다.
  - 모델이 답할 기회가 없던 회차(한도·설정 오류·증상 없음)는 정답률 분모에서 뺀다.
- 러너는 에이전트를 하위 프로세스로 부른다 — 멤버 경계를 지키고, 실제 사용자가 쓰는 CLI를 그대로 평가하기 위해서다.
- 정적 리뷰(에이전트·평가 러너·문서 세 영역)는 high 0건, medium 6건이었다. medium은 모두 고쳤고, 고친 뒤 같은 리뷰어로 재검토했다. 고치지 않은 low와 그 이유:
  - 진단 `target`에 형식 제약(`pattern`)을 두지 않았다 — Gemini strict 스키마가 `pattern`을 받는지 확인하지 못했다. 채점은 정확히 비교한다.
  - `ToolNode(handle_tool_errors=True)`는 모든 예외를 오류 메시지로 바꾸는 설정을 그대로 둔다. 모델이 오류를 읽고 고칠 수 있고, 결과 표의 「도구 오류」 열로 드러난다. 서버가 조사 도중 죽어도 조사는 0으로 끝날 수 있다.
  - `run_investigation`에 모델·도구 주입점을 두지 않았다 — 조립은 kind 통합 테스트와 수동 스모크로 확인한다.
  - 요약 표는 프로필(gemma·gemini)로 묶는다. 같은 프로필에 모델 이름이 여럿이면 모델 열에 모두 보인다.
  - id 없는 깨진 도구 호출에는 답을 붙이지 않는다. OpenAI 호환 엔드포인트는 늘 id를 준다.
  - 예외가 난 회차에서 복구까지 실패하면 그 사실이 기록되지 않는다. 다음 실행이 시작할 때 복구한다.
  - `dev-cluster.sh up`(이미 있는 클러스터)에는 종료 파드 대기가 없다. `reset`·러너·통합 테스트에는 있다.
  - 다시 돌린 회차의 번호가 1부터 다시 시작한다. 회차별 표는 결과 파일 순서대로 보인다.
  - plan(기록 문서)의 Task 19 문구는 고치지 않았다(「한도 회차는 실패로 남는다」 → 이제 「제외」 열).

## 수치
규칙 채점이다(LLM 채점 없음). 개발 PC의 kind, 2026-11-16, 진단 지시에 라벨 정의를 넣은 뒤 처음부터 다시 돌린 결과다. `uv run hoa-eval report eval/results/*.jsonl`.

| 시나리오 | 모델 | 채점 회차 | 원인 정답 | 대상 정답 | 인용 확인 | 도구 호출 평균 | 도구 오류 | 형식 깨진 호출 | 시간 평균(초) | 입력 토큰 평균 | 에이전트 실패 | 제외 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| bad-config | gemma4-26b-a4b | 3 | 3/3 | 3/3 | 5/5 | 3.7 | 0 | 0 | 14.9 | 10,433 | 0 | 0 |
| image-pull | gemma4-26b-a4b | 3 | 3/3 | 3/3 | 7/7 | 2.0 | 0 | 0 | 12.1 | 6,800 | 0 | 0 |
| bad-config | gemini-3.5-flash-lite | 1 | 1/1 | 1/1 | 1/1 | 4.0 | 0 | 0 | 10.8 | 14,274 | 0 | 0 |
| image-pull | gemini-3.5-flash-lite | 1 | 1/1 | 1/1 | 1/1 | 3.0 | 0 | 0 | 8.5 | 12,241 | 0 | 0 |

| 시나리오 | 모델 | 회차 | 원인 | 인용 | 도구 | 도구 오류 | 시간(초) | 멈춘 이유 | 오류 |
|---|---|---|---|---|---|---|---|---|---|
| bad-config | gemma4-26b-a4b | 1 | bad_config | 2/2 | 3 | 0 | 18.7 | answered | - |
| image-pull | gemma4-26b-a4b | 1 | image_pull_error | 2/2 | 2 | 0 | 8.4 | answered | - |
| bad-config | gemma4-26b-a4b | 2 | bad_config | 2/2 | 4 | 0 | 6.0 | answered | - |
| image-pull | gemma4-26b-a4b | 2 | image_pull_error | 2/2 | 2 | 0 | 16.1 | answered | - |
| bad-config | gemma4-26b-a4b | 3 | bad_config | 1/1 | 4 | 0 | 19.8 | answered | - |
| image-pull | gemma4-26b-a4b | 3 | image_pull_error | 3/3 | 2 | 0 | 11.9 | answered | - |
| bad-config | gemini-3.5-flash-lite | 1 | bad_config | 1/1 | 4 | 0 | 10.8 | answered | - |
| image-pull | gemini-3.5-flash-lite | 1 | image_pull_error | 1/1 | 3 | 0 | 8.5 | answered | - |

- 완료 기준을 넘었다 — Gemma가 두 시나리오 모두 3/3이다(기준은 3회 중 2회 이상). 인용은 모두 실제 도구 출력에서 확인됐다. 형식이 깨진 도구 호출·도구 오류·예산 초과는 없었다(모두 `answered`).
- 라벨 정의를 넣기 전, 같은 날 같은 클러스터의 Gemma는 bad-config 0/3(세 번 모두 `unknown`, 인용 9/9, 도구 4번, 입력 11,826 토큰), image-pull 3/3이었다. 원인 분석은 위 「결정」과 교본 §1.8에 있다.
- 비용: image-pull은 도구 2번(파드 목록·Deployment)으로 끝났다. bad-config는 직전 로그(필요하면 이벤트)까지 봐서 도구 3~4번, 입력 토큰이 1.5배다. Gemma 조사 1건은 모델 호출 4~6번, 입력 6.8K~12.4K 토큰이었다(문맥 예산 26K 안).
- 시간은 흔들렸다. Gemma는 같은 조사가 6~20초였다(수동 스모크 때는 5초 안팎). 회사 GPU를 다른 서비스와 함께 써서 부하에 따라 달라진다. Gemini Flash-Lite는 이번에 8~11초였지만 plan 작성 때는 26초가 걸린 적이 있다.
- Gemini는 시나리오마다 1회라 정답률 비교에는 표본이 작다. 「기준점과 같은 답을 낸다」는 방향만 보여 준다.
- 「형식 깨진 호출」은 도구 호출로 파싱됐지만 인자 JSON이 깨진 경우만 센다. 도구 호출 형식 없이 글로만 나온 호출은 잡지 못한다(spec §7).

## 클라우드 비용
- 사용 안 함. Gemini는 결제를 연결하지 않은 무료 등급 키만 썼다(요청 수는 하루 한도 안).

## 이월
- round02:
  - MCP 서버·에이전트를 GPU 티어 k3s 안으로 옮긴다(Helm).
  - 기존 Gemma vLLM을 k3s 관리로 옮기고, 임베딩 모델을 정한다.
  - round01a 이월분: Helm `templates/` check-yaml 제외, `k3s.yaml` 무시, SOPS 예외 규칙, helm 버전 고정, kubeconform.
- round04: Langfuse(OpenTelemetry) 추적, Alertmanager 웹훅으로 실제 경보 받기 — 지금의 경보 문장을 실제 경보로 바꾼다.
- round06: supervisor·서브에이전트, Postgres 체크포인트, 사람 승인, 쓰기 도구.
- round07:
  - 시나리오 확장(oom·probe·selector·downstream — 라벨은 이미 있다), 반복 횟수 늘리기, 프롬프트 인젝션 시나리오.
  - 라우팅 실험: 기본 Gemma가 기준에 못 미치는 역할만 Gemini로 돌린다(Gemini 3.5 Flash와 Flash-Lite 비교 포함).
  - 글로만 나온 도구 호출 감지, 라벨 정의의 일반화 확인.
- `langchain-openai`를 1.9 이상으로 올릴 때 `ChatOpenAICompat`의 재정의 메서드를 확인한다(서명 테스트가 먼저 깨진다). LangChain이 `extra_content`를 지원하면 하위 클래스를 지운다.

## 다음 라운드 진입점
- round02 — spec부터. GPU 티어 k3s 설치와 기존 vLLM 이전은 회사 서버의 기존 시스템·서버 설정을 바꾸는 작업이라 사용자 승인 뒤에 한다(`CLAUDE.md` §4).

## 상태
- [x] code-reviewer 정적 리뷰 통과(high·medium 수정, low는 수정하거나 「결정」에 이유)
- [ ] CI green(작업 브랜치 마지막 커밋)
- [x] 수동 스모크 확인
- [x] 문서 갱신(교본·00_status·실제로 돌려 보며 새로 겪은 함정(개발 환경 포함)을 `docs/ops/recurring-gotchas.md`에 추가)
- [x] 클라우드 리소스 정지 확인 — 해당 없음(GKE를 켜지 않은 라운드)
- [ ] `dev` 머지 승인
- [ ] `dev→main` 머지 + push 완료
