# Firebase Authentication integration

## Project

- Firebase project ID: `pravidhi-os`
- Web app ID: `1:314825143687:web:1963c7fa4ce4c276eccf22`
- Firebase Auth domain: `pravidhi-os.firebaseapp.com`
- Client SDK config lives in `dashboard/firebase-auth.js`. Firebase web config/API keys are public client identifiers; they are not server secrets. Enforce access with backend authorization.

## Current client behavior

The static dashboard uses browser ES modules from Google's Firebase CDN (it does not currently have a frontend bundler). The module adds email/password registration and sign-in, Google popup sign-in, password reset, and sign-out.

The existing Keycloak sign-in remains in place for MCP/OIDC. Firebase ID tokens are never treated as Keycloak tokens.

## Console configuration

In Firebase Console → Authentication → Settings → Authorized domains, allow only actual deployment origins:
- `mcp.pravidhisolutions.in` (if the dashboard is served from this host)
- `pravidhisolutions.in` (only if the dashboard is also served from the apex domain)
- `localhost` for local development, if needed

Do not add wildcard domains. Confirm the deployed dashboard origin before editing the allowlist. Google OAuth provider must have a support email selected and its provider enabled.

## Trusted Firebase UID → Pravidhi account/tenant mapping

Protected `/api/*` and `/v1/*` requests may authenticate with a Firebase ID token **only when** its verified UID has an explicit server-side mapping. The mapping resolver is in `gateway/firebase_mapping.py`; the commercial middleware verifies the Firebase token (including revocation checking) and resolves the UID to a Pravidhi principal before setting `request.state.principal`.

Configure `PRAVIDHI_FIREBASE_USER_MAPPINGS_JSON` in the API deployment's secret/config store. Do not put real mappings in source control. The JSON object is keyed by the exact Firebase UID and each value must contain:
- `account_id`: an existing Pravidhi account identifier
- `tenant_id`: the existing tenant identifier that account belongs to
- `role`: one of `viewer`, `user`, `operator`, `admin`

Example shape only (replace placeholders; this is not a real mapping):

```json
{
  "FIREBASE_UID_FROM_AUTHENTICATION": {
    "account_id": "EXISTING_ACCOUNT_ID",
    "tenant_id": "EXISTING_TENANT_ID",
    "role": "operator"
  }
}
```

Provision mappings only after an administrator independently verifies the Firebase UID and the account/tenant association. Do not auto-link by email, display name, user-supplied tenant headers, or Firebase custom claims. Never let the client submit or change `account_id`, `tenant_id`, or `role`. Email-bearing Firebase identities must have `email_verified=true`. Unmapped UIDs receive 403; malformed mapping configuration fails closed with 503. Existing API-key authentication remains supported.

**Important:** the middleware now applies a conservative baseline role policy: `viewer`/`user` can use read methods and the explicitly allowlisted chat/search POST endpoints; other state-changing requests require `operator` or `admin`; paths containing `admin`, `security`, `tenants`, `users`, or `billing` require `admin`. This is not complete object-level authorization. Every sensitive handler must still enforce tenant ownership and resource-level permissions, and agent routes with their own bearer tokens must be audited separately. Only grant `operator` or `admin` to users explicitly approved for those operations. Keep MCP on Keycloak OIDC until a separate, reviewed federation design is implemented.

## Gemini model access

Pravidhi OS defines the Gemini OpenAI-compatible provider:
- Provider: `gemini`
- Model: `gemini-2.5-flash`
- Base URL: `https://generativelanguage.googleapis.com/v1beta/openai`
- Server environment variable: `GEMINI_API_KEY`

Create a key in Google AI Studio and inject `GEMINI_API_KEY` into the API process environment or deployment secret manager, then restart/redeploy. Never put the Gemini key in browser code, Firebase config, client requests, or source control. Firebase sign-in does not create a Gemini key or billing entitlement. Use the model selector after the server has the key configured.

The Gemini key is separate from Firebase Admin credentials. `FIREBASE_PROJECT_ID` and Admin Application Default Credentials verify Firebase identity; `GEMINI_API_KEY` enables Gemini inference.

## Validation before production

- Run Python CI, including `tests/test_firebase_auth.py` and `tests/test_firebase_mapping.py`.
- Test mapped and unmapped UIDs, malformed mapping JSON, unverified email, wrong-project/audience, expired/revoked tokens, and missing Admin credentials.
- Test cross-tenant isolation and insufficient roles for every protected route, not only the identity endpoint.
- Browser-test registration, email/password sign-in, Google sign-in, password reset, and sign-out on the deployed HTTPS origin.
- Verify Firebase authorized domains and Google provider support email in Firebase Console.
- Verify Gemini with a server-side request using a valid `GEMINI_API_KEY`; test missing/invalid key handling without logging the key.
- Do not merge/deploy until CI and deployment-specific tests pass.
