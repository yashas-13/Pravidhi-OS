# Pravidhi Commander

**Pravidh Commander** is the branded Remote MCP control surface for the Pravidhi control plane. It provides a secure dashboard for authenticated device visibility, usage, account settings, and MCP connectivity at `https://mcp.pravidhisolutions.in/dashboard/`.

> The underlying control-plane architecture remains Pravidhi OS; **Pravidh Commander** is the user-facing product/dashboard name.


**Pravidhi OS** is a security-focused agent control plane for supervised AI-assisted operations on infrastructure and authorized computing resources.

It provides a policy boundary between an AI client and the systems the AI is allowed to operate. The architecture is built around **authentication, tenant isolation, RBAC, capability controls, approval gates, constrained execution, and auditability** rather than unrestricted machine access.

> **Security boundary:** Pravidhi OS is intended only for systems, accounts, networks, applications, and data that the operator is authorized to administer.

## What it does

Pravidhi OS can provide a unified control workflow for:

- 🔐 OIDC/OAuth-based identity and token validation
- 👥 Role-based access control (RBAC)
- 🏢 Tenant/workspace isolation
- 🛂 Per-capability authorization
- ✅ Human approval gates for consequential operations
- 🖥️ Supervised terminal and filesystem operations
- 🤖 Agent execution and execution-status tracking
- 🧾 Structured audit events
- 🚦 Rate limiting and request correlation
- 🧱 Constrained/unprivileged execution
- 🔒 Fail-closed behavior when authentication, authorization, approval, or policy checks fail
- 🔌 Remote MCP integration for AI clients
- 📦 CLI/runtime integration for self-hosted deployments

## Architecture

```text
┌───────────────────────────────┐
│ AI client / ChatGPT / Codex   │
└───────────────┬───────────────┘
                │ OAuth 2.1 + PKCE
                ▼
┌───────────────────────────────┐
│ Keycloak / OIDC Authorization │
│ Server                        │
└───────────────┬───────────────┘
                │ access token
                ▼
┌───────────────────────────────┐
│ Pravidhi MCP Resource Server  │
│ issuer + audience + signature │
│ expiry + scope validation     │
└───────────────┬───────────────┘
                │ authenticated context
                ▼
┌───────────────────────────────┐
│ Pravidhi Control Plane        │
│ tenant + RBAC + policy        │
└───────────────┬───────────────┘
                │
        ┌───────┴────────┐
        ▼                ▼
┌──────────────┐  ┌──────────────┐
│ Approval Gate│  │ Audit Ledger │
└──────┬───────┘  └──────────────┘
       │
       ▼
┌───────────────────────────────┐
│ Constrained Agent / Executor  │
└───────────────┬───────────────┘
                ▼
┌───────────────────────────────┐
│ Authorized machine resources  │
└───────────────────────────────┘
```

The key design principle is:

```text
AI request
  → identity
  → tenant
  → capability
  → RBAC
  → policy
  → approval (when required)
  → constrained execution
  → audit
```

No layer is intended to bypass the layer below it.

## Pravidh Commander dashboard

The production dashboard is available at:

```text
https://mcp.pravidhisolutions.in/dashboard/
```

The dashboard is authenticated through the Pravidhi Keycloak realm and exposes tenant-scoped device, usage, billing-status, and settings views. Device and usage APIs are protected by `pravidhi.read`; no device registry data is intentionally exposed anonymously.

Dashboard source is maintained in [`dashboard/`](dashboard/).

## MCP integration

The production MCP endpoint is:

```text
https://mcp.pravidhisolutions.in/mcp
```

Public health endpoint:

```text
https://mcp.pravidhisolutions.in/mcp-health
```

The MCP server uses Streamable HTTP and exposes public discovery/health capabilities plus authenticated identity functionality. Privileged MCP capabilities are documented as deployment-gated until their live tool scan confirms availability.

### OAuth resource protection

Protected-resource metadata:

```text
https://mcp.pravidhisolutions.in/.well-known/oauth-protected-resource
```

Authorization server:

```text
https://mcp.pravidhisolutions.in/auth/realms/pravidhi
```

The current authorization model uses these scopes:

