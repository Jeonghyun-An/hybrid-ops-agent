from typing import Literal

import pydantic_core
from pydantic import BaseModel

MAX_OUTPUT_CHARS = 12_000
MAX_LINE_CHARS = 500
MAX_MESSAGE_CHARS = 300
ELLIPSIS = "…"


def clip(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    return text[: limit - 1] + ELLIPSIS


def serialized_chars(model: BaseModel) -> int:
    """Counts characters the way FastMCP serializes a tool result (indent=2 JSON)."""
    return len(pydantic_core.to_json(model, indent=2).decode())


def fit[M: BaseModel](
    model: M,
    field: str,
    *,
    drop: Literal["head", "tail"],
    limit: int = MAX_OUTPUT_CHARS,
) -> M:
    items = list(getattr(model, field))
    fitted = model
    while items and serialized_chars(fitted) > limit:
        items = items[1:] if drop == "head" else items[:-1]
        fitted = model.model_copy(update={field: items, "truncated": True})
    return fitted
