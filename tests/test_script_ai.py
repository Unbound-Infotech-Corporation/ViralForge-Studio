import json
import logging

import httpx
import pytest

from trendforge.domain.enums import ScriptAiProvider, ScriptAiTask
from trendforge.services.script_ai import (
    ScriptAiConfig,
    ScriptAiError,
    build_messages,
    chat_url,
    config_from_settings,
    generate_script_ai,
    parse_chat_response,
    redact_secret,
)
from trendforge.settings import AppSettings


def test_settings_roundtrip_keeps_script_ai_fields(tmp_path):
    path = tmp_path / "settings.json"
    original = AppSettings(
        script_ai_provider=ScriptAiProvider.ANTHROPIC,
        script_ai_api_key="sk-ant-secret",
        script_ai_base_url="https://api.anthropic.com/v1",
        script_ai_model="claude-custom",
    )
    original._path = path
    original.save()
    assert "sk-ant-secret" not in repr(original)
    raw = json.loads(path.read_text(encoding="utf-8"))
    assert raw["script_ai_provider"] == "anthropic"
    assert raw["script_ai_api_key"] == "sk-ant-secret"
    loaded = AppSettings._from_dict(raw)
    assert loaded.script_ai_provider is ScriptAiProvider.ANTHROPIC
    assert loaded.script_ai_api_key == "sk-ant-secret"
    assert loaded.script_ai_base_url == "https://api.anthropic.com/v1"
    assert loaded.script_ai_model == "claude-custom"


def test_unknown_provider_falls_back_to_ollama():
    loaded = AppSettings._from_dict({"script_ai_provider": "nope", "script_ai_api_key": "kept"})
    assert loaded.script_ai_provider is ScriptAiProvider.OLLAMA
    assert loaded.script_ai_api_key == "kept"


def test_config_from_settings_ollama_reuses_existing_host():
    settings = AppSettings(ollama_url="http://10.0.0.8:11434", ollama_model="llama3.1:8b")
    config = config_from_settings(settings)
    assert config.provider is ScriptAiProvider.OLLAMA
    assert config.base_url == "http://10.0.0.8:11434"
    assert config.model == "llama3.1:8b"
    assert config.api_key == ""


def test_config_from_settings_cloud_defaults():
    settings = AppSettings(script_ai_provider=ScriptAiProvider.XAI, script_ai_api_key="k")
    config = config_from_settings(settings)
    assert config.base_url == "https://api.x.ai/v1"
    assert config.model == "grok-3"


def test_missing_key_fails_before_network():
    config = ScriptAiConfig(ScriptAiProvider.OPENAI, "", "https://api.openai.com/v1", "gpt-4o-mini")
    with pytest.raises(ScriptAiError, match="API key is missing"):
        generate_script_ai(config, ScriptAiTask.OUTLINE, "harbor lights")


def test_empty_brief_fails():
    config = ScriptAiConfig(ScriptAiProvider.OLLAMA, "", "http://127.0.0.1:11434", "qwen2.5:7b")
    with pytest.raises(ScriptAiError, match="needs a brief"):
        generate_script_ai(config, ScriptAiTask.DIALOGUE, "  ")


def test_shot_list_prompt_stays_on_footage():
    messages = build_messages(ScriptAiTask.SHOT_LIST, "the night shift")
    system = messages[0]["content"].lower()
    assert messages[0]["role"] == "system"
    assert "photographed" in system
    assert "title card" in system
    assert "the night shift" in messages[1]["content"]


def test_parse_openai_anthropic_and_ollama():
    assert parse_chat_response(
        ScriptAiProvider.OPENAI,
        {"choices": [{"message": {"content": "TITLE: Dock"}}]},
    ) == "TITLE: Dock"
    assert parse_chat_response(
        ScriptAiProvider.XAI,
        {"choices": [{"message": {"content": [{"type": "text", "text": "beat"}]}}]},
    ) == "beat"
    assert parse_chat_response(
        ScriptAiProvider.ANTHROPIC,
        {"content": [{"type": "text", "text": "DECISIONS"}]},
    ) == "DECISIONS"
    assert parse_chat_response(
        ScriptAiProvider.OLLAMA,
        {"message": {"role": "assistant", "content": "VO: line"}},
    ) == "VO: line"


def test_parse_provider_error_is_visible():
    with pytest.raises(ScriptAiError, match="quota"):
        parse_chat_response(ScriptAiProvider.OPENAI, {"error": {"message": "quota exceeded"}})


def test_generate_openai_with_mock_transport(caplog):
    caplog.set_level(logging.DEBUG)

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v1/chat/completions"
        assert request.headers["Authorization"] == "Bearer sk-test-secret"
        body = json.loads(request.content.decode())
        assert body["model"] == "gpt-4o-mini"
        assert body["messages"][0]["role"] == "system"
        assert "harbor" in body["messages"][1]["content"]
        return httpx.Response(200, json={"choices": [{"message": {"content": "TITLE: Harbor Lights"}}]})

    client = httpx.Client(transport=httpx.MockTransport(handler))
    config = ScriptAiConfig(ScriptAiProvider.OPENAI, "sk-test-secret", "https://api.openai.com/v1", "gpt-4o-mini")
    text = generate_script_ai(config, ScriptAiTask.OUTLINE, "harbor lights", client=client)
    assert text == "TITLE: Harbor Lights"
    logged = "\n".join(record.getMessage() for record in caplog.records if record.name == "script_ai")
    assert "sk-test-secret" not in logged
    assert "sk-test-secret" not in text


def test_http_error_redacts_key_and_names_status():
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"error": {"message": "invalid sk-test-secret"}})

    client = httpx.Client(transport=httpx.MockTransport(handler))
    config = ScriptAiConfig(
        ScriptAiProvider.ANTHROPIC,
        "sk-test-secret",
        "https://api.anthropic.com/v1",
        "claude-3-5-sonnet-latest",
    )
    with pytest.raises(ScriptAiError) as caught:
        generate_script_ai(config, ScriptAiTask.MEETING_NOTES, "mini series bible", client=client)
    message = str(caught.value)
    assert "401" in message
    assert "sk-test-secret" not in message
    assert "[redacted]" in message


def test_chat_urls_and_redact():
    assert chat_url(ScriptAiProvider.OLLAMA, "http://127.0.0.1:11434") == "http://127.0.0.1:11434/api/chat"
    assert chat_url(ScriptAiProvider.XAI, "https://api.x.ai/v1") == "https://api.x.ai/v1/chat/completions"
    assert chat_url(ScriptAiProvider.ANTHROPIC, "https://api.anthropic.com") == "https://api.anthropic.com/v1/messages"
    assert redact_secret("invalid sk-live", "sk-live") == "invalid [redacted]"