| Scope | Purpose |
|---|---|
| `pravidhi.read` | Read-only authenticated Pravidhi information |
| `pravidhi.execute` | Authorized execution capabilities |
| `pravidhi.admin` | Administrative capabilities |

The authorization server uses Keycloak with OIDC. The ChatGPT OAuth client is pre-registered using the stable ChatGPT client metadata identifier and uses PKCE S256.

**Important:** scopes are enforced at the authorization server and resource-server layers. A client must not treat possession of an MCP URL as authorization to perform privileged operations.

## Current MCP capabilities

The currently deployed public/authenticated tool surface includes:

| Tool | Authentication | Behavior |
|---|---|---|
| `pravidhi_health` | None | Public health/discovery |
| `pravidhi_capabilities` | None | Public capability information |
| `pravidhi_identity` | `pravidhi.read` | Authenticated identity/context |

Unauthenticated calls to protected tools fail closed with an OAuth resource-metadata challenge.

Future/privileged tools are designed to map individual capabilities to OAuth scopes and existing control-plane enforcement:

| Capability | Intended scope | Control |
|---|---|---|
| Tenant status | `pravidhi.read` | tenant + RBAC |
| Approval listing | `pravidhi.read` | tenant + RBAC |
| Audit events | `pravidhi.read` | tenant + RBAC |
| Filesystem read | `pravidhi.read` | tenant + policy |
| Approval creation | `pravidhi.execute` | operator/admin + gate |
| Terminal execution | `pravidhi.execute` | operator/admin + approval |
| Filesystem write | `pravidhi.execute` | operator/admin + approval |
| Approval resolution | `pravidhi.admin` | admin + policy |
| Execution status | `pravidhi.read` | tenant + RBAC |

The table describes the target contract; it is not a claim that every privileged MCP tool is currently live.

## Authentication and authorization

The reference deployment uses:

- Keycloak 26.x
- OIDC discovery
- OAuth 2.1-compatible authorization-code flow
- PKCE S256
- JWT access tokens
- JWKS signature validation
- exact issuer validation
- resource audience validation
- expiry and not-before validation
- scope enforcement
- tenant extraction
- realm/application roles
- fail-closed protected operations

The resource server validates the access token before invoking protected MCP tools.

### Role model

The reference realm defines:

- `pravidhi-user`
- `pravidhi-operator`
- `pravidhi-admin`

A scope alone is not intended to grant unrestricted privilege. Execution and administrative capabilities additionally depend on the control-plane RBAC/policy layer.

## Approval gates

Consequential actions should pass through an explicit approval workflow.

Conceptually:

```text
Request
  ↓
Authenticate
  ↓
Authorize
  ↓
Create approval requirement
  ↓
Human/operator approval
  ↓
Validate approval again
  ↓
Execute constrained operation
  ↓
Record audit event
```

Approval identifiers must be validated against the tenant and intended operation. Expired, denied, mismatched, or missing approvals must fail closed.

## Tenant isolation

Pravidhi treats tenant/workspace identity as a security boundary.

Resource identifiers, approvals, executions, audit events and filesystem workspaces should be resolved in the authenticated tenant context. Cross-tenant identifiers must not be accepted merely because a caller knows an ID.

## Execution safety

The control plane is designed to constrain execution through:

- command allowlisting
- approval checks
- tenant workspace confinement
- unprivileged execution
- request IDs
- rate limiting
- explicit cancellation/status paths
- atomic filesystem operations
- audit logging
- fail-closed authorization

Pravidhi is not intended to provide an unrestricted remote shell.

## Repository layout

```text
api/              API contracts and interfaces
cli/              AgentOS CLI components
commercial/       Product, security boundary and roadmap
cron/             Scheduling components
cyber/            Security/cyber modules
deployment/       Production deployment documentation
developers/       Developer documentation
docs/             Operational and integration documentation
engine/           Runtime engine components
gateway/          Gateway/control-plane components
memory/           Memory subsystem
packages/         Reusable packages
platform/         Platform/security/auth documentation
plugins/          Plugin integration package
research/         Research material
router_agent/     Routing/agent components
scripts/          Operational scripts
skills/           Reusable agent skills
tests/             Test suite
tools/             Developer/operator tooling
```

