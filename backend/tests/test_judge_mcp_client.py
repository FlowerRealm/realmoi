import pytest


def test_ensure_connected_catches_unexpected_connect_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    from backend.app.services import judge_mcp_client as mod

    class WeirdConnectError(Exception):
        pass

    attempted: list[str] = []

    def fake_connect(url: str, open_timeout: float = 0) -> None:  # noqa: ARG001
        attempted.append(url)
        raise WeirdConnectError("boom")

    monkeypatch.setattr(mod, "connect", fake_connect)

    client = mod.McpJudgeClient(ws_urls=["ws://a.example/api/mcp/ws", "ws://b.example/api/mcp/ws"])
    with pytest.raises(mod.McpJudgeClientError):
        client.ensure_connected()

    assert attempted == ["ws://a.example/api/mcp/ws", "ws://b.example/api/mcp/ws"]

