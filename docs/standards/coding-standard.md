# 코딩 표준

새 프로젝트라 기존 반례 없이 시작한다. 규칙을 어긴 코드를 일부러 남겨야 하면 맨 아래 「백로그」에 파일 단위로 적는다 — code-reviewer는 백로그에 적힌 반례를 새 결함으로 다시 보고하지 않는다.

## 패키지 경계

- Python 컴포넌트는 uv 워크스페이스 멤버 하나씩이다(`agent`·`mcp_servers`·`graphrag`·`demo_app`·`eval`). 멤버마다 컨테이너 이미지가 따로 나가므로 의존성을 섞지 않는다 — 예: MCP 서버 이미지에 LangGraph가 들어가지 않는다.
- 멤버끼리 다른 멤버의 내부 모듈을 import하지 않는다. 공용 타입이 필요해지면 공용 멤버를 새로 만든다.
- 레이아웃: `<멤버>/src/<import 이름>/`, 테스트는 `<멤버>/tests/`. import 이름은 `hoa_` 접두(`hoa_agent`).
- 새 멤버를 더할 때는 루트 `pyproject.toml`의 다섯 곳을 같이 고친다 — `[tool.uv.workspace] members`·`[tool.uv.sources]`·`dependencies`·ruff `src`·pytest `testpaths`. `testpaths`를 빠뜨리면 새 멤버의 테스트가 CI에서 조용히 빠진다. 멤버 이미지를 만드는 `deploy/docker/Dockerfile`과 그 옆 `Dockerfile.dockerignore`에도 새 멤버의 `pyproject.toml`을 더한다 — `uv sync --locked`가 모든 멤버의 pyproject를 요구한다.

## 외부 호출 격리

- LLM 호출은 멤버마다 한 모듈(`llm.py`)을 거친다. 온프레미스 vLLM(Gemma)과 클라우드 Gemini가 모두 OpenAI 호환 API라 클라이언트 하나를 설정으로 바꿔 쓰고(GPU 티어·로컬 티어도 설정 묶음으로 바꾼다), 역할(triage·diagnose·extract 등)마다 어느 모델을 쓸지도 `llm.py`가 정한다. 그래프 노드·도구 코드가 HTTP 클라이언트를 직접 만들지 않는다. 엔드포인트마다 다른 점(Gemini 3가 도구 호출에 붙이는 `thought_signature`를 다음 요청에 되돌려 주기 등)도 `llm.py`가 흡수한다.
- LLM을 쓰는 멤버(`agent`·`graphrag`·`eval`)가 각자 `llm.py`를 두는 중복은 허용한다(멤버 경계를 지키는 값). 공용 멤버로 뺄지는 두 번째 멤버가 LLM을 쓰기 시작하는 라운드에 정한다.
- LLM 클라이언트는 주입받는다(모듈 전역에서 생성하지 않는다) — 테스트에서 가짜 LLM으로 바꿔 끼우기 위해서다.
- 에이전트(`agent`)는 클러스터를 MCP 도구로만 만진다. 쿠버네티스 API 클라이언트는 MCP 서버(`mcp_servers`) 안에 두고, 예외는 에이전트가 아닌 두 곳뿐이다 — `graphrag` 구조 층 동기화 잡(읽기 전용 ServiceAccount)과 `eval` 러너의 장애 주입·복구(데모 네임스페이스 한정).
- MCP 도구 출력은 크기 상한을 둔다 — 응답 하나를 직렬화한 크기가 12,000자를 넘지 않게 자르고(가장 작은 문맥인 GPU 티어 32K 기준), 목록을 잘랐으면 `truncated`로 알린다. 비밀값으로 보이는 이름의 환경변수 값은 가리고, 값 안의 비밀(URL 비밀번호·JWT·PEM)은 로그·이벤트까지 지우고, Secret 참조는 이름만 보인다(목록은 `mcp_servers/src/hoa_mcp/k8s_read/convert.py`). 예상 밖 예외는 서버 로그에 traceback을 남기고 모델에는 예외 종류만 알린다 — 원문에 내부 주소가 섞일 수 있다. 이름 인자는 쿠버네티스 이름 규칙으로 검증한다.
- 클러스터를 부르는 스크립트·도구·테스트는 kubectl 컨텍스트나 kubeconfig 파일을 명시한다 — 개발 PC에 다른 클러스터 컨텍스트가 같이 있어도 엉뚱한 곳에 닿지 않게.
- 이 절의 격리 규칙(LLM은 `llm.py`, 클러스터는 MCP 도구)은 제품 코드의 규칙이다. 테스트와 `scripts/`의 운영 도구는 관리자 컨텍스트로 장애를 주입하고 상태를 볼 수 있다 — 컨텍스트를 명시하는 규칙은 똑같이 지킨다.

## 타입·데이터

