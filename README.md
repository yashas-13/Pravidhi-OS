# Pravidhi OS

Pravidhi OS is the control-plane and agent architecture for authenticated AI-assisted machine operations.

It is designed around a simple boundary:

```
AI client
   │
   ▼
Pravidhi control plane
   │  authentication · RBAC · tenant isolation · approvals · audit
   ▼
Pravidhi agent
   │
   ▼
authorized machine resources
```

## Documentation

The full documentation is built with Mintlify and lives in this repository.

- [Quickstart](quickstart.mdx)
- [Architecture](architecture.mdx)
- [Authentication](platform/authentication.mdx)
- [Security](platform/security.mdx)
- [API reference](api/overview.mdx)
- [Production deployment](deployment/production.mdx)

## Current control-plane deployment

The documented Pravidhi control-plane deployment is:

`https://pravidhisolutions.in/pravidhi/v3`

The service is designed to expose authenticated health, authentication, execution, filesystem, application and screen-agent surfaces.

## Repository scope

This repository is the canonical home for the Pravidhi OS documentation and integration contract. Runtime implementations may be deployed independently.

Credentials, OAuth client secrets, bearer tokens, private keys and production environment files must never be committed.

## License

MIT

## Runtime source

The repository now contains the migrated Pravidhi runtime source tree, including:

- Python engine, pipeline, provider routing, validation, sandbox and registry components
- Gateway/API, chat and control UI components
- Cron scheduler, memory and research subsystems
- Router agent and project configuration
- Pravidhi AgentOS CLI package
- Operational scripts, tests and reusable project skills

The runtime source is kept at the repository root so Python package imports and relative paths remain compatible with the existing implementation.

## Source migration

Runtime code was migrated from the legacy `yashas-13/pravidhi` repository and is now maintained as part of `yashas-13/Pravidhi-OS`.
