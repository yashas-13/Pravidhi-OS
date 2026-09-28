# Pravidhi OS Security Boundary

## Trust model

```text
AI client
   |
   | intent
   v
Pravidhi control plane
   |
   +-- identity
   +-- tenant
   +-- RBAC
   +-- capability
   +-- policy
   +-- approval
   +-- rate limit
   +-- audit
   |
   v
constrained agent runtime
   |
   v
authorized resource
```

## Rules

- Model output is never authorization.
- Every privileged operation requires an authenticated principal.
- Tenant identity must come from trusted identity metadata, not arbitrary request parameters.
- Filesystem operations must remain inside a tenant workspace after canonicalization.
- Shell execution must use an allowlist or sandbox; unrestricted model-generated shell is not a commercial capability.
- High-risk operations require explicit approval.
- Audit records must contain a correlation/request identifier.
- Production deployments must fail closed when security configuration is missing.

## Public API

Public: `/health`, `/docs`, `/redoc`, `/openapi.json`, `/auth/providers`, static and `.well-known` resources.

Privileged: `/api/*` and `/v1/*`. The reference gateway requires a Bearer token when `PRAVIDHI_API_KEY` is configured. If it is missing, privileged access returns `503 security_not_configured`.

Enterprise deployments should place a verified OIDC/JWT gateway in front of Pravidhi and pass only trusted identity claims to the runtime.

## Production requirements

- HTTPS only
- secrets outside source control
- API key rotation
- least-privilege service accounts
- separate development and production tenants
- append-only audit export for high assurance deployments
- container/VM isolation for hostile or multi-tenant execution
