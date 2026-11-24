import asyncio
import json
import logging
from dataclasses import dataclass
from typing import AsyncIterator

from fastapi import HTTPException
from openai import APIError, APIStatusError, AsyncOpenAI

from app.core.config import Settings, settings
from app.schemas.chat import ChatRequest

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ModelDefinition:
    alias: str
    label: str
    provider: str
    model_id: str
    access: str


def configured_models(config: Settings = settings) -> list[ModelDefinition]:
    candidates = [
        ModelDefinition("gemini-free", "Gemini · Free", "gemini", config.gemini_model_free, "free"),
        ModelDefinition("gemini-premium", "Gemini · Premium", "gemini", config.gemini_model_premium, "premium"),
        ModelDefinition("groq-budget", "Llama · Budget", "groq", config.groq_model_budget, "free"),
        ModelDefinition("groq-llama-70b", "Llama · 70B", "groq", config.groq_model_llama_70b, "premium"),
        ModelDefinition("groq-qwen", "Qwen · Groq", "groq", config.groq_model_qwen, "free"),
        ModelDefinition("deepseek-chat", "DeepSeek · Chat", "deepseek", config.deepseek_model_chat, "free"),
        ModelDefinition("deepseek-reasoner", "DeepSeek · Reasoner", "deepseek", config.deepseek_model_reasoner, "premium"),
    ]
    return [
        item for item in candidates
        if item.model_id and _provider_credentials(item.provider, config)[0]
    ]


def public_models(config: Settings = settings) -> list[dict[str, str]]:
    return [
        {"id": item.alias, "label": item.label, "provider": item.provider, "access": item.access}
        for item in configured_models(config)
    ]


def provider_status(config: Settings = settings) -> list[dict[str, object]]:
    return [
        {"id": provider, "configured": bool(key), "base_url": base_url}
        for provider, key, base_url in (
            ("gemini", config.gemini_api_key, config.gemini_base_url),
            ("groq", config.groq_api_key, config.groq_base_url),
            ("deepseek", config.deepseek_api_key, config.deepseek_base_url),
        )
    ]


def _provider_credentials(provider: str, config: Settings) -> tuple[str, str]:
    values = {
        "gemini": (config.gemini_api_key, config.gemini_base_url),
        "groq": (config.groq_api_key, config.groq_base_url),
        "deepseek": (config.deepseek_api_key, config.deepseek_base_url),
    }
    return values.get(provider, ("", ""))


def _candidates(requested_model: str, config: Settings) -> list[ModelDefinition]:
    available = configured_models(config)
    if requested_model == "auto":
        aliases = [item.strip() for item in config.ai_fallback_models.split(",") if item.strip()]
        ordered = [model for alias in aliases for model in available if model.alias == alias]
        return ordered or available

    selected = [model for model in available if model.alias == requested_model]
    if not selected:
        raise HTTPException(
            status_code=400,
            detail="That model is not configured or is currently unavailable.",
        )
    return selected


def _client(provider: str, config: Settings) -> AsyncOpenAI:
    api_key, base_url = _provider_credentials(provider, config)
    return AsyncOpenAI(
        api_key=api_key,
        base_url=base_url,
        timeout=config.provider_timeout_seconds,
        max_retries=0,
    )


def _messages(request: ChatRequest) -> list[dict[str, str]]:
    return [{"role": item.role, "content": item.content} for item in request.messages]


def _safe_error(exc: Exception) -> str:
    if isinstance(exc, APIStatusError):
        if exc.status_code == 429:
            return "The provider is rate-limiting requests."
        if exc.status_code in (401, 403):
            return "The provider rejected its server-side credentials."
        if exc.status_code >= 500:
            return "The provider is temporarily unavailable."
    return "The provider could not complete the request."


async def complete_chat(request: ChatRequest, config: Settings = settings) -> dict:
    candidates = _candidates(request.model, config)
    failures: list[str] = []

    for model in candidates:
        client = _client(model.provider, config)
        try:
            for attempt in range(config.provider_max_retries + 1):
                try:
                    kwargs: dict = {"model": model.model_id, "messages": _messages(request)}
                    if request.temperature is not None:
                        kwargs["temperature"] = request.temperature
                    response = await client.chat.completions.create(**kwargs)
                    message = response.choices[0].message
                    return {
                        "id": response.id,
                        "object": "chat.completion",
                        "model": model.alias,
                        "provider": model.provider,
                        "choices": [{
                            "index": 0,
                            "message": {"role": "assistant", "content": message.content or ""},
                            "finish_reason": response.choices[0].finish_reason,
                        }],
                        "usage": response.usage.model_dump() if response.usage else None,
                    }
                except APIError as exc:
                    failures.append(f"{model.alias}: {_safe_error(exc)}")
                    retryable = (
                        not isinstance(exc, APIStatusError)
                        or exc.status_code == 429
                        or exc.status_code >= 500
                    )
                    if not retryable or attempt >= config.provider_max_retries:
                        break
                    await asyncio.sleep(0.35 * (2**attempt))
        finally:
            await client.close()

    logger.warning("All configured AI model attempts failed: %s", "; ".join(failures))
    raise HTTPException(
        status_code=503,
        detail="No configured AI provider could complete this request. Check provider keys, model IDs and status.",
    )


async def stream_chat(request: ChatRequest, config: Settings = settings) -> AsyncIterator[str]:
    candidates = _candidates(request.model, config)
    failures: list[str] = []

    for model in candidates:
        client = _client(model.provider, config)
        emitted = False
        try:
            for attempt in range(config.provider_max_retries + 1):
                try:
                    kwargs: dict = {
                        "model": model.model_id,
                        "messages": _messages(request),
                        "stream": True,
                    }
                    if request.temperature is not None:
                        kwargs["temperature"] = request.temperature
                    stream = await client.chat.completions.create(**kwargs)

                    async for chunk in stream:
                        if not chunk.choices:
                            continue
                        content = chunk.choices[0].delta.content
                        if not content:
                            continue
                        emitted = True
                        payload = {
                            "id": "quanta-stream",
                            "object": "chat.completion.chunk",
                            "model": model.alias,
                            "choices": [{
                                "index": 0,
                                "delta": {"content": content},
                                "finish_reason": None,
                            }],
                        }
                        yield f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"

                    yield "data: [DONE]\n\n"
                    return
                except APIError as exc:
                    failures.append(f"{model.alias}: {_safe_error(exc)}")
                    if emitted:
                        payload = {"error": {"message": "The provider stream ended unexpectedly."}}
                        yield f"data: {json.dumps(payload)}\n\n"
                        yield "data: [DONE]\n\n"
                        return
                    retryable = (
                        not isinstance(exc, APIStatusError)
                        or exc.status_code == 429
                        or exc.status_code >= 500
                    )
                    if not retryable or attempt >= config.provider_max_retries:
                        break
                    await asyncio.sleep(0.35 * (2**attempt))
        finally:
            await client.close()

    logger.warning("All streaming provider attempts failed: %s", "; ".join(failures))
    payload = {"error": {"message": "No configured AI provider could start this response. Check provider keys and model IDs."}}
    yield f"data: {json.dumps(payload)}\n\n"
    yield "data: [DONE]\n\n"
