# Pravidhi OS Privacy Policy

**Effective date: September 28, 2026**

Pravidh Solutions provides Pravidhi OS, a security-focused control workflow for authorized AI-assisted machine operations.

## Data we collect

The Pravidhi OS plugin package does not independently maintain a separate user database or sell personal information. When a user uses Pravidhi OS with a configured control plane, the information necessary to perform the requested workflow may include user-supplied prompts and task parameters, tenant or organization identifiers, authentication claims, resource identifiers, command or filesystem parameters, approval references, and operational results returned by the configured control plane.

## How data is used

Data is used only to authenticate and authorize requested operations, enforce tenant isolation and policy, execute or plan authorized workflows, present relevant results, and maintain security/audit records for the configured Pravidhi OS deployment.

## Sharing

Pravidh Solutions does not sell personal information. Information may be processed by the systems the user or organization chooses to connect to Pravidhi OS, including the identity provider, OpenAI/ChatGPT platform, and the organization's own Pravidhi control-plane infrastructure. We do not intentionally disclose credentials, private keys, or unrelated tenant data.

## Retention

The plugin package itself has no independent persistent data store, so its direct retention is **0 days**. A customer-operated Pravidhi control plane may retain security and audit records according to that deployment's configured retention policy; those records remain governed by the deploying organization and its applicable agreements and policies.

## User controls

Users can stop using the plugin, revoke or rotate credentials in their identity/secret-management system, request access or deletion of data held by a customer-operated deployment from that deployment's administrator, and contact Pravidh Solutions for support regarding this policy.

## Security

Pravidhi OS is designed around OIDC/JWKS authentication, RBAC, tenant isolation, approval gates, rate limiting, constrained execution, and fail-closed security handling. Users should never paste bearer tokens, refresh tokens, client secrets, private keys, or approval credentials into chat.

## Contact

Support: https://pravidhisolutions.in/contact

Privacy contact: hello@pravidhisolutions.in
