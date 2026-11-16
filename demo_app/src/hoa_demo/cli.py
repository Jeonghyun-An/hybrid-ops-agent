import os
import sys

import uvicorn
from fastapi import FastAPI

from hoa_demo import gateway, inventory, orders
from hoa_demo.config import ConfigError, DemoSettings, Role, load_settings, require


def build_app(settings: DemoSettings) -> FastAPI:
    if settings.role is Role.INVENTORY:
        return inventory.create_app()
    if settings.role is Role.ORDERS:
        return orders.create_app(require(settings.inventory_url, "inventory_url", settings.role))
    return gateway.create_app(require(settings.orders_url, "orders_url", settings.role))


def main() -> None:
    try:
        settings = load_settings(os.environ)
        app = build_app(settings)
    except ConfigError as exc:
        print(f"hoa-demo: invalid configuration: {exc}", file=sys.stderr, flush=True)
        raise SystemExit(1) from exc
    uvicorn.run(app, host="0.0.0.0", port=settings.port, log_level="info")
