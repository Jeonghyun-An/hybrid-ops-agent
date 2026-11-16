from typing import Literal

from pydantic import BaseModel

MAX_OUTPUT_CHARS = 12_000
MAX_LINE_CHARS = 500
MAX_MESSAGE_CHARS = 300
MAX_ENV_VARS = 40
ELLIPSIS = "…"


class OutputTooLarge(Exception):
    pass


def clip(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    return text[: limit - 1] + ELLIPSIS


def serialized_chars(model: BaseModel) -> int:
    """Counts characters of the indent=2 JSON that FastMCP sends as the tool result text."""
    return len(model.model_dump_json(indent=2))


def fit[M: BaseModel](
    model: M,
    field: str,
    *,
    drop: Literal["head", "tail"],
    limit: int = MAX_OUTPUT_CHARS,
) -> M:
    items = list(getattr(model, field))
    fitted = model
    while serialized_chars(fitted) > limit:
        if not items:
            raise OutputTooLarge(f"output stays above {limit} characters even without {field}")
        items = items[1:] if drop == "head" else items[:-1]
        fitted = model.model_copy(update={field: items, "truncated": True})
    return fitted
