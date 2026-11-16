import pytest

from hoa_demo.config import ConfigError, Role, load_settings, require


def test_load_settings_reads_role_port_and_downstream_url() -> None:
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


def test_non_numeric_port_error_names_the_variable_and_value() -> None:
    with pytest.raises(ConfigError, match=r"HOA_DEMO_PORT='eighty'"):
        load_settings({"HOA_DEMO_ROLE": "inventory", "HOA_DEMO_PORT": "eighty"})


@pytest.mark.parametrize("port", ["0", "65536"])
def test_port_outside_the_valid_range_is_rejected(port: str) -> None:
    with pytest.raises(ConfigError, match=f"HOA_DEMO_PORT='{port}'"):
        load_settings({"HOA_DEMO_ROLE": "inventory", "HOA_DEMO_PORT": port})


def test_missing_role_is_a_config_error() -> None:
    with pytest.raises(ConfigError, match="HOA_DEMO_ROLE"):
        load_settings({"HOA_DEMO_PORT": "8080"})


def test_downstream_url_loses_its_trailing_slash() -> None:
    settings = load_settings(
        {
            "HOA_DEMO_ROLE": "gateway",
            "HOA_DEMO_PORT": "8080",
            "HOA_DEMO_ORDERS_URL": "http://orders/",
        }
    )
    assert settings.orders_url == "http://orders"


def test_downstream_url_without_a_scheme_is_rejected() -> None:
    with pytest.raises(ConfigError, match=r"HOA_DEMO_ORDERS_URL='orders'.*http://"):
        load_settings(
            {"HOA_DEMO_ROLE": "gateway", "HOA_DEMO_PORT": "8080", "HOA_DEMO_ORDERS_URL": "orders"}
        )


def test_require_rejects_missing_downstream_url() -> None:
    with pytest.raises(ConfigError, match="HOA_DEMO_ORDERS_URL is required for role gateway"):
        require(None, "orders_url", Role.GATEWAY)
