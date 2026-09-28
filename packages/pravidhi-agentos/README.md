# Pravidhi AgentOS CLI

Pravidhi AgentOS connects an authorized machine or infrastructure agent to the Pravidhi control plane so AI clients can operate it under authentication, RBAC, approval and audit controls.

## Quick start

Once published to npm:

```bash
npx pravidhi-agentos@latest health
```

Current package can also be tested directly from the Pravidhi distribution endpoint:

```bash
npx --yes https://pravidhisolutions.in/downloads/pravidhi-agentos-latest.tgz health
```

## Commands

```bash
npx pravidhi-agentos@latest health
npx pravidhi-agentos@latest providers
npx pravidhi-agentos@latest login google
npx pravidhi-agentos@latest login github
npx pravidhi-agentos@latest version
npx pravidhi-agentos@latest init
npx pravidhi-agentos@latest status
npx pravidhi-agentos@latest capabilities
```

## Configuration

Set `PRAVIDHI_API_URL` to use another control-plane deployment:

```bash
PRAVIDHI_API_URL=https://example.example/pravidhi/v3 npx pravidhi-agentos@latest health
```

Node.js 18 or newer is required.

## Architecture

```
AI client -> Pravidhi control plane -> authenticated agent -> authorized machine
```

The CLI is intentionally dependency-free and does not contain credentials. Authentication is handled by the Pravidhi control plane.

## Authentication

Privileged control-plane requests use a Bearer token. For the reference gateway, set `PRAVIDHI_API_KEY` through a secret manager or protected environment and never commit it.

```bash
PRAVIDHI_API_KEY='replace-with-secret' npx pravidhi-agentos@latest status
```

The gateway intentionally fails closed when privileged authentication is not configured. See `commercial/SECURITY_BOUNDARY.md`.
