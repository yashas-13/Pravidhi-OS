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

## Required backend work before Firebase can replace or complement Keycloak for protected APIs

1. Add an explicit token-validation boundary that accepts a Firebase ID token only on designated app API routes.
2. Verify the token server-side with Firebase Admin SDK (signature, issuer, audience/project ID, expiry, subject, and revocation policy as required).
3. Resolve the user to a server-controlled Pravidhi account and tenant. Never trust client-provided tenant IDs, roles, scopes, or admin flags.
4. Apply existing tenant isolation and RBAC on every protected operation. Firebase authentication alone must never grant `pravidhi.execute`, `pravidhi.admin`, agent execution, or approval authority.
5. Keep the existing Keycloak/OIDC validation for MCP OAuth/resource-server access. Do not accept a Firebase ID token as a Keycloak access token.
6. Add positive and negative tests: valid token, bad signature, wrong audience/issuer, expired/revoked token, unknown user, missing tenant mapping, cross-tenant ID, insufficient role/scope, and unauthenticated requests. Fail closed.
7. Test registration, email/password login, Google login/redirect, password reset, sign-out, and authorized-domain errors against the deployed origin.

## Validation status

The client module is added but browser-based end-to-end tests and backend Firebase ID-token validation are not claimed as complete. The backend token-exchange/identity-mapping design must be implemented and tested before enabling Firebase identity for protected application APIs.
