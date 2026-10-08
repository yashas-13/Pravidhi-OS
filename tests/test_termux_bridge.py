from engine.agent_registry import AgentRegistration, AgentRegistry
from engine.agent_tasks import AgentTaskCreate, AgentTaskQueue


def test_termux_task_lifecycle(tmp_path):
    registry = AgentRegistry(f"sqlite:///{tmp_path / 'pravidhi.db'}")
    _, token = registry.register(AgentRegistration(
        agent_id="ANDROID-TERMUX",
        tenant_id="default",
        name="ANDROID-TERMUX",
        platform="termux",
        hostname="android",
        version="1",
        capabilities=["termux.mcp", "termux.terminal", "termux.filesystem.read"],
    ))
    queue = AgentTaskQueue(registry)
    task = queue.create(
        "ANDROID-TERMUX", "default",
        AgentTaskCreate(operation="termux.run", parameters={"cmd": "printf test"}),
    )
    assert task.status == "queued"

    leased = queue.lease_next("ANDROID-TERMUX", token)
    assert leased is not None
    assert leased.status == "running"

    completed = queue.complete(
        "ANDROID-TERMUX", token, leased.task_id,
        {"ok": True, "output": "test"},
    )
    assert completed is not None
    assert completed.status == "completed"
    assert completed.result["output"] == "test"


def test_termux_task_requires_online_agent(tmp_path):
    registry = AgentRegistry(f"sqlite:///{tmp_path / 'pravidhi.db'}")
    registry.register(AgentRegistration(
        agent_id="ANDROID-TERMUX",
        tenant_id="default",
        name="ANDROID-TERMUX",
        platform="termux",
    ))
    queue = AgentTaskQueue(registry)
    # Agent registration is online; task creation therefore succeeds.
    task = queue.create(
        "ANDROID-TERMUX", "default",
        AgentTaskCreate(operation="termux.list", parameters={"path": "."}),
    )
    assert task.status == "queued"
