import httpx
from fastapi import FastAPI

from hoa_demo.common import add_health, fetch
from hoa_demo.models import OrderDetail

# orders가 inventory를 기다리는 시간보다 길게 둔다 —
# inventory가 멈췄을 때 원인이 orders로 잘못 보이지 않게
ORDERS_TIMEOUT_SECONDS = 5.0


def create_app(orders_url: str, transport: httpx.AsyncBaseTransport | None = None) -> FastAPI:
    app = FastAPI(title="hoa-demo gateway")
    add_health(app)

    @app.get("/api/orders/{order_id}")
    async def get_order(order_id: int) -> OrderDetail:
        return await fetch(
            OrderDetail,
            f"{orders_url}/orders/{order_id}",
            service="orders",
            timeout=ORDERS_TIMEOUT_SECONDS,
            transport=transport,
        )

    return app
