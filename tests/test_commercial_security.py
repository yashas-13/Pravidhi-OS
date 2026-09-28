import os
from fastapi import FastAPI
from fastapi.testclient import TestClient

from gateway.security import CommercialSecurityMiddleware


def make_app():
    app = FastAPI()
    app.add_middleware(CommercialSecurityMiddleware)

    @app.get('/health')
    def health():
        return {'status': 'ok'}

    @app.get('/api/protected')
    def protected():
        return {'status': 'authorized'}

    return app


def test_public_health_remains_public(monkeypatch):
    monkeypatch.delenv('PRAVIDHI_API_KEY', raising=False)
    client = TestClient(make_app())
    assert client.get('/health').status_code == 200


def test_privileged_api_fails_closed_without_key(monkeypatch):
    monkeypatch.delenv('PRAVIDHI_API_KEY', raising=False)
    monkeypatch.delenv('PRAVIDHI_ALLOW_UNAUTHENTICATED_DEV', raising=False)
    client = TestClient(make_app())
    response = client.get('/api/protected')
    assert response.status_code == 503
    assert response.json()['error'] == 'security_not_configured'


def test_privileged_api_rejects_bad_key(monkeypatch):
    monkeypatch.setenv('PRAVIDHI_API_KEY', 'correct-secret')
    client = TestClient(make_app())
    response = client.get('/api/protected', headers={'Authorization': 'Bearer wrong-secret'})
    assert response.status_code == 401


def test_privileged_api_accepts_configured_key(monkeypatch):
    monkeypatch.setenv('PRAVIDHI_API_KEY', 'correct-secret')
    client = TestClient(make_app())
    response = client.get('/api/protected', headers={'Authorization': 'Bearer correct-secret', 'X-Pravidhi-Tenant': 'demo'})
    assert response.status_code == 200
    assert response.json()['status'] == 'authorized'
