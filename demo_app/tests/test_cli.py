import os
import subprocess
import sys

import pytest

from hoa_demo.cli import build_app
from hoa_demo.config import ConfigError, DemoSettings, Role


def test_orders_role_requires_inventory_url():
    with pytest.raises(ConfigError, match="HOA_DEMO_INVENTORY_URL is required for role orders"):
        build_app(DemoSettings(role=Role.ORDERS, port=8080))


def test_inventory_role_builds_an_app_with_stock_route():
    app = build_app(DemoSettings(role=Role.INVENTORY, port=8080))
    assert "/stock/{sku}" in {route.path for route in app.routes}


def test_bad_port_exits_1_with_one_line_error():
    env = {**os.environ, "HOA_DEMO_ROLE": "inventory", "HOA_DEMO_PORT": "eighty"}
    result = subprocess.run(
        [sys.executable, "-m", "hoa_demo"],
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert result.returncode == 1
    assert "hoa-demo: invalid configuration: HOA_DEMO_PORT='eighty'" in result.stderr
