import logging
import os
import subprocess
import sys

import pytest

from hoa_demo.cli import SkipHealthChecks, build_app
from hoa_demo.config import ConfigError, DemoSettings, Role


def test_orders_role_requires_inventory_url() -> None:
    with pytest.raises(ConfigError, match="HOA_DEMO_INVENTORY_URL is required for role orders"):
        build_app(DemoSettings(role=Role.ORDERS, port=8080))


def test_gateway_role_requires_orders_url() -> None:
    with pytest.raises(ConfigError, match="HOA_DEMO_ORDERS_URL is required for role gateway"):
        build_app(DemoSettings(role=Role.GATEWAY, port=8080))


def test_inventory_role_builds_an_app_with_stock_route() -> None:
    app = build_app(DemoSettings(role=Role.INVENTORY, port=8080))
    assert "/stock/{sku}" in {route.path for route in app.routes}


def test_gateway_role_builds_an_app_with_order_route() -> None:
    app = build_app(DemoSettings(role=Role.GATEWAY, port=8080, orders_url="http://orders"))
    assert "/api/orders/{order_id}" in {route.path for route in app.routes}


def test_health_check_hits_are_kept_out_of_the_access_log() -> None:
    def access(path: str) -> logging.LogRecord:
        return logging.LogRecord(
            "uvicorn.access", logging.INFO, __file__, 0, '"GET %s HTTP/1.1" 200', (path,), None
        )

    assert SkipHealthChecks().filter(access("/healthz")) is False
    assert SkipHealthChecks().filter(access("/api/orders/1")) is True


def test_bad_port_exits_1_with_exactly_one_error_line() -> None:
    env = {**os.environ, "HOA_DEMO_ROLE": "inventory", "HOA_DEMO_PORT": "eighty"}
    result = subprocess.run(
        [sys.executable, "-m", "hoa_demo"],
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert result.returncode == 1
    lines = result.stderr.strip().splitlines()
    assert len(lines) == 1
    assert lines[0].startswith("hoa-demo: invalid configuration: HOA_DEMO_PORT='eighty'")
