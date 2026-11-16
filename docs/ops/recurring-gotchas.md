# 반복 함정 (Recurring Gotchas)

개발 환경·클러스터·클라우드·실데이터처럼 실제로 돌려 봐야만 드러나는 패턴을 기록한다. 겪을 때마다 아래에 `## N. 제목` 섹션을 추가한다 — 라운드 문서가 아니라 상시 갱신 문서다. 표가 아니라 산문 섹션인 이유: 항목 하나가 원인 여러 개·하위 절차·쉘 명령(`|` 포함)을 가지는 경우가 흔한데, 표 셀에는 이게 안 들어간다.

각 섹션 구성: 날짜 · 증상 · 원인 · 해결 · 재발 방지.

## 1. Windows에서 커밋할 때 "LF will be replaced by CRLF" 경고

- **날짜**: 2026-11-09 (round00)
- **증상**: Windows 개발 PC에서 `git commit` 때 `warning: in the working copy of '<파일>', LF will be replaced by CRLF the next time Git touches it`가 뜬다.
- **원인**: 전역 설정 `core.autocrlf=true`가 작업 사본을 CRLF로 바꾸려 한다. 같은 파일을 Linux(GPU 서버·CI·컨테이너)에서 쓰면 줄바꿈이 섞이고, 셸 스크립트는 줄 끝의 `\r` 때문에 `bad interpreter`로 죽는다.
- **해결**: 저장소 `.gitattributes`에 `* text=auto eol=lf`를 둔다. `eol` 속성은 개인 설정 `core.autocrlf`보다 우선하므로 작업 사본도 LF로 고정된다(PowerShell 스크립트만 CRLF). 이미 들어간 파일은 `git add --renormalize .`로 다시 정규화한다.
- **재발 방지**: 확인은 `git ls-files --eol`에서 텍스트 파일이 모두 `i/lf w/lf`인지 본다(`.ps1`은 `w/crlf`, 이미지는 `-text`). Windows 전용 파일 종류가 새로 생기면 `.gitattributes`에 규칙을 더한다.

## 2. devcontainer 이미지 빌드가 Yarn 저장소 서명 오류로 실패

- **날짜**: 2026-11-09 (round00)
- **증상**: `devcontainer up`이 기능(feature) 설치 중 `E: The repository 'https://dl.yarnpkg.com/debian stable InRelease' is not signed.`(`NO_PUBKEY 62D54FD4003F6525`)를 내고 `Feature "Docker (docker-outside-of-docker)" ... failed to install!`로 멈춘다.
- **원인**: 이미지 태그 `mcr.microsoft.com/devcontainers/python:1-3.12-bookworm`은 이미지 1번대에서 갱신이 멈춘 태그라, 서명 키가 만료된 Yarn apt 저장소(`/etc/apt/sources.list.d/yarn.list`)가 남아 있다. 기능 설치 스크립트의 `apt-get update`가 이 저장소에서 실패한다.
- **해결**: 현재 메이저 태그 `3-3.12-bookworm`을 쓴다(Yarn 저장소가 없다).
- **재발 방지**: devcontainer 이미지는 현재 메이저 태그를 쓴다. 태그를 바꿀 때는 `docker run --rm --entrypoint sh <이미지> -c 'ls /etc/apt/sources.list.d/'`로 남아 있는 서드파티 저장소를 먼저 보고, `npx -y @devcontainers/cli up --workspace-folder .`로 실제 기동까지 확인한다.

## 3. Windows 호스트와 공유한 작업 폴더에서 컨테이너 git이 멈추고 훅이 안 돎

