# OpenAI MCP Submission Guide

This document describes the Pravidhi OS submission workflow for the OpenAI Platform.

## Production MCP endpoint

```
https://mcp.pravidhisolutions.in/mcp
```

The endpoint must remain publicly reachable over HTTPS for platform scanning.

## Domain verification

OpenAI provides a challenge token in the submission form. The deployment must expose that exact token at:

```
https://mcp.pravidhisolutions.in/.well-known/openai-apps-challenge
```

The token is deployment state and must not be committed to Git.

## Submission JSON

The repository contains:

```
chatgpt-app-submission.json
```

Keep the submission file synchronized with the **actual live MCP tools and schemas**. Do not advertise planned or unverified privileged tools.

## OAuth

The current authorization server is:

```
https://mcp.pravidhisolutions.in/auth/realms/pravidhi
```

The resource server advertises protected-resource metadata at:

```
https://mcp.pravidhisolutions.in/.well-known/oauth-protected-resource
```

Current scopes:

- `pravidhi.read`
- `pravidhi.execute`
- `pravidhi.admin`

The ChatGPT OAuth client uses:

- client ID: `https://chatgpt.com/oauth/client.json`
- redirect URI: `https://chatgpt.com/connector_platform_oauth_redirect`
- PKCE: S256
- authorization-code flow

The authorization server also needs to accept standard OIDC scopes requested by the client, including `openid` and `offline_access`.

## Tool review

Before submission:

1. Connect the MCP server.
2. Complete domain verification.
3. Complete OAuth authorization.
4. Run the MCP tools scan.
5. Compare every scanned tool with `chatgpt-app-submission.json`.
6. Verify annotations.
7. Run positive and negative tests.
8. Review privacy, terms and support URLs.
9. Submit only when the live surface and submission file agree.

## Security requirements

Never include in the submission package:

- access tokens
- refresh tokens
- client secrets
- private keys
- database passwords
- production environment files
- customer data
- approval credentials

## Current verified deployment

The current deployment has:

- public HTTPS MCP transport
- protected-resource metadata
- Keycloak/OIDC authorization
- JWT/JWKS validation at the MCP resource server
- protected `pravidhi_identity` using `pravidhi.read`
- public health/capability tools
- fail-closed OAuth challenge behavior for protected tools

Privileged per-scope MCP tool expansion remains deployment-gated until a live tools scan confirms those tools.
