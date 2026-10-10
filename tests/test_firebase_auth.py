from fastapi import FastAPI
from fastapi.testclient import TestClient

from gateway import firebase_auth
from gateway.security import CommercialSecurityMiddleware


def make_app():
    app = FastAPI()
    app.add_middleware(CommercialSecurityMiddleware)

    @app.post("/auth/firebase/verify")
    async def verify(request):
        from gateway.api_server import verify_firebase_identity
        return await verify_firebase_identity(request)

    @app.get("/api/protected")
    def protected(request):
        return {"principal": getattr(request.state, "principal", None) is not None}

    return app


def test_verification_requires_bearer(monkeypatch):
    monkeypatch.setenv("PRAVIDHI_API_KEY", "server-key")
    client = TestClient(make_app())
    response = client.post("/auth/firebase/verify")
    assert response.status_code == 401
    assert response.json()["error"] == "firebase_bearer_required"


def test_verification_returns_only_allowlisted_verified_identity(monkeypatch):
    monkeypatch.setenv("PRAVIDHI_API_KEY", "server-key")
    monkeypatch.setattr(
        firebase_auth,
        "verify_firebase_id_token",
        lambda token: {"uid": "firebase-user-1", "email": "user@example.com", "email_verified": True},
    )
    client = TestClient(make_app())
    response = client.post("/auth/firebase/verify", headers={"Authorization": "Bearer valid-test-token"})
    assert response.status_code == 200
    assert response.json()["uid"] == "firebase-user-1"
    assert response.json()["email_verified"] is True
    assert response.json()["authorization"] == "not_granted"
    assert "tenant_id" not in response.json()
    assert "role" not in response.json()


def test_invalid_firebase_token_is_rejected(monkeypatch):
    monkeypatch.setenv("PRAVIDHI_API_KEY", "server-key")

    def reject(_token):
        raise firebase_auth.FirebaseTokenInvalid()

    monkeypatch.setattr(firebase_auth, "verify_firebase_id_token", reject)
    response = TestClient(make_app()).post(
        "/auth/firebase/verify", headers={"Authorization": "Bearer invalid"}
    )
    assert response.status_code == 401
    assert response.json()["error"] == "invalid_firebase_id_token"


def test_firebase_identity_does_not_authorize_protected_api(monkeypatch):
    monkeypatch.setenv("PRAVIDHI_API_KEY", "expected-server-key")
    monkeypatch.delenv("PRAVIDHI_ALLOW_UNAUTHENTICATED_DEV", raising=False)
    response = TestClient(make_app()).get(
        "/api/protected", headers={"Authorization": "Bearer firebase-id-token"}
    )
    assert response.status_code == 401