- **날짜**: 2026-11-09 (round00)
- **증상**: devcontainer 안에서 `git status`가 `fatal: detected dubious ownership in repository at '/workspaces/hybrid-ops-agent'`로 멈춘다. `safe.directory`로 넘겨도 `git commit`이 `cannot exec '.git/hooks/pre-commit': No such file or directory`로 실패한다(훅을 직접 실행하면 `not found`, 종료 코드 127).
- **원인**: (1) Windows 호스트의 작업 폴더는 bind mount 안에서 컨테이너 사용자(`vscode`)와 소유자가 달라, git의 소유자 검사가 저장소를 거부한다. (2) `.git/hooks`는 추적되지 않는 파일이라 `.gitattributes`가 적용되지 않는데, 호스트(Windows)의 pre-commit이 훅 스크립트를 CRLF로 쓴다. 첫 줄 `#!/bin/sh\r`의 `\r` 때문에 Linux가 인터프리터를 찾지 못한다(Git Bash는 이를 견딘다).
- **해결**: `postCreateCommand` 맨 앞에서 `sudo git config --system --replace-all safe.directory ${containerWorkspaceFolder}`로 작업 폴더를 등록한다(시스템 설정이라 VS Code가 복사해 넣는 `~/.gitconfig`에 덮이지 않는다). 커밋은 호스트에서 한다 — 컨테이너에서 `pre-commit install`로 훅을 다시 쓰면 이번엔 호스트 커밋이 깨진다(훅이 컨테이너 Python 경로를 가리킨다).
- **재발 방지**: 컨테이너는 도구(uv·kubectl·helm·terraform)와 테스트·`pre-commit run`용으로 쓰고, `git commit`은 호스트에서 한다(`GIT_WORKFLOW.md` §개발 환경). 컨테이너의 venv는 `UV_PROJECT_ENVIRONMENT`로 작업 폴더 밖에 둬서 호스트 `.venv`를 건드리지 않는다.

## 4. Starlette `TestClient`가 httpx 사용 경고를 낸다

- **날짜**: 2026-11-11 (round01a)
- **증상**: `uv run pytest -W error`에서 `from fastapi.testclient import TestClient`가 수집 단계에서 `StarletteDeprecationWarning: Using httpx with starlette.testclient is deprecated; install httpx2 instead.`로 실패한다. 경고를 오류로 바꾸지 않으면 테스트는 통과하고 경고만 남는다.
- **원인**: Starlette 1.x가 `TestClient`의 httpx 백엔드를 deprecated로 바꿨다. FastAPI 0.162의 `fastapi.testclient`는 Starlette 것을 그대로 내보낸다.
- **해결**: 앱을 `httpx.AsyncClient(transport=httpx.ASGITransport(app=app))`로 부르는 비동기 테스트(`@pytest.mark.anyio`)로 쓴다. 하류 서비스도 `ASGITransport`로 실제 앱을 잇는다.
- **재발 방지**: 코딩 표준 「테스트」 절. 경고가 새로 생기면 `uv run pytest -W error`로 원인부터 본다.

## 5. `mcp`를 상한 없이 설치하면 FastMCP import가 깨진다

- **날짜**: 2026-11-11 (round01a)
- **증상**: 상한 없는 `mcp` 의존성이 2.x를 받아 `from mcp.server.fastmcp import FastMCP`가 `ModuleNotFoundError: No module named 'mcp.server.fastmcp'. This is mcp 2.x, where FastMCP was renamed to MCPServer ...`로 실패한다. 반대로 서버를 2.x API로 쓰면 `langchain-mcp-adapters`(0.3.2, `mcp<2`)를 더할 때 잠금이 1.x로 내려가 서버가 깨진다.
- **원인**: MCP Python SDK 2.0에서 FastMCP가 `mcp.server.mcpserver.MCPServer`로 바뀌었다. uv 워크스페이스는 잠금 파일 하나라 멤버마다 다른 메이저를 쓸 수 없다.
- **해결**: `mcp_servers/pyproject.toml`에서 `mcp>=1.30,<2`로 고정한다.
- **재발 방지**: `langchain-mcp-adapters`가 2.x를 지원하면 서버(FastMCP → MCPServer)와 에이전트를 같은 라운드에 함께 올린다.

