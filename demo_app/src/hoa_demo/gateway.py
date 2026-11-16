import httpx
from fastapi import FastAPI

from hoa_demo.common import add_health, fetch
from hoa_demo.models import OrderDetail


def create_app(orders_url: str, transport: httpx.AsyncBaseTransport | None = None) -> FastAPI:
    app = FastAPI(title="hoa-demo gateway")
    add_health(app)

    @app.get("/api/orders/{order_id}")
    async def get_order(order_id: int) -> OrderDetail:
        return await fetch(
            OrderDetail, f"{orders_url}/orders/{order_id}", service="orders", transport=transport
        )

    return app
