"""Bring-your-own-key script writer.

Chat subscriptions on grok.com, chatgpt.com, and claude.ai do not authorize
these API calls. Callers must pass an API key (except local Ollama).
Secrets are never written to the log.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

import httpx

from trendforge.domain.enums import ScriptAiProvider, ScriptAiTask
from trendforge.logging_setup import get_logger
from trendforge.settings import AppSettings

log = get_logger("script_ai")

_ANTHROPIC_VERSION = "2023-06-01"
_MAX_TOKENS = 4096

_CINEMA_RULE = (
    "You write for a local cinema studio. Narration is spoken voiceover. "
    "Picture is photographed footage only: camera, light, location, action. "
    "Never title cards, motion graphics, kinetic text, slides, diagrams, "
    "or a zoom on a still image."
)


@dataclass(frozen=True, slots=True)
class ProviderSpec:
    provider: ScriptAiProvider
    label: str
    default_base_url: str
    default_model: str
    needs_key: bool


SPECS: dict[ScriptAiProvider, ProviderSpec] = {
    ScriptAiProvider.XAI: ProviderSpec(
        ScriptAiProvider.XAI,
        "xAI / Grok",
        "https://api.x.ai/v1",
        "grok-3",
        True,
    ),
    ScriptAiProvider.OPENAI: ProviderSpec(
        ScriptAiProvider.OPENAI,
        "OpenAI / ChatGPT",
        "https://api.openai.com/v1",
        "gpt-4o-mini",
        True,
    ),
    ScriptAiProvider.ANTHROPIC: ProviderSpec(
        ScriptAiProvider.ANTHROPIC,
        "Anthropic / Claude",
        "https://api.anthropic.com/v1",
        "claude-3-5-sonnet-latest",
        True,
    ),
    ScriptAiProvider.OLLAMA: ProviderSpec(
        ScriptAiProvider.OLLAMA,
        "Ollama (local)",
        "http://127.0.0.1:11434",
        "qwen2.5:7b",
        False,
    ),
}

PROVIDER_ORDER: tuple[ScriptAiProvider, ...] = (
    ScriptAiProvider.XAI,
    ScriptAiProvider.OPENAI,
    ScriptAiProvider.ANTHROPIC,
    ScriptAiProvider.OLLAMA,
)

TASK_LABELS: tuple[tuple[ScriptAiTask, str], ...] = (
    (ScriptAiTask.OUTLINE, "Outline / episode synopsis"),
    (ScriptAiTask.SHOT_LIST, "Shot list (story-locked beats)"),
    (ScriptAiTask.DIALOGUE, "Dialogue / VO lines per beat"),
    (ScriptAiTask.MEETING_NOTES, "Virtual meeting notes draft"),
)

_DEFAULT_MODELS = frozenset(spec.default_model for spec in SPECS.values())
_DEFAULT_BASES = frozenset(spec.default_base_url for spec in SPECS.values())


class ScriptAiError(RuntimeError):
    """User-visible Script AI failure. The message must not contain secrets."""


@dataclass(frozen=True, slots=True)
class ScriptAiConfig:
    provider: ScriptAiProvider
    api_key: str
    base_url: str
    model: str

    @property
    def spec(self) -> ProviderSpec:
        return SPECS[self.provider]


def config_from_settings(settings: AppSettings) -> ScriptAiConfig:
    provider = settings.script_ai_provider
    if provider not in SPECS:
        provider = ScriptAiProvider.OLLAMA
    spec = SPECS[provider]
    base = (settings.script_ai_base_url or "").strip()
    model = (settings.script_ai_model or "").strip()
    if provider is ScriptAiProvider.OLLAMA:
        base = base or (settings.ollama_url or "").strip() or spec.default_base_url
        model = model or (settings.ollama_model or "").strip() or spec.default_model
    else:
        base = base or spec.default_base_url
        model = model or spec.default_model
    return ScriptAiConfig(
        provider=provider,
        api_key=(settings.script_ai_api_key or "").strip(),
        base_url=base.rstrip("/"),
        model=model,
    )


def known_default_model(model: str) -> bool:
    return model.strip() in _DEFAULT_MODELS


def known_default_base(url: str) -> bool:
    return url.strip().rstrip("/") in _DEFAULT_BASES


def redact_secret(text: str, secret: str) -> str:
    cleaned = text or ""
    token = (secret or "").strip()
    if token and token in cleaned:
        cleaned = cleaned.replace(token, "[redacted]")
    return cleaned


def build_messages(task: ScriptAiTask, brief: str, context: str = "") -> list[dict[str, str]]:
    extra = (context or "").strip()
    context_block = f"\n\nExisting draft (stay consistent with it):\n{extra}" if extra else ""
    user = f"Brief:\n{brief.strip()}{context_block}"
    task_prompt = {
        ScriptAiTask.OUTLINE: (
            "Write an episode outline. Return plain text with these labels:\n"
            "TITLE:\nLOGLINE:\nSYNOPSIS:\nBEATS:\n"
            "1. one story beat per line\n"
            "Each beat is something the viewer sees and the narrator can say. No markdown fences."
        ),
        ScriptAiTask.SHOT_LIST: (
            "Write a story-locked shot list. Do not add beats that are not in the brief. "
            "Separate shots with a blank line. For each shot use exactly:\n"
            "[Beat title]\n"
            "VO: spoken line\n"
            "Visual: photographed footage (camera, light, location, action)\n"
            "No markdown fences."
        ),
        ScriptAiTask.DIALOGUE: (
            "Write dialogue and voiceover lines for each beat in the brief. "
            "Do not invent new plot beats. Separate beats with a blank line. Format:\n"
            "[Beat title]\n"
            "VO: narrator line\n"
            "NAME: spoken line\n"
            "No markdown fences."
        ),
        ScriptAiTask.MEETING_NOTES: (
            "Draft virtual writers-room meeting notes for a later mini series. "
            "This is a planning document, not a claim that a calendar meeting already happened. "
            "Use plain text sections: ATTENDEES (roles only), AGENDA, DECISIONS, OPEN QUESTIONS, EPISODE BEATS. "
            "No markdown fences."
        ),
    }[task]
    system = f"{_CINEMA_RULE}\n\n{task_prompt}"
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]


def generate_script_ai(
    config: ScriptAiConfig,
    task: ScriptAiTask,
    brief: str,
    *,
    context: str = "",
    client: httpx.Client | None = None,
    timeout: float = 120.0,
) -> str:
    """Run one Script AI task. Raises ScriptAiError with a user-visible message."""
    text = (brief or "").strip()
    if not text:
        raise ScriptAiError("Script AI needs a brief. Describe the episode, topic, or beats.")
    spec = config.spec
    if spec.needs_key and not config.api_key.strip():
        raise ScriptAiError(
            f"Script AI: {spec.label} API key is missing. "
            "A chat-site subscription does not unlock the API. "
            "Add a key under Settings → Script AI."
        )
    if not config.model.strip():
        raise ScriptAiError(f"Script AI model name is empty for {spec.label}.")
    if not config.base_url.strip():
        raise ScriptAiError(f"Script AI base URL is empty for {spec.label}.")

    messages = build_messages(task, text, context)
    log.info(
        "script ai request provider=%s model=%s task=%s",
        config.provider.value,
        config.model,
        task.value,
    )
    try:
        if client is None:
            with httpx.Client(timeout=timeout) as http:
                payload = _post(http, config, messages)
        else:
            payload = _post(client, config, messages)
        result = parse_chat_response(config.provider, payload).strip()
    except ScriptAiError:
        raise
    except httpx.HTTPError as exc:
        detail = redact_secret(str(exc), config.api_key)
        log.error("script ai transport error provider=%s detail=%s", config.provider.value, detail)
        raise ScriptAiError(f"Script AI {spec.label} request failed: {detail}") from exc

    if not result:
        raise ScriptAiError(f"Script AI {spec.label} returned an empty response.")
    result = redact_secret(result, config.api_key)
    log.info(
        "script ai ok provider=%s model=%s task=%s chars=%s",
        config.provider.value,
        config.model,
        task.value,
        len(result),
    )
    return result


def parse_chat_response(provider: ScriptAiProvider, payload: dict[str, Any]) -> str:
    if not isinstance(payload, dict):
        raise ScriptAiError("Script AI response was not a JSON object.")
    error = payload.get("error")
    if error:
        if isinstance(error, dict):
            message = str(error.get("message") or error)
        else:
            message = str(error)
        raise ScriptAiError(f"Script AI error: {message}")

    if provider is ScriptAiProvider.ANTHROPIC:
        return _anthropic_text(payload)
    if provider is ScriptAiProvider.OLLAMA:
        return _ollama_text(payload)
    return _openai_text(payload)


def chat_url(provider: ScriptAiProvider, base_url: str) -> str:
    base = (base_url or "").strip().rstrip("/")
    if provider is ScriptAiProvider.ANTHROPIC:
        if base.endswith("/messages"):
            return base
        if base.endswith("/v1"):
            return base + "/messages"
        return base + "/v1/messages"
    if provider is ScriptAiProvider.OLLAMA:
        if base.endswith("/api/chat"):
            return base
        return base + "/api/chat"
    if base.endswith("/chat/completions"):
        return base
    if base.endswith("/v1"):
        return base + "/chat/completions"
    return base + "/v1/chat/completions"


def _post(client: httpx.Client, config: ScriptAiConfig, messages: list[dict[str, str]]) -> dict[str, Any]:
    url = chat_url(config.provider, config.base_url)
    headers = {"Content-Type": "application/json"}
    if config.provider is ScriptAiProvider.ANTHROPIC:
        headers["x-api-key"] = config.api_key
        headers["anthropic-version"] = _ANTHROPIC_VERSION
        system = "\n\n".join(m["content"] for m in messages if m["role"] == "system")
        user_messages = [{"role": m["role"], "content": m["content"]} for m in messages if m["role"] != "system"]
        body: dict[str, Any] = {
            "model": config.model,
            "max_tokens": _MAX_TOKENS,
            "system": system,
            "messages": user_messages,
        }
    elif config.provider is ScriptAiProvider.OLLAMA:
        body = {"model": config.model, "messages": messages, "stream": False}
        if config.api_key.strip():
            headers["Authorization"] = f"Bearer {config.api_key}"
    else:
        headers["Authorization"] = f"Bearer {config.api_key}"
        body = {
            "model": config.model,
            "messages": messages,
            "temperature": 0.6,
        }

    response = client.post(url, headers=headers, json=body)
    raw = response.text
    if response.status_code >= 400:
        detail = redact_secret(_error_detail(raw), config.api_key)
        log.error(
            "script ai http error provider=%s status=%s detail=%s",
            config.provider.value,
            response.status_code,
            detail,
        )
        raise ScriptAiError(
            f"Script AI {config.spec.label} HTTP {response.status_code}: {detail}"
        )
    try:
        data = response.json()
    except json.JSONDecodeError as exc:
        raise ScriptAiError(
            f"Script AI {config.spec.label} returned non-JSON (HTTP {response.status_code})."
        ) from exc
    if not isinstance(data, dict):
        raise ScriptAiError(f"Script AI {config.spec.label} returned an unexpected payload.")
    return data


def _error_detail(raw: str) -> str:
    text = (raw or "").strip()
    if not text:
        return "no response body"
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return text[:400]
    if isinstance(data, dict):
        error = data.get("error")
        if isinstance(error, dict) and error.get("message"):
            return str(error["message"])[:400]
        if isinstance(error, str):
            return error[:400]
        if data.get("message"):
            return str(data["message"])[:400]
    return text[:400]


def _openai_text(payload: dict[str, Any]) -> str:
    choices = payload.get("choices") or []
    if not choices or not isinstance(choices, list):
        raise ScriptAiError("Script AI response had no choices.")
    first = choices[0] if isinstance(choices[0], dict) else {}
    message = first.get("message") if isinstance(first, dict) else {}
    if not isinstance(message, dict):
        message = {}
    content = message.get("content")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for part in content:
            if isinstance(part, str):
                parts.append(part)
            elif isinstance(part, dict):
                parts.append(str(part.get("text") or ""))
        return "".join(parts)
    raise ScriptAiError("Script AI response content was empty or unrecognized.")


def _anthropic_text(payload: dict[str, Any]) -> str:
    blocks = payload.get("content") or []
    if isinstance(blocks, str):
        return blocks
    if not isinstance(blocks, list):
        raise ScriptAiError("Script AI response content was empty or unrecognized.")
    parts: list[str] = []
    for block in blocks:
        if isinstance(block, str):
            parts.append(block)
        elif isinstance(block, dict) and block.get("type", "text") == "text":
            parts.append(str(block.get("text") or ""))
    if not parts:
        raise ScriptAiError("Script AI response content was empty or unrecognized.")
    return "".join(parts)


def _ollama_text(payload: dict[str, Any]) -> str:
    message = payload.get("message")
    if isinstance(message, dict) and message.get("content"):
        return str(message["content"])
    if payload.get("response"):
        return str(payload["response"])
    raise ScriptAiError("Script AI response content was empty or unrecognized.")
