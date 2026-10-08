#!/usr/bin/env python3
"""Pravidhi Android/Termux task worker.

The worker keeps an outbound connection to Pravidhi and executes queued work
through the local Termux-MCP REST daemon. The Termux MCP/native MCP processes
remain local-only; no phone shell port is exposed to the Internet.
"""

from __future__ import annotations
import json, os, time, urllib.error, urllib.request
from typing import Any

CONTROL_URL = os.environ["PRAVIDHI_CONTROL_URL"].rstrip("/")
AGENT_ID = os.environ["PRAVIDHI_AGENT_ID"]
TOKEN_FILE = os.path.expanduser(os.getenv("PRAVIDHI_AGENT_TOKEN_FILE", "~/.pravidhi/agent-token.json"))
TERMUX_MCP_URL = os.getenv("PRAVIDHI_TERMUX_MCP_URL", "http://127.0.0.1:8080").rstrip("/")
POLL_SECONDS = float(os.getenv("PRAVIDHI_AGENT_POLL_SECONDS", "1.0"))
MAX_RESULT_BYTES = int(os.getenv("PRAVIDHI_AGENT_MAX_RESULT_BYTES", "200000"))

def token() -> str:
    with open(TOKEN_FILE, encoding="utf-8") as f:
        return json.load(f)["agent_token"]

def request(url: str, method: str = "GET", payload: dict[str, Any] | None = None, bearer: str = "") -> dict[str, Any]:
    body = None if payload is None else json.dumps(payload).encode()
    headers = {"Accept": "application/json"}
    if body is not None:
        headers["Content-Type"] = "application/json"
    if bearer:
        headers["Authorization"] = f"Bearer {bearer}"
    req = urllib.request.Request(url, data=body, method=method, headers=headers)
    with urllib.request.urlopen(req, timeout=30) as response:
        return json.loads(response.read().decode() or "{}")

def termux_call(path: str, payload: dict[str, Any]) -> dict[str, Any]:
    headers = {"Content-Type": "application/json", "Accept": "application/json"}
    mcp_token = os.getenv("TERMUX_MCP_AUTH_TOKEN", "")
    if mcp_token:
        headers["Authorization"] = f"Bearer {mcp_token}"
    req = urllib.request.Request(
        f"{TERMUX_MCP_URL}/{path.lstrip('/')}",
        data=json.dumps(payload).encode(), method="POST", headers=headers,
    )
    with urllib.request.urlopen(req, timeout=300) as response:
        raw = response.read(MAX_RESULT_BYTES + 1)
    if len(raw) > MAX_RESULT_BYTES:
        return {"ok": True, "truncated": True, "output": raw[:MAX_RESULT_BYTES].decode(errors="replace")}
    return json.loads(raw.decode() or "{}")

def execute(task: dict[str, Any]) -> dict[str, Any]:
    p = task.get("parameters", {})
    if task["operation"] == "termux.run":
        cmd = p.get("cmd")
        if not isinstance(cmd, str) or not cmd.strip():
            raise ValueError("termux.run requires a non-empty cmd")
        payload = {"cmd": cmd}
        if p.get("confirmed") is True:
            payload["confirmed"] = True
        return termux_call("/run", payload)
    if task["operation"] == "termux.read":
        path = p.get("path")
        if not isinstance(path, str) or not path:
            raise ValueError("termux.read requires path")
        return termux_call("/read", {"path": path})
    if task["operation"] == "termux.list":
        return termux_call("/ls", {"path": p.get("path", "."), "detailed": bool(p.get("detailed", False))})
    raise ValueError(f"unsupported operation: {task['operation']}")

def main() -> None:
    bearer = token()
    while True:
        try:
            task = request(f"{CONTROL_URL}/api/agents/{AGENT_ID}/tasks/next", bearer=bearer)
            if task.get("task_id"):
                try:
                    result = execute(task)
                    request(
                        f"{CONTROL_URL}/api/agents/{AGENT_ID}/tasks/{task['task_id']}/result",
                        method="POST", payload={"result": result}, bearer=bearer,
                    )
                except Exception as exc:
                    request(
                        f"{CONTROL_URL}/api/agents/{AGENT_ID}/tasks/{task['task_id']}/result",
                        method="POST", payload={"result": {}, "error": str(exc)}, bearer=bearer,
                    )
            else:
                time.sleep(POLL_SECONDS)
        except (urllib.error.URLError, TimeoutError, OSError, ValueError) as exc:
            print(json.dumps({"status": "worker_retry", "error": str(exc)}), flush=True)
            time.sleep(max(POLL_SECONDS, 2.0))

if __name__ == "__main__":
    main()
