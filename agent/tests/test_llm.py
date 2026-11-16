import json

import httpx
import pytest
from langchain_core.messages import HumanMessage, ToolMessage
from pydantic import SecretStr

from hoa_agent.llm import (
    DEFAULT_GEMINI_MODEL,
    GEMINI_BASE_URL,
    GEMMA_MODEL,
    ChatOpenAICompat,
    LLMConfigError,
    build_chat_model,
    load_profile,
)

SIGNATURE = {"google": {"thought_signature": "sig-1"}}


def chat_response(message: dict[str, object]) -> dict[str, object]:
    return {
        "id": "r1",
        "object": "chat.completion",
        "created": 0,
        "model": "gemini-test",
        "choices": [{"index": 0, "finish_reason": "stop", "message": message}],
        "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
    }


def test_gemini_profile_uses_the_key_and_the_default_model() -> None:
    profile = load_profile("gemini", {"GEMINI_API_KEY": "test-key"})

    assert profile.model == DEFAULT_GEMINI_MODEL
    assert profile.base_url == GEMINI_BASE_URL
    assert profile.api_key.get_secret_value() == "test-key"


def test_gemini_model_name_can_be_overridden() -> None:
    env = {"GEMINI_API_KEY": "test-key", "HOA_GEMINI_MODEL": "gemini-other"}

    assert load_profile("gemini", env).model == "gemini-other"


def test_gemma_profile_points_at_the_vllm_server() -> None:
    profile = load_profile("gemma", {"HOA_GEMMA_BASE_URL": "http://gpu.test:8000/v1"})

    assert profile.model == GEMMA_MODEL
    assert profile.base_url == "http://gpu.test:8000/v1"


@pytest.mark.parametrize(
    ("name", "missing"), [("gemini", "GEMINI_API_KEY"), ("gemma", "HOA_GEMMA_BASE_URL")]
)
def test_missing_settings_name_the_variable(name: str, missing: str) -> None:
    with pytest.raises(LLMConfigError, match=missing):
        load_profile(name, {})


def test_unknown_profile_is_rejected() -> None:
    with pytest.raises(LLMConfigError, match="unknown model profile"):
        load_profile("gpt", {})


def test_chat_model_is_deterministic_and_bounded() -> None:
    profile = load_profile("gemma", {"HOA_GEMMA_BASE_URL": "http://gpu.test:8000/v1"})

    model = build_chat_model(profile)

    assert model.model_name == GEMMA_MODEL
    assert model.openai_api_base == "http://gpu.test:8000/v1"
    assert model.temperature == 0
    assert model.max_retries == 2


def test_profile_does_not_print_the_key() -> None:
    profile = load_profile("gemini", {"GEMINI_API_KEY": "test-key"})

    assert "test-key" not in repr(profile)


@pytest.mark.anyio
async def test_tool_call_signature_goes_back_with_the_tool_result() -> None:
    sent: list[dict[str, object]] = []
    replies = [
        chat_response(
            {
                "role": "assistant",
                "content": None,
                "tool_calls": [
                    {
                        "id": "c1",
                        "type": "function",
                        "function": {"name": "list_pods", "arguments": '{"namespace": "demo"}'},
                        "extra_content": SIGNATURE,
                    }
                ],
            }
        ),
        chat_response({"role": "assistant", "content": "orders cannot pull its image"}),
    ]

    def endpoint(request: httpx.Request) -> httpx.Response:
        sent.append(json.loads(request.content))
        return httpx.Response(200, json=replies.pop(0))

    model = ChatOpenAICompat(
        model="gemini-test",
        base_url="https://llm.test/v1",
        api_key=SecretStr("test-key"),
        http_async_client=httpx.AsyncClient(transport=httpx.MockTransport(endpoint)),
    )
    first = await model.ainvoke([HumanMessage("check demo")])
    await model.ainvoke(
        [HumanMessage("check demo"), first, ToolMessage("{}", tool_call_id="c1", name="list_pods")]
    )

    assert first.tool_calls[0]["id"] == "c1"
    echoed = sent[1]["messages"][1]["tool_calls"][0]
    assert echoed["extra_content"] == SIGNATURE
    assert "hoa_tool_call_extras" not in json.dumps(sent[1])
