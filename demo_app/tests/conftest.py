from collections.abc import Callable

import httpx
import pytest
from fastapi import FastAPI


def asgi_client(app: FastAPI) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test")


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture
def client_for() -> Callable[[FastAPI], httpx.AsyncClient]:
    return asgi_client
