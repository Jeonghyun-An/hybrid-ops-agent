from collections.abc import Mapping
from enum import StrEnum

from pydantic import BaseModel, Field, ValidationError, field_validator


class Role(StrEnum):
    GATEWAY = "gateway"
    ORDERS = "orders"
    INVENTORY = "inventory"


class DemoSettings(BaseModel):
    role: Role
    port: int = Field(ge=1, le=65535)
    orders_url: str | None = None
    inventory_url: str | None = None

    @field_validator("orders_url", "inventory_url")
    @classmethod
    def http_url_without_trailing_slash(cls, value: str | None) -> str | None:
        if value is None:
            return None
        if not value.startswith(("http://", "https://")):
            raise ValueError("must start with http:// or https://")
        return value.rstrip("/")


class ConfigError(Exception):
    pass


ENV_NAMES = {
    "role": "HOA_DEMO_ROLE",
    "port": "HOA_DEMO_PORT",
    "orders_url": "HOA_DEMO_ORDERS_URL",
    "inventory_url": "HOA_DEMO_INVENTORY_URL",
}


def load_settings(env: Mapping[str, str]) -> DemoSettings:
    raw = {field: env[name] for field, name in ENV_NAMES.items() if name in env}
    try:
        return DemoSettings.model_validate(raw)
    except ValidationError as exc:
        error = exc.errors()[0]
        field = str(error["loc"][0])
        raise ConfigError(f"{ENV_NAMES[field]}={raw.get(field)!r}: {error['msg']}") from exc


def require(value: str | None, field: str, role: Role) -> str:
    if not value:
        raise ConfigError(f"{ENV_NAMES[field]} is required for role {role}")
    return value
