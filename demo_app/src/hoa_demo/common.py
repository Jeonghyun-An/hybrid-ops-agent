import httpx
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from hoa_demo.models import Health

REQUEST_TIMEOUT_SECONDS = 2.0


def add_health(app: FastAPI) -> None:
    @app.get("/healthz")
    async def healthz() -> Health:
        return Health()


async def fetch[M: BaseModel](
    model: type[M],
    url: str,
    *,
    service: str,
    transport: httpx.AsyncBaseTransport | None = None,
) -> M:
    try:
        async with httpx.AsyncClient(
            transport=transport, timeout=REQUEST_TIMEOUT_SECONDS
        ) as client:
            response = await client.get(url)
    except httpx.HTTPError as exc:
        raise HTTPException(
            status_code=502, detail=f"{service} unreachable: {type(exc).__name__}"
        ) from exc
    if response.status_code == 404:
        raise HTTPException(status_code=404, detail=f"{service}: not found")
    if response.status_code != 200:
        raise HTTPException(status_code=502, detail=f"{service} returned {response.status_code}")
    return model.model_validate_json(response.content)
