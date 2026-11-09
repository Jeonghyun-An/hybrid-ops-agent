# 코딩 표준

새 프로젝트라 기존 반례 없이 시작한다. 규칙을 어긴 코드를 일부러 남겨야 하면 맨 아래 「백로그」에 파일 단위로 적는다 — code-reviewer는 백로그에 적힌 반례를 새 결함으로 다시 보고하지 않는다.

## 패키지 경계

- Python 컴포넌트는 uv 워크스페이스 멤버 하나씩이다(`agent`·`mcp_servers`·`graphrag`·`demo_app`·`eval`). 멤버마다 컨테이너 이미지가 따로 나가므로 의존성을 섞지 않는다 — 예: MCP 서버 이미지에 LangGraph가 들어가지 않는다.
- 멤버끼리 다른 멤버의 내부 모듈을 import하지 않는다. 공용 타입이 필요해지면 공용 멤버를 새로 만든다.
- 레이아웃: `<멤버>/src/<import 이름>/`, 테스트는 `<멤버>/tests/`. import 이름은 `hoa_` 접두(`hoa_agent`).

## 외부 호출 격리

- LLM 호출은 멤버마다 한 모듈(`llm.py`)을 거친다. 로컬 vLLM과 Azure OpenAI가 모두 OpenAI 호환 API라 클라이언트 하나를 설정으로 바꿔 쓴다. 그래프 노드·도구 코드가 HTTP 클라이언트를 직접 만들지 않는다.
- LLM 클라이언트는 주입받는다(모듈 전역에서 생성하지 않는다) — 테스트에서 가짜 LLM으로 바꿔 끼우기 위해서다.
- 쿠버네티스 API 호출은 MCP 서버 안에서만 한다. 에이전트는 클러스터를 MCP 도구로만 만진다.

## 타입·데이터

- 모든 함수 인자·반환에 타입힌트를 단다. `list[str]`·`X | None` 같은 최신 문법을 쓴다.
- 경계 데이터(LangGraph 상태, MCP 도구 입출력, API 요청·응답, 평가 시나리오)는 Pydantic v2 모델로 정의한다. 경계를 넘는 bare `dict`는 쓰지 않는다.
- I/O는 `async def`로 쓴다.

## 주석·docstring

- 기본은 주석 없음. 왜(why)가 코드만으로 드러나지 않을 때만 한 줄 docstring이나 주석을 단다.
- 무엇을 하는지 설명하는 주석, 현재 작업·이슈 번호를 참조하는 주석은 쓰지 않는다.

## 에러 처리

- 시스템 경계(API 입력, LLM 응답, MCP 도구 결과, k8s API 응답)에서만 검증한다. 내부 계층 간 호출은 서로를 신뢰한다.
- 구체적 예외를 잡는다. 넓은 `except Exception`으로 여러 실패를 삼키지 않는다.
- LLM 구조화 출력이 스키마를 어기면 기본값으로 조용히 메우지 않는다 — 재시도하거나 실패로 드러낸다.

## 테스트

- 새 기능은 실패하는 테스트 → 최소 구현 → 통과 순서(TDD)로 진행한다.
- LLM은 결정적 응답을 내는 가짜 구현으로 바꿔 끼운다. mock 범위는 외부 호출로만 한정한다.
- 쿠버네티스가 필요한 테스트는 kind에 붙는 통합 테스트로 분리하고 `integration` 마커를 단다(마커 등록은 round01).
- 테스트 이름은 동작을 문장으로 쓴다(`test_version_flag_prints_name_and_version`).

## 쿠버네티스·인프라

- 이미지 태그는 고정한다(`latest` 금지).
- 모든 컨테이너에 resources requests/limits를 둔다(집 PC 한 대에 많은 것이 같이 뜬다).
- ServiceAccount·RBAC는 최소 권한. 쓰기 권한은 데모 네임스페이스로 한정한다.
- 비밀값은 매니페스트에 평문으로 두지 않는다(온프레미스는 SOPS, AKS는 Key Vault + Workload Identity).
- 배포 리소스 이름은 kebab-case(`hoa-agent`).

## 네이밍

- 파일·함수: `snake_case`. 클래스: `PascalCase`.
- 1회성 실험 스크립트와 운영 스크립트를 구분해 위치시킨다(`CLAUDE.md` §2 — `scripts/` vs `research/`).

## 백로그

- 없음.
