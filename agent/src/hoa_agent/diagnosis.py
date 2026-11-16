from enum import StrEnum

from pydantic import BaseModel, Field


class CauseLabel(StrEnum):
    IMAGE_PULL_ERROR = "image_pull_error"
    BAD_CONFIG = "bad_config"
    OOM_KILLED = "oom_killed"
    PROBE_FAILURE = "probe_failure"
    SERVICE_SELECTOR_MISMATCH = "service_selector_mismatch"
    DOWNSTREAM_UNAVAILABLE = "downstream_unavailable"
    UNKNOWN = "unknown"


class Evidence(BaseModel):
    tool: str = Field(description="Name of the tool whose output contains the quote.")
    quote: str = Field(description="A sentence copied verbatim from that tool output.")


class Diagnosis(BaseModel):
    cause_label: CauseLabel = Field(description="The single most likely root cause.")
    target: str = Field(
        description="The broken workload as namespace/deployment, e.g. demo/orders."
    )
    evidence: list[Evidence] = Field(
        min_length=1, description="Quotes from tool outputs that support the cause."
    )
    confidence: float = Field(ge=0, le=1, description="How sure you are, from 0 to 1.")
    summary_ko: str = Field(description="Two to four sentences in Korean: the cause and the clue.")
