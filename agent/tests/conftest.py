from collections.abc import Callable, Sequence

import pytest
from langchain_core.callbacks import CallbackManagerForLLMRun
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from langchain_core.runnables import Runnable, RunnableLambda
from langchain_core.tools import BaseTool
from pydantic import Field

from hoa_agent.diagnosis import CauseLabel, Diagnosis, Evidence


class ScriptedChatModel(BaseChatModel):
    """대본(replies)대로 답하는 가짜 채팅 모델 — 조사 단계와 진단 단계가 받은 메시지를 기록한다."""

    replies: list[AIMessage]
    diagnosis: Diagnosis | None
    investigate_requests: list[list[BaseMessage]] = Field(default_factory=list)
    diagnose_requests: list[list[BaseMessage]] = Field(default_factory=list)

    @property
    def _llm_type(self) -> str:
        return "scripted"

    def _generate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: CallbackManagerForLLMRun | None = None,
        **kwargs: object,
    ) -> ChatResult:
        self.investigate_requests.append(list(messages))
        return ChatResult(generations=[ChatGeneration(message=self.replies.pop(0))])

    def bind_tools(self, tools: Sequence[BaseTool], **kwargs: object) -> Runnable:
        return self

    def with_structured_output(self, schema: object, **kwargs: object) -> Runnable:
        def answer(messages: list[BaseMessage]) -> dict[str, object]:
            self.diagnose_requests.append(list(messages))
            if self.diagnosis is None:
                raw = AIMessage("not json")
                return {"raw": raw, "parsed": None, "parsing_error": ValueError("not json")}
            raw = AIMessage(
                self.diagnosis.model_dump_json(),
                usage_metadata={"input_tokens": 900, "output_tokens": 120, "total_tokens": 1020},
            )
            return {"raw": raw, "parsed": self.diagnosis, "parsing_error": None}

        return RunnableLambda(answer)


def tool_call(name: str, args: dict[str, object], call_id: str) -> dict[str, object]:
    return {"name": name, "args": args, "id": call_id, "type": "tool_call"}


def reply(*calls: dict[str, object], text: str = "", input_tokens: int = 1_000) -> AIMessage:
    return AIMessage(
        text,
        tool_calls=list(calls),
        usage_metadata={
            "input_tokens": input_tokens,
            "output_tokens": 50,
            "total_tokens": input_tokens + 50,
        },
    )


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture
def diagnosis() -> Diagnosis:
    return Diagnosis(
        cause_label=CauseLabel.IMAGE_PULL_ERROR,
        target="demo/orders",
        evidence=[Evidence(tool="get_events", quote="Failed to pull image")],
        confidence=0.9,
        summary_ko="orders 이미지 태그가 없어 내려받지 못한다.",
    )


@pytest.fixture
def scripted_model(diagnosis: Diagnosis) -> Callable[..., ScriptedChatModel]:
    def build(
        replies: list[AIMessage], *, diagnosis: Diagnosis | None = diagnosis
    ) -> ScriptedChatModel:
        return ScriptedChatModel(replies=replies, diagnosis=diagnosis)

    return build


@pytest.fixture
def make_tool_call() -> Callable[..., dict[str, object]]:
    return tool_call


@pytest.fixture
def make_reply() -> Callable[..., AIMessage]:
    return reply
