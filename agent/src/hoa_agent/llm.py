from collections.abc import Mapping

import openai
from langchain_core.language_models import LanguageModelInput
from langchain_core.outputs import ChatResult
from langchain_openai import ChatOpenAI
from pydantic import BaseModel, SecretStr

GEMINI_BASE_URL = "https://generativelanguage.googleapis.com/v1beta/openai/"
# 2026-11-16 무료 등급 확인: 3.5 Flash는 하루 20회라 조사 네댓 번이면 끝나고 한 번에 200초쯤 걸린다.
# 3.5 Flash-Lite는 같은 조사를 26초에 맞혔다(3.8·3.7 Flash는 503·시간 초과, 2.5 Flash는 404)
DEFAULT_GEMINI_MODEL = "gemini-3.5-flash-lite"
GEMMA_MODEL = "gemma4-26b-a4b"
# 기본은 회사 GPU의 Gemma — 요청 한도가 없고 클러스터 데이터가 밖으로 나가지 않는다.
# Gemini는 회사망 밖에서의 대체이자 평가의 비교 기준이다(사용자 결정 2026-11-16)
DEFAULT_MODEL = "gemma"
MODEL_NAMES = ("gemma", "gemini")
REQUEST_TIMEOUT_SECONDS = 120
MAX_RETRIES = 2
TOOL_CALL_EXTRAS = "hoa_tool_call_extras"


class LLMConfigError(Exception):
    pass


class ModelProfile(BaseModel):
    name: str
    model: str
    base_url: str
    api_key: SecretStr


def load_profile(name: str, env: Mapping[str, str]) -> ModelProfile:
    if name == "gemini":
        key = env.get("GEMINI_API_KEY", "").strip()
        if not key:
            raise LLMConfigError(
                "GEMINI_API_KEY is not set — put it in .env (local, "
                "run with uv run --env-file .env) or the hoa-agent-llm Secret (cluster)"
            )
        model = env.get("HOA_GEMINI_MODEL", "").strip() or DEFAULT_GEMINI_MODEL
        return ModelProfile(
            name="gemini", model=model, base_url=GEMINI_BASE_URL, api_key=SecretStr(key)
        )
    if name == "gemma":
        url = env.get("HOA_GEMMA_BASE_URL", "").strip()
        if not url:
            raise LLMConfigError(
                "HOA_GEMMA_BASE_URL is not set — put it in .env (local, "
                "run with uv run --env-file .env) or the hoa-agent-llm Secret (cluster)"
            )
        return ModelProfile(
            name="gemma", model=GEMMA_MODEL, base_url=url, api_key=SecretStr("EMPTY")
        )
    raise LLMConfigError(f"unknown model profile: {name} (choose one of {', '.join(MODEL_NAMES)})")


class ChatOpenAICompat(ChatOpenAI):
    """OpenAI 호환 엔드포인트가 tool_calls에 붙인 확장 필드를 다음 요청에 그대로 돌려준다.

    Gemini 3는 도구 호출마다 extra_content.google.thought_signature를 붙이고, 그 값 없이
    도구 결과를 보내면 400으로 거절한다. ChatOpenAI는 이 필드를 버린다.
    """

    def _create_chat_result(
        self, response: dict | openai.BaseModel, generation_info: dict | None = None
    ) -> ChatResult:
        result = super()._create_chat_result(response, generation_info)
        raw = (
            response
            if isinstance(response, dict)
            else response.model_dump(
                exclude={"choices": {"__all__": {"message": {"parsed"}}}}, warnings=False
            )
        )
        for generation, choice in zip(result.generations, raw.get("choices") or [], strict=False):
            extras = {
                call["id"]: call["extra_content"]
                for call in choice["message"].get("tool_calls") or []
                if call.get("extra_content")
            }
            if extras:
                generation.message.additional_kwargs[TOOL_CALL_EXTRAS] = extras
        return result

    def _get_request_payload(
        self, input_: LanguageModelInput, *, stop: list[str] | None = None, **kwargs: object
    ) -> dict[str, object]:
        payload = super()._get_request_payload(input_, stop=stop, **kwargs)
        extras: dict[str, object] = {}
        for message in self._convert_input(input_).to_messages():
            extras.update(message.additional_kwargs.get(TOOL_CALL_EXTRAS, {}))
        for sent in payload.get("messages", []):
            for call in sent.get("tool_calls", []):
                if call["id"] in extras:
                    call["extra_content"] = extras[call["id"]]
        return payload


def build_chat_model(profile: ModelProfile) -> ChatOpenAICompat:
    return ChatOpenAICompat(
        model=profile.model,
        base_url=profile.base_url,
        api_key=profile.api_key,
        temperature=0,
        timeout=REQUEST_TIMEOUT_SECONDS,
        max_retries=MAX_RETRIES,
        # 스트리밍 응답은 _create_chat_result를 거치지 않아 도구 호출 서명이 빠진다
        disable_streaming=True,
    )
