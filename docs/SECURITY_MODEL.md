# Pravidhi OS Security Model

## Security boundary

Pravidhi OS is a supervised control plane. It does not make the AI an unrestricted administrator.

The authorization chain is:

```
identity → tenant → role → capability → policy → approval → execution → audit
```

Every protected operation must remain inside that chain.

## Tenant isolation

Tenant identity is derived from authenticated context and must be applied to:

- approvals
- executions
- audit events
- filesystem workspaces
- task identifiers
- resource identifiers

A caller must not gain another tenant's data merely by supplying a known identifier.

## RBAC

Reference roles:

- `pravidhi-user`
- `pravidhi-operator`
- `pravidhi-admin`

Recommended capability model:

| Capability | Scope | Role requirement |
|---|---|---|
| Read information | `pravidhi.read` | user/operator/admin |
| Execute approved action | `pravidhi.execute` | operator/admin |
| Administrative action | `pravidhi.admin` | admin |

The exact role mapping remains an application policy and must be enforced by the control plane rather than inferred from the scope alone.

## Approval gates

Consequential operations should require an approval object before execution.

An approval should bind at minimum to:

- tenant
- requester/subject
- intended operation
- relevant target/resource
- expiry
- approval state

Execution must revalidate the approval immediately before performing the operation.

## Terminal safety

Terminal operations should use:

- allowlists
- constrained arguments
- tenant workspace boundaries
- unprivileged execution
- explicit approval
- cancellation/status controls
- audit events

Pravidhi must not provide a hidden bypass around these controls.

## Filesystem safety

Filesystem writes should use:

- tenant-scoped paths
- path normalization
- traversal protection
- approval when consequential
- atomic write semantics where appropriate
- audit logging

## Audit

Security-relevant operations should generate structured audit events with a correlation/request identifier.

Audit data must be tenant-filtered and must not expose credentials or unrelated tenant data.

## Rate limiting

Public and authenticated endpoints should be rate limited to reduce abuse and protect the control plane.

## Fail closed

When a required security control cannot be evaluated, the operation should fail rather than silently downgrade to an unsafe mode.

Examples:

- missing identity → reject protected operation
- missing role → reject privileged operation
- missing approval → reject consequential operation
- unknown tenant → reject resource access
- policy error → reject execution
- invalid token → reject request

## Secrets

Never commit:

- `.env` production files
- bearer tokens
- refresh tokens
- OAuth client secrets
- Keycloak admin credentials
- database credentials
- private keys
- customer data

Use `.env.example` for configuration shape only.
