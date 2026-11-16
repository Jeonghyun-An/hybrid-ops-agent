from collections.abc import Callable

import httpx
import pytest
from fastapi import FastAPI

from hoa_demo import gateway, inventory, orders

pytestmark = pytest.mark.anyio

ClientFor = Callable[[FastAPI], httpx.AsyncClient]


def refuse(request: httpx.Request) -> httpx.Response:
    raise httpx.ConnectError("connection refused", request=request)


def gateway_over(orders_app: FastAPI) -> FastAPI:
    return gateway.create_app("http://orders", transport=httpx.ASGITransport(app=orders_app))


def gateway_over_real_services() -> FastAPI:
    inventory_transport = httpx.ASGITransport(app=inventory.create_app())
    return gateway_over(orders.create_app("http://inventory", transport=inventory_transport))


async def test_gateway_returns_order_with_stock_through_three_services(
    client_for: ClientFor,
) -> None:
    async with client_for(gateway_over_real_services()) as client:
        response = await client.get("/api/orders/1")
    assert response.status_code == 200
    assert response.json()["stock"] == {"sku": "SKU-1", "available": 10}


async def test_missing_order_stays_404_with_the_orders_detail(client_for: ClientFor) -> None:
    async with client_for(gateway_over_real_services()) as client:
        response = await client.get("/api/orders/99")
    assert response.status_code == 404
    assert response.json()["detail"] == "orders: unknown order: 99"


async def test_orders_server_error_becomes_502(client_for: ClientFor) -> None:
    transport = httpx.MockTransport(lambda request: httpx.Response(500))
    async with client_for(gateway.create_app("http://orders", transport=transport)) as client:
        response = await client.get("/api/orders/1")
    assert response.status_code == 502
    assert response.json()["detail"] == "orders returned 500"


async def test_unreachable_orders_is_502_naming_the_service(client_for: ClientFor) -> None:
    app = gateway.create_app("http://orders", transport=httpx.MockTransport(refuse))
    async with client_for(app) as client:
        response = await client.get("/api/orders/1")
    assert response.status_code == 502
    assert response.json()["detail"] == "orders unreachable: ConnectError"


async def test_invalid_body_from_orders_is_502(client_for: ClientFor) -> None:
    transport = httpx.MockTransport(lambda request: httpx.Response(200, text="oops"))
    async with client_for(gateway.create_app("http://orders", transport=transport)) as client:
        response = await client.get("/api/orders/1")
    assert response.status_code == 502
    assert response.json()["detail"] == "orders returned an invalid body"


async def test_root_cause_from_inventory_reaches_the_gateway_response(
    client_for: ClientFor,
) -> None:
    orders_app = orders.create_app("http://inventory", transport=httpx.MockTransport(refuse))
    async with client_for(gateway_over(orders_app)) as client:
        response = await client.get("/api/orders/1")
    assert response.status_code == 502
    assert response.json()["detail"] == "orders returned 502: inventory unreachable: ConnectError"


def test_gateway_waits_longer_than_orders_waits_for_inventory() -> None:
    assert gateway.ORDERS_TIMEOUT_SECONDS > orders.INVENTORY_TIMEOUT_SECONDS