The repository is the canonical open-source source/documentation tree for the Pravidhi control plane and Pravidh Commander dashboard. The production MCP process may be deployed independently from the repository.

## Quickstart

### Python/runtime

```bash
git clone https://github.com/yashas-13/Pravidhi-OS.git
cd Pravidhi-OS
python -m venv .venv
source .venv/bin/activate
pip install -e .
```

### AgentOS CLI

If the published package is available in your environment:

```bash
npx pravidhi-agentos@latest init
```

Configure service URLs and credentials through environment variables or a secret manager. **Never commit tokens, passwords, private keys, OAuth secrets, or production environment files.**

## Configuration

Start from:

```text
.env.example
```

Production configuration should provide, as appropriate:

- control-plane base URL
- MCP URL
- OIDC issuer
- OIDC audience/resource identifier
- OIDC JWKS endpoint
- tenant identifier
- service-specific policy configuration
- secret-manager references

Secrets belong outside Git.

## ChatGPT app submission

The repository contains:

```text
chatgpt-app-submission.json
```

This file is a submission draft based on the **currently confirmed MCP surface**. It deliberately does not advertise privileged MCP tools that have not been verified by a live MCP tools scan.

Submission resources:

- [OpenAI App Submission schema](https://developers.openai.com/plugins/schemas/chatgpt-app-submission.v1.json)
- [OpenAI submission documentation](https://developers.openai.com/plugins/deploy/submission)
- [OpenAI MCP authentication documentation](https://developers.openai.com/plugins/build/auth)

Before submission, verify:

1. HTTPS MCP endpoint is reachable.
2. Domain challenge returns the exact token supplied by OpenAI.
3. OAuth authorization completes successfully.
4. MCP tools scan matches this repository's submission JSON.
5. Tool annotations accurately describe read-only and consequential operations.
6. Positive and negative tests pass.
7. Privacy, terms and support pages are reachable.

## Domain verification

OpenAI's challenge URL is:

```text
https://mcp.pravidhisolutions.in/.well-known/openai-apps-challenge
```

The challenge token is intentionally **not stored in this repository**. Tokens supplied by a platform must remain deployment configuration, not source code.

## Feature and use-case guide

See [Feature & Use-Case Guide](docs/FEATURE_USE_CASES.md) for practical examples covering machine control, authentication, RBAC, tenant isolation, approvals, terminal/filesystem operations, MCP, desktop workflows, evidence, knowledge management, SOC, DevOps, developer and IT workflows.

## Security documentation

- [Security Boundary](commercial/SECURITY_BOUNDARY.md)
- [Security](platform/security.mdx)
- [Authentication](platform/authentication.mdx)
- [Production deployment](deployment/production.mdx)
- [Privacy Policy](PRIVACY.md)
- [Terms of Service](TERMS.md)
- [Architecture](architecture.mdx)
- [Quickstart](quickstart.mdx)

## Demo and evidence

The repository includes the demo/evidence workflow used to validate deployment capabilities:

```text
docs/DEMO_RECORDING_MATRIX.md
tools/demo-recorder/action-manifest.json
tools/demo-recorder/index.html
```

The browser recorder stores evidence locally in the browser. Recordings must not contain passwords, OAuth secrets, bearer tokens, private keys, customer data or other sensitive information.

## Development principles

1. **Authenticate before privilege.**
2. **Authorize every protected capability.**
3. **Keep tenant boundaries explicit.**
4. **Require approval for consequential actions.**
5. **Constrain execution.**
6. **Audit security-relevant actions.**
7. **Fail closed when a required control is unavailable.**
8. **Never commit secrets.**
9. **Document the actual deployed surface, not an aspirational one.**
10. **Treat the AI as an operator within policy, not as a bypass around policy.**

## Status

**Production MCP transport:** deployed.

**OIDC authorization layer:** deployed with Keycloak.

**Protected MCP resource validation:** deployed.

**Domain verification endpoint:** deployed and verified against the current OpenAI challenge.

**Privileged per-scope MCP tool expansion:** deployment-gated; verify through the live MCP tools scan before advertising it as available.

## License

MIT
