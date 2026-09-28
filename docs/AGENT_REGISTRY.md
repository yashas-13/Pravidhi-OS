# Pravidhi OS Agent Registry

Pravidhi OS is the authoritative source of truth for connected execution endpoints.

## Architecture

```
ChatGPT / Codex
      |
      | MCP + OAuth
      v
Pravidhi MCP Gateway
      |
      v
Pravidhi Control Plane
      |
      +-- tenant
      +-- RBAC
      +-- capability policy
      +-- approvals
      +-- audit
      |
      v
Authoritative Agent Registry
      |
      +-- DESKTOP-GU0324G
      +-- Android/Termux
      +-- Linux VPS
      +-- other registered endpoints
      |
      v
Endpoint agent / execution adapter
```

The ChatGPT plugin is an interface only. It must not maintain a second list of
machines or decide which machine is authorized. MCP tools resolve agent state
from the control-plane registry.

## Agent identity

Each machine has a stable `agent_id`, for example:

- `DESKTOP-GU0324G`
- `ANDROID-TERMUX`
- `VPS-BLR-01`

The registry stores:

- tenant
- display name
- platform
- hostname
- agent version
- enabled/disabled state
- capabilities
- public metadata
- registration timestamp
- last heartbeat
- last observed IP
- current lifecycle status

Agent credentials are stored only as SHA-256 hashes. The registration response
returns the generated agent token once; agents should store it with filesystem
permissions restricted to the local account.

## Registration

Set the control-plane bootstrap secret:

```bash
export PRAVIDHI_AGENT_REGISTRATION_TOKEN='change-me-to-a-long-random-secret'
export PRAVIDHI_AGENT_BOOTSTRAP_TENANT='default'
```

Run the portable endpoint agent:

```bash
export PRAVIDHI_CONTROL_URL='https://mcp.pravidhisolutions.in'
export PRAVIDHI_TENANT_ID='default'
export PRAVIDHI_AGENT_ID='DESKTOP-GU0324G'
export PRAVIDHI_AGENT_NAME='DESKTOP-GU0324G'
export PRAVIDHI_AGENT_CAPABILITIES='["filesystem.read","terminal.powershell"]'
python agents/pravidhi_agent.py
```

The same agent program can run on Linux VPSs and Termux. Set a platform-specific
agent ID and capability list rather than granting every endpoint `all`.

## Lifecycle

```
unregistered
   |
   | bootstrap registration
   v
online
   |
   | heartbeat timeout
   v
offline
   |
   | heartbeat
   v
online
```

The control plane marks agents offline after the heartbeat timeout. An offline
agent must never be treated as an available execution target.

## Security rules

1. Agent registration requires the bootstrap credential.
2. Each agent receives its own credential.
3. Agent credentials are not shared with the ChatGPT plugin.
4. Heartbeats authenticate with the agent credential.
5. Tenant scope is enforced by the registry.
6. Capabilities are metadata/policy inputs, not authorization by themselves.
7. Execution still requires the normal identity -> tenant -> role -> capability
   -> policy -> approval -> execution -> audit chain.
8. The agent registry must never become a shell bypass.

## Database

Set `PRAVIDHI_DATABASE_URL` to the control-plane database.

The default development database is:

```
~/.pravidhi/pravidhi.db
```

For production, use the same durable database used by the control plane and
run only one schema owner/migration path. SQLite is suitable for a single-node
deployment; PostgreSQL should be used for multi-instance control planes.

## MCP contract

The MCP plugin should expose operations such as:

- list registered agents
- inspect one agent
- inspect capabilities
- request execution against an agent
- inspect execution status
- retrieve audit evidence

Those operations must resolve the target agent from this registry. The plugin
must not contain a static machine inventory.
