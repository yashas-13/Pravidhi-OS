# Pravidhi AgentOS CLI

Pravidhi AgentOS connects an authorized machine or infrastructure agent to the Pravidhi control plane.

## One-line Termux installer

Run this inside **Termux on Android**:

```bash
npx --yes pravidhi-agentos@latest termux
```

The installer downloads/updates the Pravidhi OS repository, installs Python + `termux-services` + Termux-MCP, creates supervised MCP and agent services, keeps MCP bound to localhost, enables Termux:Boot persistence, and starts the services.

If an existing `~/.pravidhi/agent-token.json` exists, it is preserved.

### First-time pairing

Installation never embeds credentials. For a new device, provide a short-lived pairing code:

```bash
npx --yes pravidhi-agentos@latest termux --pairing-code YOUR_CODE
```

or:

```bash
PRAVIDHI_AGENT_PAIRING_CODE=YOUR_CODE npx --yes pravidhi-agentos@latest termux
```

An existing agent token can also be supplied through `PRAVIDHI_AGENT_TOKEN`; it is written with mode 0600 and is never printed.

## Other commands

```bash
npx --yes pravidhi-agentos@latest health
npx --yes pravidhi-agentos@latest providers
npx --yes pravidhi-agentos@latest login google
npx --yes pravidhi-agentos@latest login github
npx --yes pravidhi-agentos@latest version
npx --yes pravidhi-agentos@latest init
npx --yes pravidhi-agentos@latest status
npx --yes pravidhi-agentos@latest capabilities
```

## Termux architecture

```
Android Termux
  ├─ termux-mcp :8080 (localhost only)
  ├─ pravidhi-termux (heartbeat + task worker)
  └─ Termux:Boot
          │
          ▼ outbound HTTPS
Pravidhi control plane
  └─ mcp.pravidhisolutions.in
```

Node.js 18+ is required. The installer does not expose port 8080 to the Internet.
