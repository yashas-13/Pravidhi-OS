import json

from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from gateway import firebase_auth
from gateway.security import CommercialSecurityMiddleware


def make_app():
    app = FastAPI()
    app.add_middleware(CommercialSecurityMiddleware)

    @app.get("/api/whoami")
    async def whoami(request: Request):
        principal = request.state.principal
        return {
            "subject": principal.subject,
            "account_id": principal.account_id,
            "tenant_id": principal.tenant_id,
            "role": principal.role,
            "auth_method": principal.auth_method,
        }

    return app


def test_mapped_firebase_uid_resolves_only_server_owned_principal(monkeypatch):
    monkeypatch.setenv("FIREBASE_PROJECT_ID", "pravidhi-os")
    monkeypatch.delenv("PRAVIDHI_API_KEY", raising=False)
    monkeypatch.delenv("PRAVIDHI_ALLOW_UNAUTHENTICATED_DEV", raising=False)
    monkeypatch.setenv(
        "PRAVIDHI_FIREBASE_USER_MAPPINGS_JSON",
        json.dumps({
            "uid-approved": {
                "account_id": "acct-001",
                "tenant_id": "tenant-alpha",
                "role": "operator",
            }
        }),
    )
    monkeypatch.setattr(
        firebase_auth,
        "verify_firebase_id_token",
        lambda token: {
            "uid": "uid-approved",
            "email": "verified@example.com",
            "email_verified": True,
        },
    )
    response = TestClient(make_app()).get(
        "/api/whoami",
        headers={
            "Authorization": "Bearer valid-firebase-token",
            "X-Pravidhi-Tenant": "tenant-attacker",
            "X-Pravidhi-Role": "admin",
        },
    )
    assert response.status_code == 200
    assert response.json() == {
        "subject": "firebase:uid-approved",
        "account_id": "acct-001",
        "tenant_id": "tenant-alpha",
        "role": "operator",
        "auth_method": "firebase",
    }


def test_unmapped_firebase_uid_is_denied(monkeypatch):
    monkeypatch.delenv("PRAVIDHI_API_KEY", raising=False)
    monkeypatch.setenv(
        "PRAVIDHI_FIREBASE_USER_MAPPINGS_JSON",
        json.dumps({
            "different-uid": {
                "account_id": "acct-001",
                "tenant_id": "tenant-alpha",
                "role": "operator",
            }
        }),
    )
    monkeypatch.setattr(
        firebase_auth,
        "verify_firebase_id_token",
        lambda token: {"uid": "unknown-uid", "email": "user@example.com", "email_verified": True},
    )
    response = TestClient(make_app()).get(
        "/api/whoami", headers={"Authorization": "Bearer valid-firebase-token"}
    )
    assert response.status_code == 403
    assert response.json()["error"] == "firebase_identity_not_linked"


def test_unverified_email_is_denied_for_mapped_firebase_uid(monkeypatch):
    monkeypatch.delenv("PRAVIDHI_API_KEY", raising=False)
    monkeypatch.setenv(
        "PRAVIDHI_FIREBASE_USER_MAPPINGS_JSON",
        json.dumps({
            "uid-approved": {
                "account_id": "acct-001",
                "tenant_id": "tenant-alpha",
                "role": "operator",
            }
        }),
    )
    monkeypatch.setattr(
        firebase_auth,
        "verify_firebase_id_token",
        lambda token: {"uid": "uid-approved", "email": "user@example.com", "email_verified": False},
    )
    response = TestClient(make_app()).get(
        "/api/whoami", headers={"Authorization": "Bearer valid-firebase-token"}
    )
    assert response.status_code == 403
    assert response.json()["error"] == "verified_email_required"


def test_malformed_mapping_fails_closed(monkeypatch):
    monkeypatch.delenv("PRAVIDHI_API_KEY", raising=False)
    monkeypatch.setenv("PRAVIDHI_FIREBASE_USER_MAPPINGS_JSON", "not-json")
    monkeypatch.setattr(
        firebase_auth,
        "verify_firebase_id_token",
        lambda token: {"uid": "uid-approved", "email": "verified@example.com", "email_verified": True},
    )
    response = TestClient(make_app()).get(
        "/api/whoami", headers={"Authorization": "Bearer valid-firebase-token"}
    )
    assert response.status_code == 503
    assert response.json()["error"] == "firebase_mapping_misconfigured"


def test_invalid_api_key_role_is_rejected(monkeypatch):
    monkeypatch.setenv("PRAVIDHI_API_KEY", "server-key")
    monkeypatch.setenv("PRAVIDHI_API_ROLE", "root")
    monkeypatch.delenv("PRAVIDHI_FIREBASE_USER_MAPPINGS_JSON", raising=False)
    response = TestClient(make_app()).get(
        "/api/whoami", headers={"Authorization": "Bearer server-key"}
    )
    assert response.status_code == 401


def test_invalid_trusted_header_role_is_rejected(monkeypatch):
    monkeypatch.setenv("PRAVIDHI_API_KEY", "server-key")
    monkeypatch.setenv("PRAVIDHI_TRUST_IDENTITY_HEADERS", "true")
    monkeypatch.setenv("PRAVIDHI_FIREBASE_USER_MAPPINGS_JSON", "")
    response = TestClient(make_app()).get(
        "/api/whoami",
        headers={
            "Authorization": "Bearer server-key",
            "X-Pravidhi-Role": "superuser",
        },
    )
    assert response.status_code == 401


def test_unknown_mapping_role_fails_closed(monkeypatch):
    monkeypatch.delenv("PRAVIDHI_API_KEY", raising=False)
    monkeypatch.setenv(
        "PRAVIDHI_FIREBASE_USER_MAPPINGS_JSON",
        json.dumps({
            "uid-approved": {
                "account_id": "acct-001",
                "tenant_id": "tenant-alpha",
                "role": "superuser",
            }
        }),
    )
    monkeypatch.setattr(
        firebase_auth,
        "verify_firebase_id_token",
        lambda token: {"uid": "uid-approved", "email": None, "email_verified": False},
    )
    response = TestClient(make_app()).get(
        "/api/whoami", headers={"Authorization": "Bearer valid-firebase-token"}
    )
    assert response.status_code == 503
    assert response.json()["error"] == "firebase_mapping_misconfigured"
