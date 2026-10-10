# Firebase Authentication integration

## Project

- Firebase project ID: `pravidhi-os`
- Web app ID: `1:314825143687:web:1963c7fa4ce4c276eccf22`
- Firebase Auth domain: `pravidhi-os.firebaseapp.com`
- Client SDK config lives in `dashboard/firebase-auth.js`. Firebase web config/API keys are public client identifiers; they are not server secrets. Enforce access with Firebase Security Rules and backend authorization.

## Current client behavior

The static dashboard uses browser ES modules from Google's Firebase CDN (it does not currently have a frontend bundler, so `npm install firebase` alone would not wire the SDK into its classic script). The module adds:
- Email/password registration and sign-in
- Google popup sign-in
- Password-reset email
- Firebase sign-out and auth-state display

The existing Keycloak sign-in is deliberately retained. A successful Firebase sign-in does **not** authorize protected dashboard API requests and does not grant a tenant, role, scope, or administrative permission.

## Console configuration

In Firebase Console → Authentication → Settings → Authorized domains, allow only actual deployment origins:
- `mcp.pravidhisolutions.in` (if the dashboard is served from this host)
- `pravidhisolutions.in` (only if the dashboard is also served from the apex domain)
- `localhost` for local development, if needed

Do not add wildcard domains. Confirm the deployed dashboard origin before editing the allowlist. Google OAuth provider must have a support email selected and its provider enabled. Firebase-managed Google OAuth redirects use the Firebase auth domain; custom domain setups may require the documented redirect URI shown by Firebase Console.

## Gemini model access

Pravidhi OS already defines the Gemini OpenAI-compatible provider in `engine/provider_router.py`:
- Provider: `gemini`
- Model: `gemini-2.5-flash`
- Base URL: `https://generativelanguage.googleapis.com/v1beta/openai`
- Server environment variable: `GEMINI_API_KEY`

To enable Gemini, create a key in Google AI Studio and set `GEMINI_API_KEY` in the environment of the Pravidhi API process (or the deployment's secret manager). Restart/redeploy that process after updating its environment. Never put the Gemini key in browser code, Firebase config, a client request, or source control. Firebase sign-in does not create a Gemini API key or billing entitlement. Use the app's model selector to choose `gemini-2.5-flash` once the server has the key configured. If the selector does not list the model, check the models endpoint and provider discovery/configuration; do not expose secret values in logs.

The Gemini API key is separate from Firebase Admin credentials. `FIREBASE_PROJECT_ID` and Admin Application Default Credentials are for verifying Firebase identity; `GEMINI_API_KEY` is for Gemini inference.

## Backend identity verification and authorization boundary

The API exposes `POST /auth/firebase/verify` for verifying Firebase end-user identity. Set `FIREBASE_PROJECT_ID=pravidhi-os` and configure Firebase Admin SDK Application Default Credentials on the server (preferred) or a server-side `GOOGLE_APPLICATION_CREDENTIALS` path. Never commit a service-account JSON file or expose Admin credentials to the browser. The endpoint verifies the token through Firebase Admin SDK with revocation checking and returns only verified UID/email fields. It fails closed if Admin credentials are unavailable or the token is invalid.

**This is not a Pravidhi API session exchange.** Firebase identity does not grant a tenant, role, scopes, or execution permissions. Protected `/api/*` and `/v1/*` operations retain the existing Pravidhi API credential boundary; MCP continues to use Keycloak OIDC. Do not send Firebase ID tokens to MCP endpoints. Before allowing Firebase-only access to protected features, implement server-owned Firebase UID → existing Pravidhi account/tenant mapping and enforce server-side RBAC/scopes for every operation. Unknown identities must be denied by default.

## Required validation before production

- Run the Python CI suite including `tests/test_firebase_auth.py`.
- Browser-test registration, email/password sign-in, Google sign-in, password reset, and sign-out on the deployed HTTPS origin.
- Add the exact dashboard host to Firebase Authentication → Settings → Authorized domains and verify the Google provider support email.
- Run negative tests for wrong-project/audience, expired/revoked tokens, missing Admin credentials, unlinked users, cross-tenant access, and insufficient roles.
- Verify Gemini by making a server-side request to `gemini-2.5-flash` with a valid server-side `GEMINI_API_KEY`; test missing/invalid key handling without printing the key.
- Keep Keycloak and the existing tenant/RBAC boundary in place until the mapping and migration tests are reviewed.
