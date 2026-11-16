from collections.abc import Callable

import httpx
import pytest
from fastapi import FastAPI

from hoa_demo import inventory, orders

pytestmark = pytest.mark.anyio

ClientFor = Callable[[FastAPI], httpx.AsyncClient]


def orders_over_real_inventory() -> FastAPI:
    transport = httpx.ASGITransport(app=inventory.create_app())
    return orders.create_app("http://inventory", transport=transport)


async def test_order_includes_stock_from_inventory(client_for: ClientFor) -> None:
    async with client_for(orders_over_real_inventory()) as client:
        response = await client.get("/orders/1")
    assert response.status_code == 200
    assert response.json() == {
        "order": {"order_id": 1, "sku": "SKU-1", "quantity": 2},
        "stock": {"sku": "SKU-1", "available": 10},
    }


async def test_unknown_order_is_404(client_for: ClientFor) -> None:
    async with client_for(orders_over_real_inventory()) as client:
        response = await client.get("/orders/99")
    assert response.status_code == 404


async def test_unreachable_inventory_is_502_naming_the_service(client_for: ClientFor) -> None:
    def refuse(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused", request=request)

    app = orders.create_app("http://inventory", transport=httpx.MockTransport(refuse))
    async with client_for(app) as client:
        response = await client.get("/orders/1")
    assert response.status_code == 502
    assert response.json()["detail"] == "inventory unreachable: ConnectError"


async def test_inventory_server_error_keeps_its_detail(client_for: ClientFor) -> None:
    transport = httpx.MockTransport(
        lambda request: httpx.Response(503, json={"detail": "warming up"})
    )
    app = orders.create_app("http://inventory", transport=transport)
    async with client_for(app) as client:
        response = await client.get("/orders/1")
    assert response.status_code == 502
    assert response.json()["detail"] == "inventory returned 503: warming up"
