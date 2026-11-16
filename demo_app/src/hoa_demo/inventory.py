from fastapi import FastAPI, HTTPException

from hoa_demo.common import add_health
from hoa_demo.models import Stock

STOCK = {"SKU-1": 10, "SKU-2": 0}


def create_app() -> FastAPI:
    app = FastAPI(title="hoa-demo inventory")
    add_health(app)

    @app.get("/stock/{sku}")
    async def get_stock(sku: str) -> Stock:
        if sku not in STOCK:
            raise HTTPException(status_code=404, detail=f"unknown sku: {sku}")
        return Stock(sku=sku, available=STOCK[sku])

    return app
