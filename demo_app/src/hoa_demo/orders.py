import httpx
from fastapi import FastAPI, HTTPException

from hoa_demo.common import add_health, fetch
from hoa_demo.models import Order, OrderDetail, Stock

ORDERS = {
    1: Order(order_id=1, sku="SKU-1", quantity=2),
    2: Order(order_id=2, sku="SKU-2", quantity=1),
}


def create_app(inventory_url: str, transport: httpx.AsyncBaseTransport | None = None) -> FastAPI:
    app = FastAPI(title="hoa-demo orders")
    add_health(app)

    @app.get("/orders/{order_id}")
    async def get_order(order_id: int) -> OrderDetail:
        order = ORDERS.get(order_id)
        if order is None:
            raise HTTPException(status_code=404, detail=f"unknown order: {order_id}")
        stock = await fetch(
            Stock, f"{inventory_url}/stock/{order.sku}", service="inventory", transport=transport
        )
        return OrderDetail(order=order, stock=stock)

    return app
