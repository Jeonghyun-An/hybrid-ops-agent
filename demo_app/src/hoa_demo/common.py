import httpx
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, ValidationError

from hoa_demo.models import ErrorBody, Health


def add_health(app: FastAPI) -> None:
    @app.get("/healthz")
    async def healthz() -> Health:
        return Health()


def downstream_detail(response: httpx.Response) -> str:
    try:
        return ErrorBody.model_validate_json(response.content).detail
    except ValidationError:
        return ""


async def fetch[M: BaseModel](
    model: type[M],
    url: str,
    *,
    service: str,
    timeout: float,
    transport: httpx.AsyncBaseTransport | None = None,
) -> M:
    try:
        async with httpx.AsyncClient(transport=transport, timeout=timeout) as client:
            response = await client.get(url)
    except httpx.HTTPError as exc:
        raise HTTPException(
            status_code=502, detail=f"{service} unreachable: {type(exc).__name__}"
        ) from exc
    detail = downstream_detail(response)
    if response.status_code == 404:
        raise HTTPException(status_code=404, detail=f"{service}: {detail or 'not found'}")
    if response.status_code != 200:
        suffix = f": {detail}" if detail else ""
        raise HTTPException(
            status_code=502, detail=f"{service} returned {response.status_code}{suffix}"
        )
    try:
        return model.model_validate_json(response.content)
    except ValidationError as exc:
        raise HTTPException(status_code=502, detail=f"{service} returned an invalid body") from exc
