"""Trusted server-side mapping from Firebase UIDs to Pravidhi principals.

The mapping is provisioned by an operator in deployment configuration. Client
claims, email addresses, and Firebase custom claims never select an account,
tenant, or role.
"""
from __future__ import annotations

import json
import os
from typing import Any


_ALLOWED_ROLES = {"viewer", "user", "operator", "admin"}


class FirebaseMappingConfigurationError(ValueError):
    """The trusted server-side identity mapping is malformed."""


def resolve_firebase_principal(uid: str) -> dict[str, Any] | None:
    """Return the explicitly provisioned account binding for a verified UID."""
    raw = os.getenv("PRAVIDHI_FIREBASE_USER_MAPPINGS_JSON", "").strip()
    if not raw:
        return None
    try:
        mappings = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise FirebaseMappingConfigurationError(
            "PRAVIDHI_FIREBASE_USER_MAPPINGS_JSON must be valid JSON"
        ) from exc
    if not isinstance(mappings, dict):
        raise FirebaseMappingConfigurationError("Firebase mappings must be a JSON object")
    record = mappings.get(uid)
    if record is None:
        return None
    if not isinstance(record, dict):
        raise FirebaseMappingConfigurationError("Each Firebase UID mapping must be an object")

    account_id = record.get("account_id")
    tenant_id = record.get("tenant_id")
    role = record.get("role")
    if not all(isinstance(v, str) and v.strip() for v in (account_id, tenant_id, role)):
        raise FirebaseMappingConfigurationError(
            "Each mapping requires non-empty account_id, tenant_id, and role"
        )
    if role not in _ALLOWED_ROLES:
        raise FirebaseMappingConfigurationError("Mapping contains an unsupported role")
    if account_id.strip() != account_id or tenant_id.strip() != tenant_id or role.strip() != role:
        raise FirebaseMappingConfigurationError("Mapping identifiers and roles must not contain surrounding whitespace")
    return {
        "subject": f"firebase:{uid}",
        "account_id": account_id.strip(),
        "tenant_id": tenant_id.strip(),
        "role": role,
        "auth_method": "firebase",
    }
