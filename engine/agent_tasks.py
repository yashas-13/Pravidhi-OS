"""Durable task queue for registered endpoint agents."""

from __future__ import annotations
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from pydantic import BaseModel, Field
from sqlalchemy import DateTime, String, Text, JSON, select
from sqlalchemy.orm import Mapped, mapped_column

from engine.agent_registry import Base, get_agent_registry, AgentHeartbeat

def _utcnow() -> datetime:
    return datetime.now(timezone.utc)

class AgentTaskRecord(Base):
    __tablename__ = "pravidhi_agent_tasks"
    task_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    agent_id: Mapped[str] = mapped_column(String(128), index=True)
    tenant_id: Mapped[str] = mapped_column(String(128), index=True)
    operation: Mapped[str] = mapped_column(String(64))
    parameters: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    status: Mapped[str] = mapped_column(String(32), default="queued", index=True)
    result: Mapped[Optional[dict[str, Any]]] = mapped_column(JSON, nullable=True)
    error: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    leased_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

class AgentTaskCreate(BaseModel):
    operation: str = Field(pattern=r"^(termux\.run|termux\.read|termux\.list)$")
    parameters: dict[str, Any] = Field(default_factory=dict)

class AgentTaskView(BaseModel):
    task_id: str
    agent_id: str
    tenant_id: str
    operation: str
    parameters: dict[str, Any]
    status: str
    result: Optional[dict[str, Any]] = None
    error: str = ""
    created_at: datetime
    leased_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None

class AgentTaskQueue:
    def __init__(self, registry=None):
        self.registry = registry or get_agent_registry()
        self.engine = self.registry.engine
        self.Session = self.registry.Session
        Base.metadata.create_all(self.engine)

    @staticmethod
    def _view(row: AgentTaskRecord) -> AgentTaskView:
        return AgentTaskView(
            task_id=row.task_id, agent_id=row.agent_id, tenant_id=row.tenant_id,
            operation=row.operation, parameters=dict(row.parameters or {}),
            status=row.status, result=dict(row.result or {}) if row.result is not None else None,
            error=row.error or "", created_at=row.created_at, leased_at=row.leased_at,
            completed_at=row.completed_at,
        )

    def create(self, agent_id: str, tenant_id: str, task: AgentTaskCreate) -> AgentTaskView:
        agent = self.registry.get(agent_id, tenant_id=tenant_id)
        if agent is None:
            raise ValueError("agent_not_found")
        if agent.status != "online":
            raise ValueError("agent_offline")
        row = AgentTaskRecord(
            task_id="pat_" + uuid.uuid4().hex, agent_id=agent_id, tenant_id=tenant_id,
            operation=task.operation, parameters=task.parameters, status="queued",
        )
        with self.Session.begin() as session:
            session.add(row)
        return self._view(row)

    def lease_next(self, agent_id: str, token: str) -> Optional[AgentTaskView]:
        agent = self.registry.heartbeat(agent_id, token, AgentHeartbeat(status="online"))
        if agent is None:
            return None
        with self.Session.begin() as session:
            row = session.scalars(
                select(AgentTaskRecord).where(
                    AgentTaskRecord.agent_id == agent_id,
                    AgentTaskRecord.tenant_id == agent.tenant_id,
                    AgentTaskRecord.status == "queued",
                ).order_by(AgentTaskRecord.created_at.asc()).limit(1)
            ).first()
            if row is None:
                return None
            row.status = "running"
            row.leased_at = _utcnow()
            return self._view(row)

    def complete(self, agent_id: str, token: str, task_id: str, result: dict[str, Any], error: str = "") -> Optional[AgentTaskView]:
        agent = self.registry.get(agent_id)
        if agent is None:
            return None
        if self.registry.heartbeat(agent_id, token, AgentHeartbeat(status="online")) is None:
            return None
        with self.Session.begin() as session:
            row = session.get(AgentTaskRecord, task_id)
            if row is None or row.agent_id != agent_id or row.tenant_id != agent.tenant_id:
                return None
            row.status = "failed" if error else "completed"
            row.result = result
            row.error = error
            row.completed_at = _utcnow()
            return self._view(row)

    def get(self, task_id: str, tenant_id: str) -> Optional[AgentTaskView]:
        with self.Session() as session:
            row = session.get(AgentTaskRecord, task_id)
            if row is None or row.tenant_id != tenant_id:
                return None
            return self._view(row)
