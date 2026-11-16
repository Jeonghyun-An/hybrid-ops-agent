import pytest

from hoa_demo.config import ConfigError, Role, load_settings, require


def test_load_settings_reads_role_port_and_downstream_url():
    settings = load_settings(
        {
            "HOA_DEMO_ROLE": "orders",
            "HOA_DEMO_PORT": "8080",
            "HOA_DEMO_INVENTORY_URL": "http://inventory",
        }
    )
    assert settings.role is Role.ORDERS
    assert settings.port == 8080
    assert settings.inventory_url == "http://inventory"


def test_non_numeric_port_error_names_the_variable_and_value():
    with pytest.raises(ConfigError, match=r"HOA_DEMO_PORT='eighty'"):
        load_settings({"HOA_DEMO_ROLE": "inventory", "HOA_DEMO_PORT": "eighty"})


def test_missing_role_is_a_config_error():
    with pytest.raises(ConfigError, match="HOA_DEMO_ROLE"):
        load_settings({"HOA_DEMO_PORT": "8080"})


def test_require_rejects_missing_downstream_url():
    with pytest.raises(ConfigError, match="HOA_DEMO_ORDERS_URL is required for role gateway"):
        require(None, "orders_url", Role.GATEWAY)
