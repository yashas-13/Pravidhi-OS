"""Fail-closed Firebase ID-token verification for Pravidhi end-user identity.

This module verifies identity only. It does not assign tenant, role, scopes, or
execution permissions. Those remain controlled by the existing Pravidhi
authorization system.
"""
from __future__ import annotations

import os
from functools import lru_cache
from typing import Any


class FirebaseAuthNotConfigured(RuntimeError):
    """Firebase Admin credentials or SDK are not configured."""


class FirebaseTokenInvalid(ValueError):
    """Firebase ID token failed verification."""


@lru_cache(maxsize=1)
def _firebase_app():
    try:
        import firebase_admin
        from firebase_admin import credentials
    except ImportError as exc:
        raise FirebaseAuthNotConfigured("Install firebase-admin to enable verification") from exc

    project_id = os.getenv("FIREBASE_PROJECT_ID", "").strip()
    if not project_id:
        raise FirebaseAuthNotConfigured("FIREBASE_PROJECT_ID is required")

    try:
        # Prefer Application Default Credentials (workload identity in cloud,
        # or GOOGLE_APPLICATION_CREDENTIALS pointing to a server-side file).
        # Never place service-account credentials in the repository/client.
        try:
            return firebase_admin.get_app()
        except ValueError:
            return firebase_admin.initialize_app(options={"projectId": project_id})
    except Exception as exc:
        raise FirebaseAuthNotConfigured("Firebase Admin credentials are unavailable") from exc


def verify_firebase_id_token(token: str) -> dict[str, Any]:
    """Verify signature, issuer/audience/project, expiry and revocation status."""
    if not token or len(token) > 16_384:
        raise FirebaseTokenInvalid("Malformed token")

    try:
        from firebase_admin import auth
        decoded = auth.verify_id_token(token, app=_firebase_app(), check_revoked=True)
    except FirebaseAuthNotConfigured:
        raise
    except Exception as exc:
        raise FirebaseTokenInvalid("Firebase ID token rejected") from exc

    uid = decoded.get("uid") or decoded.get("sub")
    if not isinstance(uid, str) or not uid:
        raise FirebaseTokenInvalid("Token has no Firebase UID")

    # Only return a small allowlist of verified claims. Never trust tenant/role
    # custom claims here; identity-to-tenant mapping must be server-owned.
    email = decoded.get("email")
    return {
        "uid": uid,
        "email": email if isinstance(email, str) else None,
        "email_verified": decoded.get("email_verified") is True,
    }
