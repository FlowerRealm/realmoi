from __future__ import annotations

import pytest


def test_resolve_default_upstream_target(monkeypatch: pytest.MonkeyPatch):
    from backend.app.services.upstream_channels import resolve_upstream_target  # noqa: WPS433
    from backend.app.settings import SETTINGS  # noqa: WPS433

    monkeypatch.setattr(SETTINGS, "openai_base_url", "https://api.default.example")
    monkeypatch.setattr(SETTINGS, "openai_api_key", "sk-default")
    monkeypatch.setattr(SETTINGS, "upstream_models_path", "/v1/models")
    monkeypatch.setattr(SETTINGS, "upstream_channels_json", "")

    target = resolve_upstream_target("")
    assert target.channel == ""
    assert target.base_url == "https://api.default.example"
    assert target.api_key == "sk-default"
    assert target.models_path == "/v1/models"


def test_resolve_named_channel_with_fallback(monkeypatch: pytest.MonkeyPatch):
    from backend.app.services.upstream_channels import resolve_upstream_target  # noqa: WPS433
    from backend.app.settings import SETTINGS  # noqa: WPS433

    monkeypatch.setattr(SETTINGS, "openai_base_url", "https://api.default.example")
    monkeypatch.setattr(SETTINGS, "openai_api_key", "sk-default")
    monkeypatch.setattr(SETTINGS, "upstream_models_path", "/v1/models")
    monkeypatch.setattr(
        SETTINGS,
        "upstream_channels_json",
        '{"openai-cn":{"base_url":"https://cn.example.com/v1","api_key":"sk-cn","models_path":"v1/models"}}',
    )

    target = resolve_upstream_target("openai-cn")
    assert target.channel == "openai-cn"
    assert target.base_url == "https://cn.example.com/v1"
    assert target.api_key == "sk-cn"
    assert target.models_path == "/v1/models"


def test_resolve_unknown_channel_raises(monkeypatch: pytest.MonkeyPatch):
    from backend.app.services.upstream_channels import resolve_upstream_target  # noqa: WPS433
    from backend.app.settings import SETTINGS  # noqa: WPS433

    monkeypatch.setattr(SETTINGS, "upstream_channels_json", '{"openai-cn":{"api_key":"sk-cn"}}')

    with pytest.raises(ValueError, match="unknown_upstream_channel:missing"):
        resolve_upstream_target("missing")
