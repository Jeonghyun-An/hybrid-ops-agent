import httpx
import pytest
from fastapi import FastAPI

from hoa_demo import gateway, inventory, orders

pytestmark = pytest.mark.anyio


def gateway_over_real_services() -> FastAPI:
    inventory_transport = httpx.ASGITransport(app=inventory.create_app())
    orders_app = orders.create_app("http://inventory", transport=inventory_transport)
    orders_transport = httpx.ASGITransport(app=orders_app)
    return gateway.create_app("http://orders", transport=orders_transport)


async def test_gateway_returns_order_with_stock_through_three_services(client_for):
    async with client_for(gateway_over_real_services()) as client:
        response = await client.get("/api/orders/1")
    assert response.status_code == 200
    assert response.json()["stock"] == {"sku": "SKU-1", "available": 10}


async def test_missing_order_stays_404_through_gateway(client_for):
    async with client_for(gateway_over_real_services()) as client:
        response = await client.get("/api/orders/99")
    assert response.status_code == 404


async def test_orders_server_error_becomes_502(client_for):
    transport = httpx.MockTransport(lambda request: httpx.Response(500))
    async with client_for(gateway.create_app("http://orders", transport=transport)) as client:
        response = await client.get("/api/orders/1")
    assert response.status_code == 502
    assert response.json()["detail"] == "orders returned 500"
