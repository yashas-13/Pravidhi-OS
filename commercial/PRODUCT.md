# Pravidhi OS — Commercial Product Specification

## Positioning

**Pravidhi OS is a secure control plane for AI agents operating computers, servers, browsers, infrastructure and MCP tools.**

Core promise: **Authenticate. Control. Approve. Execute. Audit.**

## Product editions

| Edition | Target | Core capability |
|---|---|---|
| Community | Developers | Local agent, CLI, policy, audit |
| Developer | Individuals | Multi-machine control and API |
| Pro | Consultants/power users | Advanced policy, approvals, browser/desktop |
| Team | Organizations | RBAC, organizations, agent registry, SSO |
| Enterprise | Regulated/large deployments | Private deployment, SCIM, SIEM, SLA |

## Launch pricing targets

- Community: Free
- Developer: ₹499/month
- Pro: ₹1,999/month
- Team: ₹7,999/month
- Business: ₹24,999/month
- Enterprise: Custom

These are product targets, not active billing configuration.

## Product boundary

The commercial control plane contains identity, tenants, agent registry, capabilities, policy, approvals, execution gateway, audit and metering. Experimental modules must not bypass that control plane.

## Distribution

- npm: `npx pravidhi-agentos@latest`
- Python: `pip install pravidhi`
- Docker: `pravidhisolutions/pravidhi-agent`
- GitHub: public source and documentation

## Security promise

Model output is intent, never authorization. Privileged execution must be authenticated, tenant-scoped, capability-checked, policy-checked, approval-checked where required, constrained and audited.

## Launch gate

No endpoint should be advertised as production-ready until it has authentication, authorization, rate limiting, request correlation, audit logging, negative authorization tests and safe failure behavior.
