import asyncio
import logging
import time
from collections.abc import Awaitable, Callable
from typing import Literal

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field

from hoa_agent.failures import HTTP_STATUSES, KNOWN_FAILURES, classify, public_message
from hoa_agent.result import InvestigationResult

Investigate = Callable[[str], Awaitable[InvestigationResult]]
MAX_ALERT_CHARS = 2_000
RETRY_AFTER_SECONDS = 30

logger = logging.getLogger(__name__)


class Health(BaseModel):
    status: Literal["ok"] = "ok"


class InvestigationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    alert: str = Field(min_length=1, max_length=MAX_ALERT_CHARS)


class ApiError(BaseModel):
    kind: str
    message: str


class ErrorBody(BaseModel):
    error: ApiError


def error_response(
    status: int, kind: str, message: str, *, retry_after: int | None = None
) -> JSONResponse:
    headers = None if retry_after is None else {"Retry-After": str(retry_after)}
    body = ErrorBody(error=ApiError(kind=kind, message=message))
    return JSONResponse(status_code=status, content=body.model_dump(), headers=headers)


def crashed(exc: Exception) -> JSONResponse:
    """분류 밖 예외 — 원문은 로그에만, 응답에는 종류만 남긴다."""
    logger.exception("investigation crashed", exc_info=exc)
    return error_response(500, "internal_error", type(exc).__name__)


def create_app(investigate: Investigate, *, timeout_seconds: float) -> FastAPI:
    """조사 함수를 주입받는다 — 테스트는 가짜를, hoa serve는 run_investigation을 끼운다."""
    app = FastAPI(title="hoa agent", docs_url=None, redoc_url=None, openapi_url=None)
    # 조사 예산(도구 6번·문맥 26K)이 1건 기준이고 GPU를 다른 시스템과 같이 쓴다 —
    # 줄 세우지 않고 바로 429로 돌려보낸다
    busy = asyncio.Lock()

    @app.get("/healthz", response_model=Health)
    async def healthz() -> Health:
        """프로세스만 본다 — LLM·MCP가 죽어도 재시작하지 않고 조사 요청에 503으로 알린다."""
        return Health()

    @app.post("/investigations", response_model=InvestigationResult)
    async def investigations(request: InvestigationRequest) -> InvestigationResult | JSONResponse:
        if busy.locked():
            return error_response(
                429,
                "busy",
                "an investigation is already running",
                retry_after=RETRY_AFTER_SECONDS,
            )
        async with busy:
            started = time.monotonic()
            try:
                async with asyncio.timeout(timeout_seconds) as deadline:
                    result = await investigate(request.alert)
            except TimeoutError as exc:
                if not deadline.expired():
                    # 우리 제한 시간이 아닌 TimeoutError — 분류 밖 예외와 같게 다룬다
                    return crashed(exc)
                logger.warning("investigation timed out after %gs", timeout_seconds)
                return error_response(
                    504,
                    "timeout",
                    f"the investigation did not finish within {timeout_seconds:g}s",
                )
            except KNOWN_FAILURES as exc:
                kind = classify(exc)
                # 원문(내부 주소가 섞일 수 있다)은 운영자 로그에만 남긴다
                logger.warning("investigation failed: %s", kind.value, exc_info=exc)
                return error_response(HTTP_STATUSES[kind], kind.value, public_message(kind, exc))
            except Exception as exc:
                # 시스템 경계 — 분류 밖 예외도 500으로 응답한다(MCP 서버의 reported와 같은 이유)
                return crashed(exc)
        logger.info(
            "investigation done: cause=%s stop=%s seconds=%.1f alert=%r",
            result.diagnosis.cause_label.value,
            result.stop_reason,
            time.monotonic() - started,
            request.alert[:80],
        )
        return result

    return app
