"""Commercial security boundary for the Pravidhi API."""
from __future__ import annotations

import hashlib
import hmac
import os
import secrets
from dataclasses import dataclass
from typing import Iterable

from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

PUBLIC_EXACT = {
    "/health", "/docs", "/redoc", "/openapi.json", "/auth/providers",
    "/auth/firebase/verify", "/api/agents/register", "/api/agents/pair",
    "/api/agents/pairing/start",
}

# Every protected route that performs an administrative action must enforce
# the role vocabulary centrally or with an equivalent route-level policy.
# Keep this set aligned with gateway/firebase_mapping.py and SECURITY_MODEL.md.
_ALLOWED_PRINCIPAL_ROLES = {"viewer", "user", "operator", "admin"}
PUBLIC_PREFIXES = ("/static/", "/.well-known/")


def is_agent_heartbeat_path(path: str) -> bool:
    """Agent heartbeat is self-authenticated by its per-agent bearer token."""
    parts = path.strip("/").split("/")
    return len(parts) == 4 and parts[:2] == ["api", "agents"] and parts[3] == "heartbeat"


def is_agent_task_path(path: str) -> bool:
    """Worker task polling/result routes use the per-agent bearer token."""
    parts = path.strip("/").split("/")
    return (
        len(parts) == 5 and parts[:2] == ["api", "agents"]
        and parts[3] == "tasks" and parts[4] in {"next", "result"}
    ) or (
        len(parts) == 6 and parts[:2] == ["api", "agents"]
        and parts[3] == "tasks" and parts[5] == "result"
    )


@dataclass(frozen=True)
class Principal:
    subject: str
    role: str
    tenant_id: str
    account_id: str = ""
    auth_method: str = "api_key"


def _configured_key() -> str:
    return os.getenv("PRAVIDHI_API_KEY", "").strip()


def _constant_time_equal(left: str, right: str) -> bool:
    return hmac.compare_digest(hashlib.sha256(left.encode()).digest(), hashlib.sha256(right.encode()).digest())


def extract_bearer(request: Request) -> str:
    header = request.headers.get("authorization", "")
    scheme, _, token = header.partition(" ")
    return token.strip() if scheme.lower() == "bearer" and token.strip() else ""


def is_public_path(path: str) -> bool:
    return path in PUBLIC_EXACT or any(path.startswith(p) for p in PUBLIC_PREFIXES)


def principal_from_request(request: Request) -> Principal | None:
    token, expected = extract_bearer(request), _configured_key()
    if not token or not expected or not _constant_time_equal(token, expected):
        return None
    trusted_headers = os.getenv("PRAVIDHI_TRUST_IDENTITY_HEADERS", "").lower() == "true"
    role = request.headers.get("x-pravidhi-role", "operator") if trusted_headers else os.getenv("PRAVIDHI_API_ROLE", "operator")
    if role not in _ALLOWED_PRINCIPAL_ROLES:
        return None
    return Principal(
        subject=request.headers.get("x-pravidhi-subject", "api-key-client") if trusted_headers else "api-key-client",
        role=role,
        tenant_id=request.headers.get("x-pravidhi-tenant", os.getenv("PRAVIDHI_TENANT_ID", "default")) if trusted_headers else os.getenv("PRAVIDHI_TENANT_ID", "default"),
        account_id="api-key-client",
        auth_method="api_key",
    )


def _firebase_principal(token: str) -> tuple[Principal | None, JSONResponse | None]:
    """Verify Firebase token and resolve UID only through server-owned mapping."""
    from gateway.firebase_mapping import (
        FirebaseMappingConfigurationError,
        resolve_firebase_principal,
    )
    from gateway.firebase_auth import (
        FirebaseAuthNotConfigured,
        FirebaseTokenInvalid,
        verify_firebase_id_token,
    )

    try:
        claims = verify_firebase_id_token(token)
        mapped = resolve_firebase_principal(claims["uid"])
    except FirebaseAuthNotConfigured:
        return None, JSONResponse(status_code=503, content={"error": "firebase_auth_not_configured"})
    except FirebaseTokenInvalid:
        return None, JSONResponse(
            status_code=401,
            content={"error": "invalid_bearer_token"},
            headers={"WWW-Authenticate": "Bearer"},
        )
    except FirebaseMappingConfigurationError:
        return None, JSONResponse(status_code=503, content={"error": "firebase_mapping_misconfigured"})

    if mapped is None:
        return None, JSONResponse(status_code=403, content={"error": "firebase_identity_not_linked"})
    if mapped.get("role") not in _ALLOWED_PRINCIPAL_ROLES:
        return None, JSONResponse(status_code=503, content={"error": "firebase_mapping_misconfigured"})
    if claims.get("email") and not claims.get("email_verified", False):
        return None, JSONResponse(status_code=403, content={"error": "verified_email_required"})

    return Principal(
        subject=mapped["subject"],
        role=mapped["role"],
        tenant_id=mapped["tenant_id"],
        account_id=mapped["account_id"],
        auth_method="firebase",
    ), None


class CommercialSecurityMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, protected_prefixes: Iterable[str] = ("/api/", "/v1/")):
        super().__init__(app)
        self.protected_prefixes = tuple(protected_prefixes)

    async def dispatch(self, request: Request, call_next):
        path = request.url.path
        if (
            is_public_path(path) or is_agent_heartbeat_path(path)
            or is_agent_task_path(path)
            or not any(path.startswith(p) for p in self.protected_prefixes)
        ):
            return await call_next(request)
        if os.getenv("PRAVIDHI_ALLOW_UNAUTHENTICATED_DEV", "").lower() == "true":
            return await call_next(request)

        token = extract_bearer(request)
        principal = principal_from_request(request)
        mapping_configured = bool(os.getenv("PRAVIDHI_FIREBASE_USER_MAPPINGS_JSON", "").strip())

        # API-key authentication remains supported. Only attempt Firebase when
        # that bearer did not match the API key and an explicit mapping exists.
        if principal is None and token and mapping_configured:
            principal, error_response = _firebase_principal(token)
            if error_response is not None:
                return error_response

        if principal is None:
            if not _configured_key() and not mapping_configured:
                return JSONResponse(
                    status_code=503,
                    content={
                        "error": "security_not_configured",
                        "message": "Privileged API access is disabled until an API key or trusted Firebase mapping is configured.",
                    },
                )
            return JSONResponse(
                status_code=401,
                content={"error": "authentication_required", "message": "A valid API key or linked Firebase identity is required."},
                headers={"WWW-Authenticate": "Bearer"},
            )

        request.state.principal = principal
        request.state.request_id = request.headers.get("x-request-id", secrets.token_hex(16))
        response = await call_next(request)
        response.headers["X-Request-ID"] = request.state.request_id
        return response
