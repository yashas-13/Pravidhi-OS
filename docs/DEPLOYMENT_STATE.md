# Deployment State

This document records the currently known production integration state without storing secrets.

## Public endpoints

| Endpoint | Purpose |
|---|---|
| `https://mcp.pravidhisolutions.in/mcp` | MCP Streamable HTTP |
| `https://mcp.pravidhisolutions.in/mcp-health` | MCP health |
| `https://mcp.pravidhisolutions.in/.well-known/oauth-protected-resource` | OAuth protected-resource metadata |
| `https://mcp.pravidhisolutions.in/.well-known/openai-apps-challenge` | OpenAI domain verification challenge |
| `https://mcp.pravidhisolutions.in/auth/realms/pravidhi` | Keycloak OIDC realm |

## Transport

The public MCP hostname terminates TLS at Nginx and proxies MCP traffic to the local MCP service.

The MCP service is intentionally not exposed directly on a public interface.

## Authentication

Keycloak is the authorization server.

The MCP resource server validates JWT access tokens against the realm JWKS and checks issuer, resource audience, time validity and scopes.

## Control plane

The control plane contains the reference tenant/RBAC/approval/audit architecture.

The MCP layer is intended to pass authenticated context into that existing control plane rather than maintain a separate authorization implementation.

## Current live MCP surface

Verified public/authenticated capabilities:

- `pravidhi_health`
- `pravidhi_capabilities`
- `pravidhi_identity`

The protected identity capability requires `pravidhi.read`.

## Privileged capability rollout

The intended privileged MCP contract uses:

- `pravidhi.read`
- `pravidhi.execute`
- `pravidhi.admin`

The production documentation must only advertise an individual privileged tool after the live MCP tools scan confirms that it is deployed and its schema/annotations match the submission contract.

## Domain verification

The OpenAI challenge token is deployment state and is intentionally excluded from Git.

## Change management

When changing MCP tools:

1. update implementation
2. update tool annotations
3. update submission JSON
4. run MCP initialize/tools/list
5. test authentication
6. test authorization
7. test approval gates
8. test tenant isolation
9. update documentation
10. scan the live server again

Never document an aspirational tool as a production capability.