- 모든 함수 인자·반환에 타입힌트를 단다(테스트 포함 — ruff `ANN`이 강제한다). `list[str]`·`X | None` 같은 최신 문법을 쓴다.
- 경계 데이터(LangGraph 상태, MCP 도구 입출력, API 요청·응답, 평가 시나리오)는 Pydantic v2 모델로 정의한다. 경계를 넘는 bare `dict`는 쓰지 않는다.
- 네트워크 I/O(LLM·MCP·DB·HTTP·k8s API)는 `async def`로 쓴다. CLI 진입점(`main`)은 동기로 두고 필요하면 `asyncio.run`으로 감싼다.
- 하위 프로세스(`kubectl`·`hoa` CLI)를 하나씩 차례로 부르는 도구(평가 러너)는 동기 `subprocess.run`을 쓰고 컨텍스트·제한 시간·`encoding="utf-8"`(읽는 쪽은 `errors="replace"`도)을 명시한다. 하위 프로세스로 JSON을 넘기는 CLI는 표준출력을 UTF-8로 고정한다(`docs/ops/recurring-gotchas.md` 8번).

## 주석·docstring

- 기본은 주석 없음. 왜(why)가 코드만으로 드러나지 않을 때만 한 줄 docstring이나 주석을 단다.
- 무엇을 하는지 설명하는 주석, 현재 작업·이슈 번호를 참조하는 주석은 쓰지 않는다.

## 에러 처리

- 시스템 경계(API 입력, LLM 응답, MCP 도구 결과, k8s API 응답)에서만 검증한다. 내부 계층 간 호출은 서로를 신뢰한다.
- 구체적 예외를 잡는다. 넓은 `except Exception`으로 여러 실패를 삼키지 않는다.
- LLM 구조화 출력이 스키마를 어기면 기본값으로 조용히 메우지 않는다 — 재시도하거나 실패로 드러낸다.
- CLI 종료 코드: 0 성공, 1 실행 실패, 2 설정·사용법 오류, 3 LLM 요청 한도. 평가 러너는 에이전트가 2·3으로 끝나면 남은 회차를 멈추고 같은 코드로 끝난다.

## 테스트

- 새 기능은 실패하는 테스트 → 최소 구현 → 통과 순서(TDD)로 진행한다.
- LLM은 결정적 응답을 내는 가짜 구현으로 바꿔 끼운다. mock 범위는 외부 호출로만 한정한다. 채팅 모델은 `BaseChatModel`을 상속한 대본 모델(`agent/tests/conftest.py`의 `ScriptedChatModel` — 정해 둔 `AIMessage`를 차례로 내고 `bind_tools`·`with_structured_output`을 흉내 낸다)로, OpenAI 호환 HTTP 계층은 httpx `MockTransport`로 바꾼다.
- 쿠버네티스가 필요한 테스트는 kind에 붙는 통합 테스트로 분리하고 `integration` 마커를 단다. 마커는 루트 `pyproject.toml`에 등록돼 있고 기본 `pytest`에서 빠진다 — `uv run pytest -m integration`으로 따로 돌린다.
- 비동기 테스트는 anyio pytest 플러그인으로 쓴다(`@pytest.mark.anyio`, 멤버마다 `tests/conftest.py`의 `anyio_backend` 픽스처). FastAPI 앱은 httpx `ASGITransport`로 부른다 — Starlette 1.x는 `TestClient`의 httpx 사용을 deprecated로 바꿨다.
- 경고는 오류로 다룬다(`filterwarnings = ["error"]`), 등록하지 않은 마커는 오류다(`--strict-markers`).
- 테스트 이름은 동작을 문장으로 쓴다(`test_version_flag_prints_name_and_version`).

## 쿠버네티스·인프라

- 이미지 태그는 고정한다(`latest` 금지).
- 모든 컨테이너에 resources requests/limits를 둔다(회사 GPU 서버에서 다른 시스템과 같이 뜬다).
- 컨테이너는 root가 아닌 사용자·그룹으로 돌리고(`runAsNonRoot`·`runAsGroup`, `allowPrivilegeEscalation: false`, `capabilities.drop: [ALL]`, `seccompProfile: RuntimeDefault`), 쓰기가 필요 없으면 `readOnlyRootFilesystem`을 켠다. 쿠버네티스 API를 쓰지 않는 파드는 `automountServiceAccountToken: false`. 데모 네임스페이스는 restricted 파드 보안 표준을 강제한다.
- 이미지는 빌드 단계와 실행 단계를 나눠 실행 이미지에 빌드 도구·소스·캐시를 남기지 않는다.
- 공개 저장소다 — 로컬 절대 경로·회사 정보(이름·주소·계정)를 코드와 문서에 쓰지 않는다(`CLAUDE.md` §2).
- ServiceAccount·RBAC는 최소 권한. 쓰기 권한은 데모 네임스페이스로 한정한다.
- 비밀값은 매니페스트에 평문으로 두지 않는다(온프레미스는 SOPS, GKE는 Secret Manager + Workload Identity Federation, 로컬 티어의 API 키는 커밋하지 않는 `.env`).
- 배포 리소스 이름은 kebab-case(`hoa-agent`).

## 네이밍

- 파일·함수: `snake_case`. 클래스: `PascalCase`.
- 1회성 실험 스크립트와 운영 스크립트를 구분해 위치시킨다(`CLAUDE.md` §2 — `scripts/` vs `research/`).

## 백로그

- 없음.
