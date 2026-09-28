# OAuth and Keycloak

Pravidhi OS uses Keycloak as the authorization server and the MCP server as the OAuth resource server.

## Components

```
ChatGPT
  │
  │ Authorization Code + PKCE S256
  ▼
Keycloak / OIDC
  │
  │ signed access token
  ▼
Pravidhi MCP
  │
  │ issuer/audience/signature/expiry/scope validation
  ▼
Pravidhi Control Plane
```

## Authorization server

```
https://mcp.pravidhisolutions.in/auth/realms/pravidhi
```

OIDC discovery:

```
https://mcp.pravidhisolutions.in/auth/realms/pravidhi/.well-known/openid-configuration
```

JWKS:

```
https://mcp.pravidhisolutions.in/auth/realms/pravidhi/protocol/openid-connect/certs
```

## ChatGPT client

The reference client is:

```
https://chatgpt.com/oauth/client.json
```

Redirect URI:

```
https://chatgpt.com/connector_platform_oauth_redirect
```

The client is configured for standard authorization code flow and PKCE S256.

## Scopes

| Scope | Intended use |
|---|---|
| `pravidhi.read` | Authenticated read-only operations |
| `pravidhi.execute` | Authorized execution operations |
| `pravidhi.admin` | Administrative operations |

Standard OIDC scopes such as `openid` and `offline_access` must also be supported according to the client authorization request.

## Roles

The reference realm defines:

- `pravidhi-user`
- `pravidhi-operator`
- `pravidhi-admin`

A scope is not a substitute for application authorization. The control plane must apply tenant and RBAC policy after token validation.

## Resource audience

Pravidhi access tokens are audience-bound to:

```
https://mcp.pravidhisolutions.in
```

The MCP resource server validates:

- JWT algorithm
- signing key / JWKS `kid`
- signature
- issuer
- audience
- `exp`
- `nbf`
- required scopes

## Protected-resource metadata

```
https://mcp.pravidhisolutions.in/.well-known/oauth-protected-resource
```

The metadata points clients to the Pravidhi Keycloak realm and advertises the supported Pravidhi scopes.

## Fail-closed behavior

Protected MCP tools must not execute when:

- Authorization is absent
- token signature is invalid
- issuer is incorrect
- audience is incorrect
- token is expired/not-yet-valid
- required scope is missing
- downstream tenant/RBAC checks fail
- an approval required by policy is absent or invalid

For OAuth-protected MCP tools, the server can return the MCP `mcp/www_authenticate` challenge metadata referencing the protected-resource metadata endpoint.

## Operations

Never commit:

- Keycloak admin passwords
- database passwords
- client secrets
- private signing keys
- access/refresh tokens

Production secrets belong in a secret manager or protected deployment environment.