## 6. `kubernetes_asyncio`의 파드 로그가 JSON 한 덩어리면 원문이 바뀐다

- **날짜**: 2026-11-16 (round01a, 정적 리뷰에서 발견)
- **증상**: `read_namespaced_pod_log` 결과가 로그 원문과 다르다. 본문 전체가 JSON 값 하나이면 `{"level":"error"}`가 `{'level': 'error'}`로, `true`가 `True`로 바뀌고, 본문이 `null`이면 `None`이 돌아온다. UTF-8이 아닌 바이트가 섞이면 디코딩 오류로 실패한다.
- **원인**: 생성된 클라이언트가 응답 타입 `str`을 역직렬화할 때 본문을 먼저 `json.loads`하고 그 결과를 `str()`로 바꾼다. 디코딩도 엄격한 UTF-8이다.
- **해결**: `_preload_content=False`로 받아 `ApiClient`를 닫기 전에 `await response.read()`로 원문 바이트를 읽고 `decode("utf-8", errors="replace")`한다. `limit_bytes`로 거대한 줄도 막는다(`mcp_servers/src/hoa_mcp/k8s_read/kube.py`).
- **재발 방지**: 생성된 클라이언트로 텍스트 본문(로그 등)을 받을 때는 원문 바이트로 받는다.

## 7. Gemini 3에 도구 결과를 보내면 `thought_signature`가 없다며 400

- **날짜**: 2026-11-16 (round01b)
- **증상**: `ChatOpenAI`(langchain-openai 1.8)로 Gemini OpenAI 호환 주소를 부르면 첫 호출의 도구 호출은 오는데, 도구 결과를 붙인 두 번째 호출이 `400 Function call is missing a thought_signature in functionCall parts`로 거절된다.
- **원인**: Gemini 3는 도구 호출마다 `tool_calls[].extra_content.google.thought_signature`를 붙이고, 다음 요청의 assistant 메시지에 그 값이 그대로 있어야 한다. `ChatOpenAI`는 응답을 `AIMessage`로 바꿀 때 이 확장 필드를 버리고, 요청을 만들 때도 넣지 않는다.
- **해결**: `agent/src/hoa_agent/llm.py`의 `ChatOpenAICompat`이 응답의 `extra_content`를 `AIMessage.additional_kwargs`에 도구 호출 id별로 보관했다가 요청 payload의 같은 id 도구 호출에 다시 붙인다. vLLM(Gemma)은 이 필드를 보내지 않으므로 영향이 없다.
- **재발 방지**: `agent/tests/test_llm.py`의 httpx `MockTransport` 테스트가 서명이 두 번째 요청에 실리는지 확인한다. langchain-openai를 올리면 이 테스트가 먼저 깨진다(재정의한 `_create_chat_result`·`_get_request_payload`는 비공개 메서드다).

## 8. Windows에서 표준출력을 파일·파이프로 돌리면 `UnicodeEncodeError`

- **날짜**: 2026-11-16 (round01b)
- **증상**: 콘솔에서는 되던 `hoa investigate`가 `> out.json`이나 하위 프로세스 파이프로 돌리면 `UnicodeEncodeError: 'cp949' codec can't encode character '—'`로 죽는다. 반대로 UTF-8로 읽는 쪽(`subprocess.run(..., encoding="utf-8")`)은 한국어가 든 cp949 출력을 읽다 읽기 스레드가 죽는다.
- **원인**: Windows의 Python은 콘솔이 아닌 표준 스트림에 로캘 인코딩(한국어 Windows는 cp949)을 쓴다.
- **해결**: JSON·표를 내는 CLI(`hoa`·`hoa-eval`)는 시작할 때 `sys.stdout.reconfigure(encoding="utf-8")`(표준오류도)로 고정하고, 하위 프로세스를 읽는 쪽은 `encoding="utf-8", errors="replace"`를 준다.
- **재발 방지**: 하위 프로세스로 텍스트를 주고받는 새 CLI도 같은 두 가지를 지킨다(코딩 표준 「타입·데이터」).

