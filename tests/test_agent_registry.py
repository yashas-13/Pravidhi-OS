from pathlib import Path

from engine.agent_registry import AgentHeartbeat, AgentRegistration, AgentRegistry


def test_register_and_heartbeat(tmp_path: Path):
    db = tmp_path / "agents.db"
    registry = AgentRegistry(f"sqlite:///{db}")

    view, token = registry.register(
        AgentRegistration(
            agent_id="DESKTOP-GU0324G",
            tenant_id="default",
            name="DESKTOP-GU0324G",
            platform="windows",
            hostname="DESKTOP-GU0324G",
            version="0.1.0",
            capabilities=["filesystem.read", "terminal.powershell"],
        )
    )

    assert view.agent_id == "DESKTOP-GU0324G"
    assert view.status == "online"
    assert registry.get("DESKTOP-GU0324G", tenant_id="default").agent_id == "DESKTOP-GU0324G"

    heartbeat = registry.heartbeat(
        "DESKTOP-GU0324G",
        token,
        AgentHeartbeat(status="online", capabilities=["filesystem.read"]),
    )
    assert heartbeat.status == "online"
    assert heartbeat.capabilities == ["filesystem.read"]


def test_tenant_isolation(tmp_path: Path):
    registry = AgentRegistry(f"sqlite:///{tmp_path / 'agents.db'}")
    registry.register(
        AgentRegistration(
            agent_id="VPS-001",
            tenant_id="tenant-a",
            name="VPS-001",
            platform="linux",
        )
    )

    assert registry.get("VPS-001", tenant_id="tenant-a") is not None
    assert registry.get("VPS-001", tenant_id="tenant-b") is None
    assert registry.list(tenant_id="tenant-b") == []
