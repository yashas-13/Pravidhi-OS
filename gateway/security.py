"""Commercial security boundary for the Pravidhi API."""
from __future__ import annotations
import hashlib, hmac, os, secrets
from dataclasses import dataclass
from typing import Iterable
from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

PUBLIC_EXACT = {'/health','/docs','/redoc','/openapi.json','/auth/providers'}
PUBLIC_PREFIXES = ('/static/','/.well-known/')

@dataclass(frozen=True)
class Principal:
    subject: str
    role: str
    tenant_id: str

def _configured_key() -> str:
    return os.getenv('PRAVIDHI_API_KEY', '').strip()

def _constant_time_equal(left: str, right: str) -> bool:
    return hmac.compare_digest(hashlib.sha256(left.encode()).digest(), hashlib.sha256(right.encode()).digest())

def extract_bearer(request: Request) -> str:
    header = request.headers.get('authorization', '')
    scheme, _, token = header.partition(' ')
    return token.strip() if scheme.lower() == 'bearer' and token.strip() else ''

def is_public_path(path: str) -> bool:
    return path in PUBLIC_EXACT or any(path.startswith(p) for p in PUBLIC_PREFIXES)

def principal_from_request(request: Request) -> Principal | None:
    token, expected = extract_bearer(request), _configured_key()
    if not token or not expected or not _constant_time_equal(token, expected):
        return None
    return Principal(subject=request.headers.get('x-pravidhi-subject', 'api-key-client'), role=request.headers.get('x-pravidhi-role', 'operator'), tenant_id=request.headers.get('x-pravidhi-tenant', os.getenv('PRAVIDHI_TENANT_ID', 'default')))

class CommercialSecurityMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, protected_prefixes: Iterable[str] = ('/api/','/v1/')):
        super().__init__(app)
        self.protected_prefixes = tuple(protected_prefixes)

    async def dispatch(self, request: Request, call_next):
        path = request.url.path
        if is_public_path(path) or not any(path.startswith(p) for p in self.protected_prefixes):
            return await call_next(request)
        if os.getenv('PRAVIDHI_ALLOW_UNAUTHENTICATED_DEV', '').lower() == 'true':
            return await call_next(request)
        if not _configured_key():
            return JSONResponse(status_code=503, content={'error':'security_not_configured','message':'Privileged API access is disabled until PRAVIDHI_API_KEY is configured.'})
        principal = principal_from_request(request)
        if principal is None:
            return JSONResponse(status_code=401, content={'error':'authentication_required','message':'Bearer authentication is required for privileged Pravidhi operations.'}, headers={'WWW-Authenticate':'Bearer'})
        request.state.principal = principal
        request.state.request_id = request.headers.get('x-request-id', secrets.token_hex(16))
        response = await call_next(request)
        response.headers['X-Request-ID'] = request.state.request_id
        return response
