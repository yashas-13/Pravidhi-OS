# Pravidhi OS ↔ Termux MCP

Pravidhi OS treats Android/Termux as a first-class registered execution endpoint.

## Data path

ChatGPT -> Pravidhi MCP Gateway -> tenant/RBAC/capability policy -> durable
agent task queue -> outbound HTTPS polling -> ANDROID-TERMUX -> local
Termux-MCP execution kernel -> Termux/Android.

The phone does not need an Internet-facing shell port. The endpoint worker
initiates the connection to Pravidhi, which is safer for mobile networks and NAT.

Termux-MCP provides both a native Streamable HTTP MCP server on 127.0.0.1:8081
and a REST daemon on 127.0.0.1:8080. They share the same execution kernel and
safety controls. The Pravidhi worker uses the local REST transport for durable
task execution; the native MCP transport remains available for direct MCP
clients.

## Install on Termux

    pkg update -y
    pkg install python curl git termux-services -y
    python -m pip install -U termux-mcp

Start both local transports:

    export TERMUX_MCP_AUTH=on
    export TERMUX_MCP_HOST=127.0.0.1
    export TERMUX_MCP_PORT=8080
    export TERMUX_MCP_AUTH_TOKEN="$(termux-mcp token)"
    termux-mcp &
    termux-native-mcp --host 127.0.0.1 --port 8081 &

Do not bind either service to 0.0.0.0 for this architecture.

## Pair the phone

On the Pravidhi control plane, create a short-lived pairing code through the
authenticated pairing workflow. Then on Termux:

    export PRAVIDHI_CONTROL_URL='https://mcp.pravidhisolutions.in'
    export PRAVIDHI_TENANT_ID='default'
    export PRAVIDHI_AGENT_ID='ANDROID-TERMUX'
    export PRAVIDHI_AGENT_NAME='ANDROID-TERMUX'
    export PRAVIDHI_AGENT_CAPABILITIES='["termux.mcp","termux.terminal","termux.filesystem.read"]'
    export PRAVIDHI_AGENT_PAIRING_CODE='<PAIRING_CODE>'
    python agents/pravidhi_agent.py

The agent stores its one-time credential at ~/.pravidhi/agent-token.json.

Run the worker in a second Termux process:

    export PRAVIDHI_TERMUX_MCP_URL='http://127.0.0.1:8080'
    export TERMUX_MCP_AUTH_TOKEN='<TERMUX_MCP_TOKEN>'
    python agents/termux_worker.py

The production setup should supervise both processes with termux-services or
Termux:Boot. Keep credentials out of shell history where practical.

## ChatGPT control flow

Once the server deployment exposes the authenticated agent/task MCP tools and
ANDROID-TERMUX is online, ChatGPT can resolve the current endpoint, submit an
authorized task, poll status, and receive the bounded result. It must not claim
connectivity from a stale hostname or from plugin metadata alone.

High-risk Termux operations remain subject to the Termux-MCP device-side risk
gate/approval system. Pravidhi enforces identity, tenant, RBAC and endpoint
capability checks before queueing work.

## Operational requirements

- HTTPS for the Pravidhi control plane.
- One unique agent ID and credential per device.
- No public 8080/8081 listener.
- Bounded task output.
- Offline agents are unavailable execution targets.
- Never commit Pravidhi or Termux bearer tokens.
