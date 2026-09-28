#!/usr/bin/env python3
"""Pravidhi OS endpoint agent.

Registers a machine with the Pravidhi control plane once, stores the returned
per-agent token locally, and sends heartbeats. It does not execute commands;
execution adapters can consume the same agent identity later.

Environment:
  PRAVIDHI_CONTROL_URL              e.g. https://mcp.pravidhisolutions.in
  PRAVIDHI_AGENT_BOOTSTRAP_TOKEN    admin bootstrap credential
  PRAVIDHI_TENANT_ID                tenant to register into
  PRAVIDHI_AGENT_NAME               display name
  PRAVIDHI_AGENT_TOKEN_FILE         optional local token path
"""

from __future__ import annotations

import json
import os
import platform
import socket
import time
from pathlib import Path
from urllib.request import Request, urlopen


def _post(url: str, payload: dict, headers: dict) -> dict:
    body = json.dumps(payload).encode()
    req = Request(url, data=body, method="POST", headers={
        "Content-Type": "application/json",
        **headers,
    })
    with urlopen(req, timeout=15) as response:
        return json.loads(response.read().decode())


def token_path() -> Path:
    return Path(os.getenv(
        "PRAVIDHI_AGENT_TOKEN_FILE",
        str(Path.home() / ".pravidhi" / "agent-token.json"),
    )).expanduser()


def register() -> dict:
    base = os.environ["PRAVIDHI_CONTROL_URL"].rstrip("/")
    bootstrap = os.environ["PRAVIDHI_AGENT_BOOTSTRAP_TOKEN"]
    tenant = os.environ["PRAVIDHI_TENANT_ID"]
    name = os.getenv("PRAVIDHI_AGENT_NAME", socket.gethostname())
    payload = {
        "agent_id": os.getenv("PRAVIDHI_AGENT_ID", socket.gethostname()),
        "tenant_id": tenant,
        "name": name,
        "platform": platform.system().lower(),
        "hostname": socket.gethostname(),
        "version": os.getenv("PRAVIDHI_AGENT_VERSION", "0.1.0"),
        "capabilities": json.loads(os.getenv("PRAVIDHI_AGENT_CAPABILITIES", "[]")),
        "metadata": {
            "architecture": platform.machine(),
            "python": platform.python_version(),
        },
    }
    result = _post(
        f"{base}/api/agents/register",
        payload,
        {"X-Pravidhi-Agent-Bootstrap": bootstrap},
    )
    path = token_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({
        "agent_id": result["agent"]["agent_id"],
        "agent_token": result["agent_token"],
        "control_url": base,
    }))
    try:
        path.chmod(0o600)
    except OSError:
        pass
    return result["agent"]


def heartbeat() -> dict:
    state = json.loads(token_path().read_text())
    payload = {
        "status": "online",
        "capabilities": json.loads(os.getenv("PRAVIDHI_AGENT_CAPABILITIES", "[]")),
        "version": os.getenv("PRAVIDHI_AGENT_VERSION", "0.1.0"),
        "metadata": {
            "architecture": platform.machine(),
            "python": platform.python_version(),
        },
    }
    return _post(
        f'{state["control_url"]}/api/agents/{state["agent_id"]}/heartbeat',
        payload,
        {"Authorization": f'Bearer {state["agent_token"]}'},
    )


if __name__ == "__main__":
    if not token_path().exists():
        print(json.dumps(register(), indent=2))
    while True:
        try:
            print(json.dumps(heartbeat(), indent=2))
        except Exception as exc:
            print(json.dumps({"status": "offline", "error": str(exc)}))
        time.sleep(int(os.getenv("PRAVIDHI_AGENT_HEARTBEAT_SECONDS", "30")))