## 9. MCP 세션 안에서 난 예외가 `ExceptionGroup`으로 묶여 `except`를 빠져나간다

- **날짜**: 2026-11-16 (round01b)
- **증상**: 그래프 안에서 난 `openai.BadRequestError`를 CLI의 `except openai.APIError`가 잡지 못하고 `ExceptionGroup` traceback이 그대로 나온다.
- **원인**: MCP stdio 클라이언트(`mcp.client.stdio`)가 anyio 작업 그룹을 쓰고, anyio 4는 작업 그룹을 빠져나가는 예외를 늘 `ExceptionGroup`으로 감싼다. 세션을 연 `async with` 안의 모든 예외가 감싸진다.
- **해결**: `run_investigation`이 세션 밖에서 `BaseExceptionGroup`을 받아, 안에 예외가 하나뿐이면 풀어서 다시 올린다(`agent/src/hoa_agent/investigate.py`의 `sole_exception`).
- **재발 방지**: MCP 세션을 여는 다른 진입점(round02 클러스터 안 에이전트 등)도 같은 함수를 거친다.

## 10. Gemini 무료 등급은 모델마다 하루 요청 수 한도가 있다

- **날짜**: 2026-11-16 (round01b)
- **증상**: 몇 번 잘 되던 호출이 `429 RESOURCE_EXHAUSTED — Quota exceeded for metric generate_content_free_tier_requests, limit: 20 ... Please retry in 2h30m`으로 막힌다. `gemini-3.5-flash`는 내부적으로 다른 버전(`gemini-3.6-flash`)의 한도로 센다.
- **원인**: 무료 등급 한도는 모델마다 분당·하루 요청 수로 따로 있고, 하루 한도는 태평양 시간 자정에 초기화된다. 모델별 값은 문서에 없고 AI Studio(로그인)의 rate-limit 화면에만 있다. 조사 1건이 모델을 네댓 번 부르므로 하루 20회 모델은 조사 네 번이면 끝난다. 클라이언트 재시도(`max_retries`)로는 풀리지 않는다.
- **해결**: 기본 LLM을 요청 한도가 없는 회사 GPU의 Gemma로 두고(평가에서 Gemini는 시나리오마다 1회 비교 기준만), Gemini 프로필의 기본 모델은 같은 조사를 빠르게 맞힌 `gemini-3.5-flash-lite`로 둔다. `hoa investigate`는 한도 오류에 종료 코드 3을 내고, `hoa-eval run`은 3을 보면 남은 회차를 멈춘다 — 한도가 풀린 뒤 남은 시나리오만 `--scenario`로 다시 돌려 `report`로 합친다.
- **재발 방지**: 프로브·실험도 한도에 들어간다 — 평가를 돌릴 날에는 같은 모델로 따로 시험하지 않는다.

## 11. `rollout status`가 끝나도 종료 중인 옛 파드가 남는다

- **날짜**: 2026-11-16 (round01b)
- **증상**: 평가 러너가 데모 앱을 복구(`apply` → `rollout restart` → `rollout status`)한 직후 다음 테스트의 gateway 프록시 요청이 `InternalError ("unknown")`로 실패한다. 다음 회차 조사에서 `list_pods`가 `terminating` 파드를 보여 진단이 흐려질 수 있다.
- **원인**: `rollout status`는 새 ReplicaSet의 파드가 준비되면 끝난다. 옛 파드는 그 뒤에 종료되고, 그동안 Service 엔드포인트와 파드 목록에 남는다.
- **해결**: `DemoCluster.reset`이 `rollout status` 뒤에 `deletionTimestamp`가 붙은 파드가 데모 네임스페이스에서 사라질 때까지 기다린다(`eval/src/hoa_eval/cluster.py`의 `wait_settled`, 120초).
- **재발 방지**: 장애 주입 전 「깨끗한 상태」는 「종료 중인 파드 없음」까지로 본다.
