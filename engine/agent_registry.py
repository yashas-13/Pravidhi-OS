"""Authoritative Pravidhi OS agent registry.

The registry is the single source of truth for connected execution endpoints.
It owns identity, tenant binding, lifecycle state, capabilities and heartbeat
metadata. Runtime transports (MCP/A2A/desktop relays) consume this registry;
they do not maintain independent authoritative agent state.
"""

from __future__ import annotations

import hashlib
import hmac
import os
import secrets
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field
from sqlalchemy import JSON, Boolean, DateTime, Float, String, Text, create_engine, select
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _database_url() -> str:
    return os.getenv("PRAVIDHI_DATABASE_URL", "sqlite:///" + os.path.expanduser("~/.pravidhi/pravidhi.db"))


class Base(DeclarativeBase):
    pass


class AgentRecord(Base):
    __tablename__ = "pravidhi_agents"

    agent_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(128), index=True)
    name: Mapped[str] = mapped_column(String(255))
    platform: Mapped[str] = mapped_column(String(64))
    hostname: Mapped[str] = mapped_column(String(255), default="")
    version: Mapped[str] = mapped_column(String(64), default="")
    status: Mapped[str] = mapped_column(String(32), default="offline", index=True)
    capabilities: Mapped[List[str]] = mapped_column(JSON, default=list)
    metadata_json: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict)
    token_hash: Mapped[str] = mapped_column(String(128))
    public_key: Mapped[str] = mapped_column(Text, default="")
    registered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    last_seen_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    last_ip: Mapped[str] = mapped_column(String(64), default="")
    last_error: Mapped[str] = mapped_column(Text, default="")
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    load_average: Mapped[Optional[float]] = mapped_column(Float, nullable=True)


class AgentRegistration(BaseModel):
    agent_id: Optional[str] = None
    tenant_id: str = Field(min_length=1, max_length=128)
    name: str = Field(min_length=1, max_length=255)
    platform: str = Field(min_length=1, max_length=64)
    hostname: str = ""
    version: str = ""
    capabilities: List[str] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)
    public_key: str = ""


class AgentHeartbeat(BaseModel):
    status: str = "online"
    capabilities: Optional[List[str]] = None
    version: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None
    load_average: Optional[float] = None
    error: str = ""


class AgentView(BaseModel):
    agent_id: str
    tenant_id: str
    name: str
    platform: str
    hostname: str
    version: str
    status: str
    capabilities: List[str]
    metadata: Dict[str, Any]
    registered_at: datetime
    last_seen_at: Optional[datetime]
    enabled: bool


class AgentRegistry:
    """Persistent, tenant-scoped source of truth for connected agents."""

    def __init__(self, database_url: Optional[str] = None):
        url = database_url or _database_url()
        if url.startswith("sqlite:///"):
            path = url.removeprefix("sqlite:///")
            if path and path != ":memory:":
                os.makedirs(os.path.dirname(os.path.abspath(os.path.expanduser(path))), exist_ok=True)
        connect_args = {"check_same_thread": False} if url.startswith("sqlite") else {}
        self.engine = create_engine(url, future=True, connect_args=connect_args)
        self.Session = sessionmaker(self.engine, expire_on_commit=False)
        Base.metadata.create_all(self.engine)

    @staticmethod
    def _hash_token(token: str) -> str:
        return hashlib.sha256(token.encode("utf-8")).hexdigest()

    @staticmethod
    def _new_agent_id(platform: str) -> str:
        slug = "".join(c.lower() if c.isalnum() else "-" for c in platform).strip("-") or "agent"
        return f"{slug}-{uuid.uuid4().hex[:12]}"

    def register(self, request: AgentRegistration) -> tuple[AgentView, str]:
        agent_id = request.agent_id or self._new_agent_id(request.platform)
        if not agent_id.replace("-", "").replace("_", "").isalnum():
            raise ValueError("agent_id must contain only letters, numbers, hyphens or underscores")
        with self.Session() as session:
            existing = session.get(AgentRecord, agent_id)
            if existing and existing.enabled:
                raise ValueError("agent_id_already_registered")
        token = "pra_" + secrets.token_urlsafe(32)
        record = AgentRecord(
            agent_id=agent_id,
            tenant_id=request.tenant_id,
            name=request.name,
            platform=request.platform,
            hostname=request.hostname,
            version=request.version,
            status="online",
            capabilities=sorted(set(request.capabilities)),
            metadata_json=request.metadata,
            token_hash=self._hash_token(token),
            public_key=request.public_key,
            registered_at=_utcnow(),
            last_seen_at=_utcnow(),
        )
        with self.Session.begin() as session:
            session.add(record)
        return self._view(record), token

    def heartbeat(self, agent_id: str, token: str, request: AgentHeartbeat, ip: str = "") -> Optional[AgentView]:
        with self.Session.begin() as session:
            record = session.get(AgentRecord, agent_id)
            if not record or not record.enabled:
                return None
            if not hmac.compare_digest(record.token_hash, self._hash_token(token)):
                return None
            record.status = request.status
            record.last_seen_at = _utcnow()
            record.last_ip = ip
            record.last_error = request.error
            if request.capabilities is not None:
                record.capabilities = sorted(set(request.capabilities))
            if request.version is not None:
                record.version = request.version
            if request.metadata is not None:
                record.metadata_json = request.metadata
            if request.load_average is not None:
                record.load_average = request.load_average
            return self._view(record)

    def list(self, tenant_id: Optional[str] = None, include_disabled: bool = False) -> List[AgentView]:
        with self.Session() as session:
            stmt = select(AgentRecord).order_by(AgentRecord.name.asc())
            if tenant_id:
                stmt = stmt.where(AgentRecord.tenant_id == tenant_id)
            if not include_disabled:
                stmt = stmt.where(AgentRecord.enabled.is_(True))
            return [self._view(row) for row in session.scalars(stmt).all()]

    def get(self, agent_id: str, tenant_id: Optional[str] = None) -> Optional[AgentView]:
        with self.Session() as session:
            record = session.get(AgentRecord, agent_id)
            if not record or not record.enabled:
                return None
            if tenant_id and record.tenant_id != tenant_id:
                return None
            return self._view(record)

    def mark_stale(self, timeout_seconds: int = 90) -> int:
        cutoff = datetime.fromtimestamp(time.time() - timeout_seconds, tz=timezone.utc)
        changed = 0
        with self.Session.begin() as session:
            rows = session.scalars(select(AgentRecord).where(
                AgentRecord.enabled.is_(True),
                AgentRecord.status == "online",
                AgentRecord.last_seen_at.is_not(None),
                AgentRecord.last_seen_at < cutoff,
            )).all()
            for row in rows:
                row.status = "offline"
                changed += 1
        return changed

    @staticmethod
    def _view(record: AgentRecord) -> AgentView:
        return AgentView(
            agent_id=record.agent_id,
            tenant_id=record.tenant_id,
            name=record.name,
            platform=record.platform,
            hostname=record.hostname,
            version=record.version,
            status=record.status,
            capabilities=list(record.capabilities or []),
            metadata=dict(record.metadata_json or {}),
            registered_at=record.registered_at,
            last_seen_at=record.last_seen_at,
            enabled=record.enabled,
        )


_registry: Optional[AgentRegistry] = None


def get_agent_registry() -> AgentRegistry:
    global _registry
    if _registry is None:
        _registry = AgentRegistry()
    return _registry
