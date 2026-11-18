# 워크스페이스 멤버 하나를 담는 이미지 — 데모 앱·MCP 서버·에이전트가 같은 파일을 쓴다.
# 빌드 컨텍스트는 저장소 루트다(uv 워크스페이스의 잠금 파일과 멤버 pyproject가 루트 기준).
#   docker build -f deploy/docker/Dockerfile --build-arg PACKAGE=hoa-mcp --build-arg MEMBER=mcp_servers -t hoa-mcp:0.1.0 .
# uv sync --locked 는 워크스페이스 모든 멤버의 pyproject를 요구한다 — 멤버가 늘면 아래 COPY 줄과
# Dockerfile.dockerignore 를 같이 늘린다. 실행 명령은 차트가 정한다(이미지에는 CMD가 없다).
FROM ghcr.io/astral-sh/uv:0.11.31 AS uv

FROM python:3.12.16-slim-bookworm AS build
ARG PACKAGE
ARG MEMBER
COPY --from=uv /uv /usr/local/bin/uv
ENV UV_COMPILE_BYTECODE=1 \
    UV_NO_CACHE=1 \
    UV_PYTHON_DOWNLOADS=never
WORKDIR /app
COPY pyproject.toml uv.lock ./
COPY agent/pyproject.toml agent/
COPY demo_app/pyproject.toml demo_app/
COPY eval/pyproject.toml eval/
COPY mcp_servers/pyproject.toml mcp_servers/
# 의존성 레이어를 소스보다 먼저 만든다 — 소스만 바뀌면 이 레이어는 캐시에서 온다
RUN test -n "${PACKAGE}" && test -n "${MEMBER}" \
    && uv sync --locked --package "${PACKAGE}" --no-dev --no-install-workspace
COPY ${MEMBER}/src ${MEMBER}/src
RUN uv sync --locked --package "${PACKAGE}" --no-dev --no-editable

# 실행 이미지에는 가상환경만 옮긴다 — uv·소스·빌드 잔여물을 남기지 않는다.
FROM python:3.12.16-slim-bookworm
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH=/app/.venv/bin:$PATH
COPY --from=build /app/.venv /app/.venv
USER 65532:65532
