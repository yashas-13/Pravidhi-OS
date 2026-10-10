from fastapi.testclient import TestClient

from engine.provider_router import ProviderRouter
from gateway.api_server import app


def test_gemini_model_is_listed_when_server_key_is_configured(monkeypatch):
    monkeypatch.setenv("PRAVIDHI_API_KEY", "test-api-key")
    monkeypatch.setenv("GEMINI_API_KEY", "test-gemini-key")
    response = TestClient(app).get(
        "/v1/models", headers={"Authorization": "Bearer test-api-key"}
    )
    assert response.status_code == 200
    assert any(model["id"] == "gemini/gemini-2.5-flash" for model in response.json()["data"])


def test_gemini_chat_request_uses_server_side_provider_key(monkeypatch):
    monkeypatch.setenv("PRAVIDHI_API_KEY", "test-api-key")
    monkeypatch.setenv("GEMINI_API_KEY", "test-gemini-key")
    captured = {}

    async def fake_chat(self, messages, model=None, provider=None, max_retries=3):
        captured.update({"messages": messages, "model": model, "provider": provider})
        return {
            "content": "Gemini test response",
            "model": model,
            "provider": provider,
            "usage": {"prompt_tokens": 2, "completion_tokens": 3, "total_tokens": 5},
        }

    monkeypatch.setattr(ProviderRouter, "chat", fake_chat)
    response = TestClient(app).post(
        "/v1/chat/completions",
        headers={"Authorization": "Bearer test-api-key"},
        json={
            "model": "gemini/gemini-2.5-flash",
            "messages": [{"role": "user", "content": "Say hello"}],
        },
    )
    assert response.status_code == 200, response.text
    assert response.json()["choices"][0]["message"]["content"] == "Gemini test response"
    assert captured["provider"] == "gemini"
    assert captured["model"] == "gemini-2.5-flash"
    assert captured["messages"][0]["content"] == "Say hello"


def test_gemini_without_credentials_is_not_advertised(monkeypatch):
    monkeypatch.setenv("PRAVIDHI_API_KEY", "test-api-key")
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    response = TestClient(app).get(
        "/v1/models", headers={"Authorization": "Bearer test-api-key"}
    )
    assert response.status_code == 200
    assert not any(model["id"] == "gemini/gemini-2.5-flash" for model in response.json()["data"])
