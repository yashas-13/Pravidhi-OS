"""Independent offline Cron scheduler daemon.

Runs as a standalone process — no gateway dependency.
Jobs persist in SQLite and survive restarts.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import signal
import sqlite3
import subprocess
import sys
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, TypeAlias

import yaml

logger = logging.getLogger("pravidhi.cron")


# ── Types ─────────────────────────────────────────────────────────────────────

class JobStatus(Enum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    PAUSED = "paused"


class JobMode(Enum):
    AGENT = "agent"      # Full LLM agent session
    NO_AGENT = "no-agent"  # Raw command execution, no LLM


@dataclass
class CronJob:
    """A scheduled job persisted in the database."""
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:16])
    name: str = ""
    schedule: str = ""          # cron expression or interval string
    mode: JobMode = JobMode.AGENT
    prompt: str = ""            # For agent mode
    command: str = ""           # For no-agent mode
    skill: str = ""             # Optional skill attachment
    delivery: str = "file"      # file | webhook | telegram | discord | mqtt
    delivery_target: str = ""   # File path, webhook URL, etc.
    status: JobStatus = JobStatus.PENDING
    last_run: Optional[float] = None
    next_run: Optional[float] = None
    run_count: int = 0
    success_count: int = 0
    fail_count: int = 0
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    paused: bool = False
    tags: List[str] = field(default_factory=list)


@dataclass
class JobResult:
    """Result of a single job execution."""
    job_id: str
    started_at: float
    finished_at: float
    success: bool
    stdout: str = ""
    stderr: str = ""
    error: Optional[str] = None
    delivery_status: str = "pending"


# ── Cron Expression Parser ────────────────────────────────────────────────────

def parse_cron_expression(expr: str) -> Optional[Dict[str, Any]]:
    """Parse cron expression or natural language interval.

    Supports:
    - Standard cron: "*/5 * * * *", "0 9 * * 1-5"
    - Natural: "every 2h", "30m", "daily at 9am", "hourly"
    """
    expr = expr.strip().lower()

    # Natural language parsers
    natural_map = {
        "hourly": "0 * * * *",
        "every hour": "0 * * * *",
        "every 2 hours": "0 */2 * * *",
        "every 3 hours": "0 */3 * * *",
        "every 6 hours": "0 */6 * * *",
        "every 12 hours": "0 */12 * * *",
        "daily": "0 0 * * *",
        "daily at 9am": "0 9 * * *",
        "daily at 9": "0 9 * * *",
        "nightly": "0 0 * * *",
        "weekly": "0 0 * * 0",
        "every monday": "0 0 * * 1",
        "every monday at 9am": "0 9 * * 1",
        "monthly": "0 0 1 * *",
        "yearly": "0 0 1 1 *",
        "every minute": "* * * * *",
        "every 5 minutes": "*/5 * * * *",
        "every 10 minutes": "*/10 * * * *",
        "every 15 minutes": "*/15 * * * *",
        "every 30 minutes": "*/30 * * * *",
    }

    if expr in natural_map:
        expr = natural_map[expr]

    # Handle "every Xm" / "every Xh" / "every Xd"
    if expr.startswith("every "):
        rest = expr[6:].strip()
        if rest.endswith("m") or rest.endswith("min"):
            try:
                mins = int(rest.rstrip("m").rstrip("min").strip())
                return {"type": "interval", "seconds": mins * 60, "cron": f"*/{mins} * * * *"}
            except ValueError:
                pass
        elif rest.endswith("h"):
            try:
                hours = int(rest.rstrip("h").strip())
                return {"type": "interval", "seconds": hours * 3600, "cron": f"0 */{hours} * * *"}
            except ValueError:
                pass
        elif rest.endswith("d"):
            try:
                days = int(rest.rstrip("d").strip())
                return {"type": "interval", "seconds": days * 86400, "cron": f"0 0 */{days} * *"}
            except ValueError:
                pass

    # Handle "30m" / "2h" / "7d"
    if expr.endswith("m") and expr[:-1].isdigit():
        mins = int(expr[:-1])
        return {"type": "interval", "seconds": mins * 60, "cron": f"*/{mins} * * * *"}
    if expr.endswith("h") and expr[:-1].isdigit():
        hours = int(expr[:-1])
        return {"type": "interval", "seconds": hours * 3600, "cron": f"0 */{hours} * * *"}
    if expr.endswith("d") and expr[:-1].isdigit():
        days = int(expr[:-1])
        return {"type": "interval", "seconds": days * 86400, "cron": f"0 0 */{days} * *"}

    # Assume it's a cron expression
    parts = expr.split()
    if len(parts) == 5:
        return {"type": "cron", "expression": expr}

    return None


def next_cron_time(cron_expr: str) -> Optional[float]:
    """Calculate next execution time from cron expression.

    Simplistic implementation for common patterns.
    For production, use croniter library.
    """
    parts = cron_expr.split()
    if len(parts) != 5:
        return time.time() + 3600  # Default: 1 hour

    now = time.time()
    current = datetime.fromtimestamp(now, tz=timezone.utc)

    minute_pattern = parts[0]
    hour_pattern = parts[1]

    # Handle simple */N patterns
    if minute_pattern.startswith("*/"):
        interval = int(minute_pattern[2:])
        next_minute = ((current.minute // interval) + 1) * interval
        if next_minute >= 60:
            next_dt = current.replace(hour=current.hour + 1, minute=0, second=0, microsecond=0)
        else:
            next_dt = current.replace(minute=next_minute, second=0, microsecond=0)
        return next_dt.timestamp()

    if minute_pattern == "0" and hour_pattern.startswith("*/"):
        interval = int(hour_pattern[2:])
        next_hour = ((current.hour // interval) + 1) * interval
        if next_hour >= 24:
            next_dt = current.replace(day=current.day + 1, hour=0, minute=0, second=0, microsecond=0)
        else:
            next_dt = current.replace(hour=next_hour, minute=0, second=0, microsecond=0)
        return next_dt.timestamp()

    if minute_pattern == "0" and hour_pattern == "0":
        # Daily at midnight
        next_dt = current.replace(day=current.day + 1, hour=0, minute=0, second=0, microsecond=0)
        return next_dt.timestamp()

    # Default: add 1 minute
    return now + 60


# ── Database ──────────────────────────────────────────────────────────────────

class CronDB:
    """SQLite-backed persistence for cron jobs."""

    def __init__(self, db_path: str = "~/.pravidhi/cron.db"):
        expanded = Path(db_path.replace("~", str(Path.home())))
        expanded.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(expanded))
        self.conn.row_factory = sqlite3.Row
        self._init_schema()

    def _init_schema(self) -> None:
        self.conn.executescript("""
            CREATE TABLE IF NOT EXISTS jobs (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                schedule TEXT NOT NULL,
                mode TEXT NOT NULL DEFAULT 'agent',
                prompt TEXT DEFAULT '',
                command TEXT DEFAULT '',
                skill TEXT DEFAULT '',
                delivery TEXT DEFAULT 'file',
                delivery_target TEXT DEFAULT '',
                status TEXT DEFAULT 'pending',
                last_run REAL,
                next_run REAL,
                run_count INTEGER DEFAULT 0,
                success_count INTEGER DEFAULT 0,
                fail_count INTEGER DEFAULT 0,
                created_at REAL NOT NULL,
                updated_at REAL NOT NULL,
                paused INTEGER DEFAULT 0,
                tags TEXT DEFAULT '[]'
            );
            CREATE TABLE IF NOT EXISTS job_results (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                job_id TEXT NOT NULL,
                started_at REAL NOT NULL,
                finished_at REAL NOT NULL,
                success INTEGER NOT NULL,
                stdout TEXT DEFAULT '',
                stderr TEXT DEFAULT '',
                error TEXT,
                delivery_status TEXT DEFAULT 'pending',
                FOREIGN KEY (job_id) REFERENCES jobs(id)
            );
            CREATE INDEX IF NOT EXISTS idx_jobs_next_run ON jobs(next_run);
            CREATE INDEX IF NOT EXISTS idx_jobs_status ON jobs(status);
        """)
        self.conn.commit()

    def add_job(self, job: CronJob) -> str:
        self.conn.execute(
            """INSERT INTO jobs (id, name, schedule, mode, prompt, command, skill,
               delivery, delivery_target, status, next_run, run_count, success_count,
               fail_count, created_at, updated_at, paused, tags)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (job.id, job.name, job.schedule, job.mode.value, job.prompt, job.command,
             job.skill, job.delivery, job.delivery_target, job.status.value,
             job.next_run, job.run_count, job.success_count, job.fail_count,
             job.created_at, job.updated_at, 1 if job.paused else 0,
             json.dumps(job.tags)),
        )
        self.conn.commit()
        return job.id

    def update_job(self, job: CronJob) -> None:
        job.updated_at = time.time()
        self.conn.execute(
            """UPDATE jobs SET name=?, schedule=?, mode=?, prompt=?, command=?,
               skill=?, delivery=?, delivery_target=?, status=?, last_run=?,
               next_run=?, run_count=?, success_count=?, fail_count=?,
               updated_at=?, paused=?, tags=?
               WHERE id=?""",
            (job.name, job.schedule, job.mode.value, job.prompt, job.command,
             job.skill, job.delivery, job.delivery_target, job.status.value,
             job.last_run, job.next_run, job.run_count, job.success_count,
             job.fail_count, job.updated_at, 1 if job.paused else 0,
             json.dumps(job.tags), job.id),
        )
        self.conn.commit()

    def get_job(self, job_id: str) -> Optional[CronJob]:
        row = self.conn.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()
        return self._row_to_job(row) if row else None

    def get_due_jobs(self) -> List[CronJob]:
        now = time.time()
        rows = self.conn.execute(
            "SELECT * FROM jobs WHERE paused=0 AND next_run IS NOT NULL AND next_run <= ?",
            (now,),
        ).fetchall()
        return [self._row_to_job(r) for r in rows]

    def list_jobs(self, include_paused: bool = False) -> List[CronJob]:
        if include_paused:
            rows = self.conn.execute("SELECT * FROM jobs ORDER BY created_at DESC").fetchall()
        else:
            rows = self.conn.execute(
                "SELECT * FROM jobs WHERE paused=0 ORDER BY created_at DESC"
            ).fetchall()
        return [self._row_to_job(r) for r in rows]

    def delete_job(self, job_id: str) -> bool:
        self.conn.execute("DELETE FROM jobs WHERE id=?", (job_id,))
        self.conn.commit()
        return True

    def pause_job(self, job_id: str) -> bool:
        self.conn.execute(
            "UPDATE jobs SET paused=1, updated_at=? WHERE id=?",
            (time.time(), job_id),
        )
        self.conn.commit()
        return True

    def resume_job(self, job_id: str) -> bool:
        self.conn.execute(
            "UPDATE jobs SET paused=0, updated_at=? WHERE id=?",
            (time.time(), job_id),
        )
        self.conn.commit()
        return True

    def record_result(self, result: JobResult) -> int:
        cur = self.conn.execute(
            """INSERT INTO job_results (job_id, started_at, finished_at, success,
               stdout, stderr, error, delivery_status)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (result.job_id, result.started_at, result.finished_at,
             1 if result.success else 0,
             result.stdout[:10000], result.stderr[:10000],
             result.error, result.delivery_status),
        )
        self.conn.commit()
        return cur.lastrowid

    def get_results(self, job_id: str, limit: int = 20) -> List[Dict]:
        rows = self.conn.execute(
            """SELECT * FROM job_results WHERE job_id=?
               ORDER BY started_at DESC LIMIT ?""",
            (job_id, limit),
        ).fetchall()
        return [dict(r) for r in rows]

    def _row_to_job(self, row: sqlite3.Row) -> CronJob:
        return CronJob(
            id=row["id"],
            name=row["name"],
            schedule=row["schedule"],
            mode=JobMode(row["mode"]),
            prompt=row["prompt"],
            command=row["command"],
            skill=row["skill"],
            delivery=row["delivery"],
            delivery_target=row["delivery_target"],
            status=JobStatus(row["status"]),
            last_run=row["last_run"],
            next_run=row["next_run"],
            run_count=row["run_count"],
            success_count=row["success_count"],
            fail_count=row["fail_count"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            paused=bool(row["paused"]),
            tags=json.loads(row["tags"]),
        )

    def close(self) -> None:
        self.conn.close()


# ── Job Executor ──────────────────────────────────────────────────────────────

class JobExecutor:
    """Executes cron jobs — both agent-mode and no-agent-mode."""

    def __init__(self, db: CronDB):
        self.db = db

    async def execute(self, job: CronJob) -> JobResult:
        """Execute a single job and record the result."""
        started_at = time.time()
        logger.info(f"Executing job: {job.name} ({job.id}) [{job.mode.value}]")

        try:
            if job.mode == JobMode.NO_AGENT and job.command:
                result = await self._execute_command(job.command)
            elif job.mode == JobMode.AGENT and job.prompt:
                result = await self._execute_agent(job.prompt, job.skill)
            else:
                result = JobResult(
                    job_id=job.id, started_at=started_at,
                    finished_at=time.time(), success=False,
                    error="No command or prompt configured",
                )

            result.job_id = job.id
            result.started_at = started_at
            result.finished_at = time.time()

            # Update job stats
            job.last_run = started_at
            job.run_count += 1
            if result.success:
                job.success_count += 1
            else:
                job.fail_count += 1

            # Calculate next run
            parsed = parse_cron_expression(job.schedule)
            if parsed:
                if parsed["type"] == "interval":
                    job.next_run = time.time() + parsed["seconds"]
                else:
                    job.next_run = next_cron_time(parsed.get("expression", job.schedule))
            else:
                job.next_run = time.time() + 3600

            job.status = JobStatus.SUCCESS if result.success else JobStatus.FAILED
            self.db.update_job(job)
            self.db.record_result(result)

            logger.info(
                f"Job {job.name} {'✓' if result.success else '✗'} "
                f"({result.finished_at - result.started_at:.1f}s)"
            )
            return result

        except Exception as e:
            result = JobResult(
                job_id=job.id, started_at=started_at,
                finished_at=time.time(), success=False,
                error=str(e),
            )
            self.db.record_result(result)
            return result

    async def _execute_command(self, command: str) -> JobResult:
        """Execute a shell command (no-agent mode)."""
        start = time.time()
        proc = await asyncio.create_subprocess_shell(
            command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        try:
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=300)
            return JobResult(
                job_id="", started_at=start, finished_at=time.time(),
                success=proc.returncode == 0,
                stdout=stdout.decode("utf-8", errors="replace") if stdout else "",
                stderr=stderr.decode("utf-8", errors="replace") if stderr else "",
            )
        except asyncio.TimeoutError:
            proc.kill()
            return JobResult(
                job_id="", started_at=start, finished_at=time.time(),
                success=False, error="Command timed out after 300s",
            )

    async def _execute_agent(self, prompt: str, skill: str = "") -> JobResult:
        """Execute an agent-mode prompt.

        For now, this is a lightweight execution.
        In production, this delegates to the LLM provider.
        """
        start = time.time()
        try:
            # TODO: Full agent execution via provider_router
            # For now, run a simple analysis
            from engine.provider_router import ProviderRouter
            router = ProviderRouter()

            messages = [{"role": "user", "content": prompt}]
            if skill:
                messages.insert(0, {
                    "role": "system",
                    "content": f"You have the following skill loaded: {skill}",
                })

            response = await router.chat(messages)
            return JobResult(
                job_id="", started_at=start, finished_at=time.time(),
                success="error" not in response,
                stdout=response.get("content", ""),
                error=response.get("error"),
            )
        except Exception as e:
            return JobResult(
                job_id="", started_at=start, finished_at=time.time(),
                success=False, error=str(e),
            )


# ── Delivery ──────────────────────────────────────────────────────────────────

class DeliveryService:
    """Routes job results to configured destinations."""

    def __init__(self, db: CronDB):
        self.db = db

    async def deliver(self, result: JobResult) -> str:
        """Deliver a result to its configured destination."""
        job = self.db.get_job(result.job_id)
        if not job:
            return "unknown_job"

        delivery_type = job.delivery

        if delivery_type == "file":
            return await self._deliver_file(result, job)
        elif delivery_type == "webhook":
            return await self._deliver_webhook(result, job)
        else:
            return await self._deliver_file(result, job)

    async def _deliver_file(self, result: JobResult, job: CronJob) -> str:
        """Write result to a file."""
        target = job.delivery_target or f"~/.pravidhi/cron-results/{job.name}.log"
        path = Path(target.replace("~", str(Path.home())))
        path.parent.mkdir(parents=True, exist_ok=True)

        with open(path, "a") as f:
            f.write(f"\n{'='*60}\n")
            f.write(f"Job: {job.name} ({job.id})\n")
            f.write(f"Time: {datetime.fromtimestamp(result.finished_at, tz=timezone.utc)}\n")
            f.write(f"Status: {'SUCCESS' if result.success else 'FAILED'}\n")
            f.write(f"{'='*60}\n")
            if result.stdout:
                f.write(f"STDOUT:\n{result.stdout}\n")
            if result.stderr:
                f.write(f"STDERR:\n{result.stderr}\n")
            if result.error:
                f.write(f"ERROR:\n{result.error}\n")

        return "file_saved"

    async def _deliver_webhook(self, result: JobResult, job: CronJob) -> str:
        """POST result to a webhook URL."""
        target = job.delivery_target
        if not target:
            return "no_webhook_target"

        import httpx
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    target,
                    json={
                        "job_id": result.job_id,
                        "job_name": job.name,
                        "success": result.success,
                        "stdout": result.stdout[:5000],
                        "stderr": result.stderr[:5000],
                        "error": result.error,
                        "finished_at": result.finished_at,
                    },
                    timeout=30,
                )
                return f"webhook_sent_{response.status_code}"
        except Exception as e:
            logger.warning(f"Webhook delivery failed: {e}")
            return f"webhook_failed_{e}"


# ── Scheduler Daemon ──────────────────────────────────────────────────────────

class CronDaemon:
    """Independent cron daemon — runs as a standalone process."""

    def __init__(self, db_path: str = "~/.pravidhi/cron.db"):
        self.db = CronDB(db_path)
        self.executor = JobExecutor(self.db)
        self.delivery = DeliveryService(self.db)
        self._running = False
        self._poll_interval = 15  # seconds

    async def start(self) -> None:
        """Start the cron scheduling loop."""
        self._running = True
        logger.info("Cron daemon started")

        while self._running:
            try:
                await self._tick()
            except Exception as e:
                logger.error(f"Cron tick error: {e}")

            await asyncio.sleep(self._poll_interval)

    async def stop(self) -> None:
        """Gracefully stop the daemon."""
        self._running = False
        logger.info("Cron daemon stopping")

    async def _tick(self) -> None:
        """Check for due jobs and execute them."""
        due_jobs = self.db.get_due_jobs()
        if due_jobs:
            logger.debug(f"Found {len(due_jobs)} due jobs")

        # Limit concurrency
        max_concurrent = 3
        for i in range(0, len(due_jobs), max_concurrent):
            batch = due_jobs[i:i + max_concurrent]
            tasks = [self.executor.execute(job) for job in batch]
            results = await asyncio.gather(*tasks, return_exceptions=True)

            for job, result in zip(batch, results):
                if isinstance(result, Exception):
                    logger.error(f"Job {job.name} failed with exception: {result}")
                    continue
                # Deliver result
                delivery_status = await self.delivery.deliver(result)
                logger.debug(f"Job {job.name} delivery: {delivery_status}")

    def load_from_config(self, jobs_config: List[Dict[str, Any]]) -> int:
        """Load jobs from config dict."""
        count = 0
        for jc in jobs_config:
            parsed = parse_cron_expression(jc.get("schedule", ""))
            next_run = time.time() + 60  # Default: run soon
            if parsed:
                if parsed["type"] == "interval":
                    next_run = time.time() + parsed["seconds"]
                else:
                    next_run = next_cron_time(parsed.get("expression", jc["schedule"]))

            job = CronJob(
                name=jc.get("name", "unnamed"),
                schedule=jc.get("schedule", "0 * * * *"),
                mode=JobMode(jc.get("mode", "agent")),
                prompt=jc.get("prompt", ""),
                command=jc.get("command", ""),
                skill=jc.get("skill", ""),
                delivery=jc.get("delivery", "file"),
                next_run=next_run,
            )
            self.db.add_job(job)
            count += 1
        return count


# ── CLI-Compatible Entry Points ──────────────────────────────────────────────

def start_daemon(db_path: str = "~/.pravidhi/cron.db"):
    """Start the cron daemon (blocking)."""
    logging.basicConfig(level=logging.INFO)
    daemon = CronDaemon(db_path)

    # Handle shutdown signals
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, lambda: asyncio.ensure_future(daemon.stop()))
        except NotImplementedError:
            pass  # Windows doesn't support add_signal_handler

    try:
        loop.run_until_complete(daemon.start())
    except KeyboardInterrupt:
        loop.run_until_complete(daemon.stop())
    finally:
        loop.close()


def list_jobs(db_path: str = "~/.pravidhi/cron.db"):
    """List all cron jobs."""
    db = CronDB(db_path)
    jobs = db.list_jobs(include_paused=True)
    for j in jobs:
        status = "PAUSED" if j.paused else j.status.value.upper()
        print(f"{j.id[:8]}  {status:8}  {j.name:30}  next: {j.next_run or 'never'}")
    db.close()


def add_job(name: str, schedule: str, command: str = "",
            prompt: str = "", db_path: str = "~/.pravidhi/cron.db"):
    """Add a new cron job."""
    db = CronDB(db_path)
    parsed = parse_cron_expression(schedule)
    next_run = time.time() + 60
    if parsed:
        if parsed["type"] == "interval":
            next_run = time.time() + parsed["seconds"]
        else:
            next_run = next_cron_time(parsed.get("expression", schedule))

    job = CronJob(
        name=name,
        schedule=schedule,
        mode=JobMode.NO_AGENT if command else JobMode.AGENT,
        prompt=prompt,
        command=command,
        next_run=next_run,
    )
    job_id = db.add_job(job)
    print(f"Added job: {job_id[:8]} — {name} ({schedule})")
    db.close()
    return job_id
