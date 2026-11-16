import pytest

from hoa_demo import inventory

pytestmark = pytest.mark.anyio


async def test_stock_returns_available_quantity(client_for):
    async with client_for(inventory.create_app()) as client:
        response = await client.get("/stock/SKU-1")
    assert response.status_code == 200
    assert response.json() == {"sku": "SKU-1", "available": 10}


async def test_unknown_sku_is_404(client_for):
    async with client_for(inventory.create_app()) as client:
        response = await client.get("/stock/NOPE")
    assert response.status_code == 404


async def test_healthz_reports_ok(client_for):
    async with client_for(inventory.create_app()) as client:
        response = await client.get("/healthz")
    assert response.json() == {"status": "ok"}
