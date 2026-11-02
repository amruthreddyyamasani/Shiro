from __future__ import annotations

import json

import pytest
from pydantic import ValidationError

from shiro.config import Settings


def test_settings_load_json_and_environment_override(tmp_path, monkeypatch):
    config_path = tmp_path / "config.json"
    config_path.write_text(
        json.dumps({"port": 8123, "ollama_model": "custom"}),
        encoding="utf-8",
    )
    monkeypatch.setenv("SHIRO_PORT", "8124")

    settings = Settings.load(config_path)

    assert settings.port == 8124
    assert settings.ollama_model == "custom"
    assert settings.host == "127.0.0.1"


def test_default_database_uses_local_app_data(tmp_path, monkeypatch):
    local_app_data = tmp_path / "LocalAppData"
    monkeypatch.setenv("LOCALAPPDATA", str(local_app_data))

    settings = Settings()

    assert settings.resolved_database_path == (
        local_app_data / "SHIRO" / "data" / "shiro.db"
    )


def test_settings_reject_non_localhost_binding():
    with pytest.raises(ValidationError):
        Settings(host="0.0.0.0")

    with pytest.raises(ValidationError):
        Settings(ollama_base_url="https://example.com/ollama")


def test_settings_keep_thinking_disabled():
    with pytest.raises(ValidationError):
        Settings(thinking_enabled=True)


def test_settings_allow_registered_tools_when_explicitly_enabled():
    assert Settings(allow_tools=True).allow_tools is True
