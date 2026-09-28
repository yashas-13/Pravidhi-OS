"""Pravidhi Control UI — FastAPI routes for the web dashboard.

Provides:
- System status & health monitoring
- Cron job management (CRUD)
- Cybersecurity agent controls
- Reverse engineering tools
- Research engine controls
- Provider configuration
- Real-time logs & metrics
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, FastAPI, HTTPException, Query, WebSocket
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel

from engine.config import get_config, reload_config
from engine.pipeline import Pipeline
from engine.registry import get_registry
from engine.provider_router import ProviderRouter

logger = logging.getLogger("pravidhi.control_ui")


# ── Pydantic Models ──────────────────────────────────────────────────────────

class CronJobCreate(BaseModel):
    name: str
    schedule: str
    command: str = ""
    prompt: str = ""
    mode: str = "no-agent"
    delivery: str = "file"


class CronJobUpdate(BaseModel):
    name: Optional[str] = None
    schedule: Optional[str] = None
    command: Optional[str] = None
    paused: Optional[bool] = None


class PentestRequest(BaseModel):
    target: str
    intent: str = "full pentest"
    model: str = "openai/gpt-5.4-mini"


class CommandRequest(BaseModel):
    command: str
    target: str = ""


class BinaryAnalysisRequest(BaseModel):
    path: str
    depth: str = "basic"


class ProviderUpdate(BaseModel):
    key: str
    value: str


# ── Router ────────────────────────────────────────────────────────────────────

router = APIRouter(prefix="/api", tags=["control"])


@router.get("/status")
async def get_status():
    """Get full system status."""
    config = get_config()
    registry = get_registry()

    # Check cron
    cron_running = False
    try:
        from cron.scheduler import get_cron_status
        cron_running = get_cron_status()
    except Exception:
        pass

    return {
        "service": "pravidhi",
        "version": config.engine.version,
        "uptime": time.time(),
        "status": "running",
        "cron": {"running": cron_running},
        "registry": registry.summary(),
        "provider": {
            "default_model": config.providers.default_model,
            "routing": config.providers.routing.sort,
        },
        "features": {
            "pipeline": config.engine.pipeline.enabled,
            "research": True,
            "cyber": True,
            "reverse_engineering": True,
            "router_agent": True,
        },
    }


@router.get("/stats")
async def get_stats():
    """Get real-time statistics."""
    registry = get_registry()
    router = ProviderRouter()
    return {
        "tools": len(registry.list_tools()),
        "mcp_servers": len(registry.mcp_servers),
        "skills": len(registry.skills),
        "plugins": len(registry.plugins),
        "providers": len(registry.list_providers()),
        "endpoints": len(router.endpoints),
        "models_available": sum(len(p.models if hasattr(p, 'models') else [])
                                for p in registry.list_providers()),
    }


@router.get("/logs")
async def get_logs(lines: int = Query(50, ge=10, le=500)):
    """Get recent system logs."""
    log_file = Path.home() / ".pravidhi" / "pravidhi.log"
    if not log_file.exists():
        return {"logs": []}
    content = log_file.read_text().split("\n")
    return {"logs": content[-lines:]}


# ── Cron Management ──────────────────────────────────────────────────────────

@router.get("/cron/jobs")
async def list_cron_jobs():
    """List all cron jobs."""
    try:
        from cron.scheduler import CronDB
        db = CronDB()
        jobs = db.list_jobs(include_paused=True)
        return {
            "jobs": [{
                "id": j.id,
                "name": j.name,
                "schedule": j.schedule,
                "mode": j.mode.value if hasattr(j.mode, 'value') else str(j.mode),
                "status": j.status.value if hasattr(j.status, 'value') else str(j.status),
                "paused": j.paused,
                "last_run": j.last_run,
                "next_run": j.next_run,
                "run_count": j.run_count,
                "success_count": j.success_count,
                "fail_count": j.fail_count,
            } for j in jobs],
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/cron/jobs")
async def create_cron_job(job: CronJobCreate):
    """Create a new cron job."""
    try:
        from cron.scheduler import CronDB, CronJob, JobMode
        db = CronDB()
        from cron.scheduler import parse_cron_expression
        parsed = parse_cron_expression(job.schedule)
        next_run = time.time() + 60
        if parsed:
            if parsed["type"] == "interval":
                next_run = time.time() + parsed["seconds"]

        new_job = CronJob(
            name=job.name,
            schedule=job.schedule,
            mode=JobMode.NO_AGENT if job.command else JobMode.AGENT,
            command=job.command,
            prompt=job.prompt,
            delivery=job.delivery,
            next_run=next_run,
        )
        job_id = db.add_job(new_job)
        return {"id": job_id, "name": job.name, "status": "created"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/cron/jobs/{job_id}")
async def delete_cron_job(job_id: str):
    """Delete a cron job."""
    try:
        from cron.scheduler import CronDB
        db = CronDB()
        db.delete_job(job_id)
        return {"status": "deleted", "id": job_id}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/cron/jobs/{job_id}/toggle")
async def toggle_cron_job(job_id: str):
    """Pause/resume a cron job."""
    try:
        from cron.scheduler import CronDB
        db = CronDB()
        job = db.get_job(job_id)
        if not job:
            raise HTTPException(status_code=404, detail="Job not found")
        db.pause_job(job_id, not job.paused)
        return {"status": "paused" if not job.paused else "resumed", "id": job_id}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ── Cybersecurity Agent ──────────────────────────────────────────────────────

@router.post("/cyber/pentest")
async def run_pentest(req: PentestRequest):
    """Run a penetration test."""
    try:
        from router_agent.core import NineRouterAgent
        agent = NineRouterAgent()
        report = await agent.pentest(req.target, req.intent, req.model)
        return {
            "status": report.status,
            "target": req.target,
            "duration": report.duration,
            "findings_count": len(report.findings),
            "findings": [{
                "title": f.title,
                "severity": f.severity,
                "phase": f.phase,
                "description": f.description[:200],
                "remediation": f.remediation[:200] if f.remediation else "",
            } for f in report.findings],
            "summary": report.summary[:500],
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/cyber/scan")
async def run_scan(req: CommandRequest):
    """Run a security scan command."""
    try:
        from router_agent.core import NineRouterAgent
        agent = NineRouterAgent()
        result = await agent.scan(req.target, req.command)
        return {"result": result[:2000]}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/cyber/skills")
async def list_cyber_skills(query: str = "", top_k: int = 10):
    """Search cybersecurity skills."""
    try:
        from router_agent.core import NineRouterAgent
        agent = NineRouterAgent()
        skills = list(agent.skills_index.values())
        if query:
            query = query.lower()
            skills = [s for s in skills if query in s.get("name", "").lower()
                      or query in s.get("description", "").lower()]
        return {"total": len(skills), "skills": skills[:top_k]}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ── Reverse Engineering ──────────────────────────────────────────────────────

@router.post("/re/analyze")
async def analyze_binary(req: BinaryAnalysisRequest):
    """Analyze a binary file."""
    try:
        from engine.reverse_engineering import BinaryAnalyzer
        analyzer = BinaryAnalyzer()
        report = await analyzer.analyze(req.path, req.depth)
        return {
            "format": report.binary.format.value,
            "arch": report.binary.arch,
            "size": report.binary.size,
            "entropy": report.binary.entropy,
            "strings": len(report.binary.strings),
            "hashes": report.binary.hashes,
            "vulnerabilities": len(report.vulnerabilities),
            "summary": report.summary,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ── Pipeline ──────────────────────────────────────────────────────────────────

@router.get("/pipeline/run")
async def run_pipeline(prompt: str = Query(..., min_length=1)):
    """Run a prompt through the Pravidhi pipeline."""
    try:
        pipeline = Pipeline()
        ctx = await pipeline.run(prompt)
        return {
            "request_id": ctx.request_id,
            "duration_ms": ctx.metadata.get("total_duration_ms", 0),
            "validation_score": ctx.validation_score,
            "stages_completed": 7 - len(ctx.errors),
            "errors": ctx.errors[:5],
            "output": str(ctx.final_output)[:1000] if ctx.final_output else "",
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ── Provider Config ───────────────────────────────────────────────────────────

@router.get("/providers")
async def list_providers():
    """List configured providers."""
    try:
        from engine.provider_router import BUILTIN_PROVIDERS
        providers = []
        for name, info in BUILTIN_PROVIDERS.items():
            key = os.getenv(info.get("env_key", ""), "")
            providers.append({
                "name": name,
                "api_type": info["api_type"],
                "configured": bool(key),
                "models": list(info.get("models", {}).keys()),
            })
        return {"providers": providers}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ── Doctor ────────────────────────────────────────────────────────────────────

@router.get("/doctor")
async def run_doctor_endpoint():
    """Run doctor diagnostics."""
    try:
        from gateway.doctor import DoctorEngine
        engine = DoctorEngine()
        results = engine.diagnose()
        return {
            "results": [{
                "name": r.name,
                "passed": r.passed,
                "severity": r.severity,
                "message": r.message,
                "fix_command": r.fix_command,
            } for r in results],
            "summary": engine.summary(results),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/doctor/fix")
async def doctor_fix_endpoint():
    """Auto-fix all doctor issues."""
    try:
        from gateway.doctor import DoctorEngine
        engine = DoctorEngine()
        results = engine.diagnose()
        fixes = engine.auto_fix(results)
        return {
            "fixes": [{
                "check": f["check"],
                "status": f["status"],
                "message": f["message"],
            } for f in fixes],
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ── Research ──────────────────────────────────────────────────────────────────

@router.post("/research/cycle")
async def run_research_cycle():
    """Trigger an auto-research cycle."""
    try:
        from research.training_loop import run_research_cycle
        result = await run_research_cycle()
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/research/status")
async def get_research_status():
    """Get research engine status."""
    try:
        from research.training_loop import TrainingLoop
        loop = TrainingLoop()
        return loop.get_status()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ── Mount to App ──────────────────────────────────────────────────────────────

def mount_dashboard(app: FastAPI):
    """Mount control UI routes and serve static files."""
    app.include_router(router)

    from fastapi.staticfiles import StaticFiles
    static_dir = Path(__file__).parent / "static"
    static_dir.mkdir(parents=True, exist_ok=True)
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

    # Serve the main HTML page
    @app.get("/", response_class=HTMLResponse, include_in_schema=False)
    async def serve_dashboard():
        html = (static_dir / "index.html").read_text() if (static_dir / "index.html").exists() else _generate_default_html()
        return HTMLResponse(content=html)

    logger.info("Control UI dashboard mounted at /")


def _generate_default_html() -> str:
    """Generate the default dashboard HTML."""
    return """<!DOCTYPE html><html lang="en">
<head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>Pravidhi Control UI</title>
<script src="https://cdn.tailwindcss.com"></script>
<link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.5.1/css/all.min.css">
</head><body class="bg-gray-900 text-gray-100 font-sans">
<div id="app" class="min-h-screen flex flex-col">
  <!-- Nav -->
  <nav class="bg-gray-800 border-b border-gray-700 px-6 py-3 flex items-center justify-between">
    <div class="flex items-center gap-3">
      <i class="fas fa-robot text-2xl text-cyan-400"></i>
      <span class="text-xl font-bold">Pravidhi <span class="text-cyan-400">Control UI</span></span>
    </div>
    <div class="flex items-center gap-4 text-sm">
      <span id="status-badge" class="px-2 py-1 rounded bg-green-600 text-xs">RUNNING</span>
      <span id="version-display" class="text-gray-400">v0.1.0</span>
    </div>
  </nav>

  <div class="flex flex-1">
    <!-- Sidebar -->
    <aside class="w-64 bg-gray-800 border-r border-gray-700 p-4 hidden md:block">
      <nav class="space-y-1">
        <a class="nav-link flex items-center gap-3 px-3 py-2 rounded bg-gray-700 text-cyan-300" data-section="overview" href="#">
          <i class="fas fa-tachometer-alt w-5"></i>Overview
        </a>
        <a class="nav-link flex items-center gap-3 px-3 py-2 rounded hover:bg-gray-700" data-section="cron" href="#">
          <i class="fas fa-clock w-5"></i>Cron Jobs
        </a>
        <a class="nav-link flex items-center gap-3 px-3 py-2 rounded hover:bg-gray-700" data-section="cyber" href="#">
          <i class="fas fa-shield-alt w-5"></i>Cyber Security
        </a>
        <a class="nav-link flex items-center gap-3 px-3 py-2 rounded hover:bg-gray-700" data-section="re" href="#">
          <i class="fas fa-microchip w-5"></i>Reverse Engineering
        </a>
        <a class="nav-link flex items-center gap-3 px-3 py-2 rounded hover:bg-gray-700" data-section="pipeline" href="#">
          <i class="fas fa-cogs w-5"></i>Pipeline
        </a>
        <a class="nav-link flex items-center gap-3 px-3 py-2 rounded hover:bg-gray-700" data-section="providers" href="#">
          <i class="fas fa-plug w-5"></i>Providers
        </a>
        <a class="nav-link flex items-center gap-3 px-3 py-2 rounded hover:bg-gray-700" data-section="research" href="#">
          <i class="fas fa-brain w-5"></i>Research
        </a>
        <a class="nav-link flex items-center gap-3 px-3 py-2 rounded hover:bg-gray-700" data-section="logs" href="#">
          <i class="fas fa-list w-5"></i>Logs
        </a>
      </nav>
    </aside>

    <!-- Main Content -->
    <main class="flex-1 p-6 overflow-auto">
      <!-- Overview -->
      <div id="section-overview" class="section active">
        <h2 class="text-2xl font-bold mb-6">System Overview</h2>
        <div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4 mb-8" id="stats-grid">
          <div class="stat-card bg-gray-800 p-4 rounded-lg border border-gray-700"><div class="text-gray-400 text-sm">Tools</div><div class="text-2xl font-bold text-cyan-400" id="stat-tools">-</div></div>
          <div class="stat-card bg-gray-800 p-4 rounded-lg border border-gray-700"><div class="text-gray-400 text-sm">Skills</div><div class="text-2xl font-bold text-green-400" id="stat-skills">-</div></div>
          <div class="stat-card bg-gray-800 p-4 rounded-lg border border-gray-700"><div class="text-gray-400 text-sm">Providers</div><div class="text-2xl font-bold text-purple-400" id="stat-providers">-</div></div>
          <div class="stat-card bg-gray-800 p-4 rounded-lg border border-gray-700"><div class="text-gray-400 text-sm">Endpoints</div><div class="text-2xl font-bold text-yellow-400" id="stat-endpoints">-</div></div>
        </div>

        <div class="bg-gray-800 p-4 rounded-lg border border-gray-700 mb-6">
          <h3 class="text-lg font-semibold mb-3">Quick Actions</h3>
          <div class="flex flex-wrap gap-3">
            <button onclick="runDoctor()" class="px-4 py-2 bg-cyan-600 hover:bg-cyan-700 rounded text-sm"><i class="fas fa-stethoscope mr-2"></i>Run Doctor</button>
            <button onclick="runDoctorFix()" class="px-4 py-2 bg-green-600 hover:bg-green-700 rounded text-sm"><i class="fas fa-wrench mr-2"></i>Doctor --fix</button>
            <button onclick="triggerResearch()" class="px-4 py-2 bg-purple-600 hover:bg-purple-700 rounded text-sm"><i class="fas fa-sync mr-2"></i>Research Cycle</button>
          </div>
        </div>
        <div id="doctor-results" class="mb-6"></div>
      </div>

      <!-- Cron Section -->
      <div id="section-cron" class="section hidden">
        <h2 class="text-2xl font-bold mb-4">Cron Jobs</h2>
        <div class="mb-4 bg-gray-800 p-4 rounded-lg border border-gray-700">
          <h3 class="font-semibold mb-3">Add Job</h3>
          <div class="grid grid-cols-1 md:grid-cols-5 gap-3">
            <input id="cron-name" placeholder="Job name" class="bg-gray-700 px-3 py-2 rounded text-sm">
            <input id="cron-schedule" placeholder="Schedule (e.g., 0 * * * *)" class="bg-gray-700 px-3 py-2 rounded text-sm">
            <input id="cron-command" placeholder="Command (no-agent)" class="bg-gray-700 px-3 py-2 rounded text-sm">
            <input id="cron-prompt" placeholder="Prompt (agent mode)" class="bg-gray-700 px-3 py-2 rounded text-sm">
            <button onclick="addCronJob()" class="px-4 py-2 bg-cyan-600 hover:bg-cyan-700 rounded text-sm"><i class="fas fa-plus mr-2"></i>Add</button>
          </div>
        </div>
        <div class="bg-gray-800 rounded-lg border border-gray-700 overflow-x-auto">
          <table class="w-full text-sm">
            <thead><tr class="bg-gray-700"><th class="px-4 py-2 text-left">Name</th><th class="px-4 py-2 text-left">Schedule</th><th class="px-4 py-2 text-left">Mode</th><th class="px-4 py-2 text-left">Status</th><th class="px-4 py-2 text-left">Runs</th><th class="px-4 py-2 text-left">Next</th><th class="px-4 py-2 text-left">Actions</th></tr></thead>
            <tbody id="cron-table-body"></tbody>
          </table>
        </div>
      </div>

      <!-- Cyber Section -->
      <div id="section-cyber" class="section hidden">
        <h2 class="text-2xl font-bold mb-4">Cybersecurity Agent</h2>
        <div class="grid grid-cols-1 lg:grid-cols-2 gap-6">
          <div class="bg-gray-800 p-4 rounded-lg border border-gray-700">
            <h3 class="font-semibold mb-3">Run Pentest</h3>
            <div class="space-y-3"><input id="pentest-target" placeholder="Target URL/IP" class="w-full bg-gray-700 px-3 py-2 rounded text-sm">
              <select id="pentest-intent" class="w-full bg-gray-700 px-3 py-2 rounded text-sm"><option value="full pentest">Full Pentest</option><option value="recon">Recon</option><option value="discovery">Discovery</option><option value="exploitation">Exploitation</option></select>
              <input id="pentest-model" placeholder="Model (default: openai/gpt-5.4-mini)" class="w-full bg-gray-700 px-3 py-2 rounded text-sm">
              <button onclick="runPentest()" class="px-4 py-2 bg-red-600 hover:bg-red-700 rounded text-sm"><i class="fas fa-crosshairs mr-2"></i>Run Pentest</button></div>
          </div>
          <div class="bg-gray-800 p-4 rounded-lg border border-gray-700">
            <h3 class="font-semibold mb-3">Quick Scan</h3>
            <div class="space-y-3"><input id="scan-target" placeholder="Target" class="w-full bg-gray-700 px-3 py-2 rounded text-sm">
              <input id="scan-command" placeholder="Command (e.g., nmap -sV)" class="w-full bg-gray-700 px-3 py-2 rounded text-sm">
              <button onclick="runScan()" class="px-4 py-2 bg-yellow-600 hover:bg-yellow-700 rounded text-sm"><i class="fas fa-search mr-2"></i>Scan</button></div>
          </div>
        </div>
        <div id="pentest-results" class="mt-4"></div>
        <div class="mt-6 bg-gray-800 p-4 rounded-lg border border-gray-700">
          <h3 class="font-semibold mb-3">Skill Search</h3>
          <div class="flex gap-3"><input id="skill-query" placeholder="Search skills..." class="flex-1 bg-gray-700 px-3 py-2 rounded text-sm"><button onclick="searchSkills()" class="px-4 py-2 bg-blue-600 hover:bg-blue-700 rounded text-sm">Search</button></div>
          <div id="skills-results" class="mt-3 text-sm max-h-60 overflow-y-auto"></div>
        </div>
      </div>

      <!-- Reverse Engineering -->
      <div id="section-re" class="section hidden">
        <h2 class="text-2xl font-bold mb-4">Reverse Engineering</h2>
        <div class="bg-gray-800 p-4 rounded-lg border border-gray-700 mb-4">
          <h3 class="font-semibold mb-3">Binary Analysis</h3>
          <div class="flex gap-3"><input id="binary-path" placeholder="Path to binary file" class="flex-1 bg-gray-700 px-3 py-2 rounded text-sm">
            <select id="binary-depth" class="bg-gray-700 px-3 py-2 rounded text-sm"><option value="basic">Basic</option><option value="deep">Deep</option><option value="full">Full</option></select>
            <button onclick="analyzeBinary()" class="px-4 py-2 bg-purple-600 hover:bg-purple-700 rounded text-sm"><i class="fas fa-microchip mr-2"></i>Analyze</button></div>
        </div>
        <div id="binary-results" class="text-sm"></div>
      </div>

      <!-- Pipeline -->
      <div id="section-pipeline" class="section hidden">
        <h2 class="text-2xl font-bold mb-4">Pipeline</h2>
        <div class="bg-gray-800 p-4 rounded-lg border border-gray-700">
          <div class="flex gap-3 mb-4"><textarea id="pipeline-prompt" placeholder="Enter your prompt..." class="flex-1 bg-gray-700 px-3 py-2 rounded text-sm h-24"></textarea></div>
          <button onclick="runPipeline()" class="px-4 py-2 bg-cyan-600 hover:bg-cyan-700 rounded text-sm"><i class="fas fa-play mr-2"></i>Run Pipeline</button>
        </div>
        <div id="pipeline-results" class="mt-4 text-sm"></div>
      </div>

      <!-- Providers -->
      <div id="section-providers" class="section hidden">
        <h2 class="text-2xl font-bold mb-4">Providers</h2>
        <div id="providers-grid" class="grid grid-cols-1 md:grid-cols-2 gap-4"></div>
      </div>

      <!-- Research -->
      <div id="section-research" class="section hidden">
        <h2 class="text-2xl font-bold mb-4">Research Engine</h2>
        <div id="research-status" class="bg-gray-800 p-4 rounded-lg border border-gray-700 text-sm"></div>
      </div>

      <!-- Logs -->
      <div id="section-logs" class="section hidden">
        <h2 class="text-2xl font-bold mb-4">System Logs</h2>
        <div class="flex gap-3 mb-4"><button onclick="loadLogs(50)" class="px-4 py-2 bg-gray-700 hover:bg-gray-600 rounded text-sm">Last 50</button>
          <button onclick="loadLogs(200)" class="px-4 py-2 bg-gray-700 hover:bg-gray-600 rounded text-sm">Last 200</button>
          <button onclick="loadLogs(500)" class="px-4 py-2 bg-gray-700 hover:bg-gray-600 rounded text-sm">Last 500</button></div>
        <pre id="log-output" class="bg-gray-950 p-4 rounded-lg text-xs font-mono max-h-96 overflow-y-auto border border-gray-700"></pre>
      </div>
    </main>
  </div>
</div>

<script>
const API = '/api';

// Navigation
document.querySelectorAll('.nav-link').forEach(link => {
  link.addEventListener('click', e => {
    e.preventDefault();
    document.querySelectorAll('.section').forEach(s => s.classList.add('hidden'));
    document.getElementById('section-' + link.dataset.section).classList.remove('hidden');
    document.querySelectorAll('.nav-link').forEach(l => l.classList.remove('bg-gray-700', 'text-cyan-300'));
    link.classList.add('bg-gray-700', 'text-cyan-300');
  });
});

// Init
loadStats();
loadCronJobs();
loadProviders();

function show(elementId, html) {
  const el = document.getElementById(elementId);
  if (el) el.innerHTML = html;
}

async function api(path, opts = {}) {
  const res = await fetch(API + path, { headers: {'Content-Type': 'application/json'}, ...opts });
  return await res.json();
}

// Stats
async function loadStats() {
  try { const s = await api('/stats');
    document.getElementById('stat-tools').textContent = s.tools;
    document.getElementById('stat-skills').textContent = s.skills;
    document.getElementById('stat-providers').textContent = s.providers;
    document.getElementById('stat-endpoints').textContent = s.endpoints;
  } catch(e) {}
}

// Doctor
async function runDoctor() {
  const r = await api('/doctor');
  let html = '<div class="bg-gray-800 p-4 rounded-lg border border-gray-700"><h3 class="font-semibold mb-3">Doctor Results</h3>';
  r.results.forEach(res => {
    const icon = res.passed ? '✅' : res.severity === 'error' ? '❌' : '⚠️';
    html += '<div class="flex items-center gap-2 py-1 text-sm"><span>' + icon + '</span><span class="font-mono">' + res.name + '</span><span class="text-gray-400">' + res.message + '</span></div>';
  });
  html += '<div class="mt-3 text-sm">Passed: ' + r.summary.passed + ' | Errors: ' + r.summary.errors + ' | Warnings: ' + r.summary.warnings + '</div></div>';
  show('doctor-results', html);
}

async function runDoctorFix() {
  const r = await api('/doctor/fix', { method: 'POST' });
  let html = '<div class="bg-gray-800 p-4 rounded-lg border border-gray-700"><h3 class="font-semibold mb-3">Auto-Fix Results</h3>';
  r.fixes.forEach(f => { html += '<div class="text-sm py-1">' + (f.status === 'fixed' ? '✅' : '❌') + ' ' + f.check + ': ' + f.message + '</div>'; });
  html += '</div>';
  show('doctor-results', html);
}

// Cron
async function loadCronJobs() {
  try { const r = await api('/cron/jobs');
    let html = '';
    r.jobs.forEach(j => {
      const status = j.paused ? '⏸' : j.status === 'success' ? '✅' : j.status === 'failed' ? '❌' : '⏳';
      html += '<tr class="border-b border-gray-700"><td class="px-4 py-2">' + j.name + '</td><td class="px-4 py-2 font-mono text-xs">' + j.schedule + '</td><td class="px-4 py-2">' + j.mode + '</td><td class="px-4 py-2">' + status + '</td><td class="px-4 py-2">' + j.run_count + '</td><td class="px-4 py-2 text-xs">' + (j.next_run ? new Date(j.next_run*1000).toLocaleString() : '-') + '</td><td class="px-4 py-2"><button onclick="toggleJob(\'' + j.id + '\')" class="text-xs ' + (j.paused ? 'text-green-400' : 'text-yellow-400') + '">' + (j.paused ? 'Resume' : 'Pause') + '</button> <button onclick="deleteJob(\'' + j.id + '\')" class="text-xs text-red-400">Delete</button></td></tr>';
    });
    document.getElementById('cron-table-body').innerHTML = html;
  } catch(e) {}
}

async function addCronJob() {
  const name = document.getElementById('cron-name').value;
  const schedule = document.getElementById('cron-schedule').value;
  const command = document.getElementById('cron-command').value;
  const prompt = document.getElementById('cron-prompt').value;
  if (!name) return alert('Name required');
  await api('/cron/jobs', { method: 'POST', body: JSON.stringify({name, schedule, command, prompt}) });
  loadCronJobs();
  document.getElementById('cron-name').value = '';
  document.getElementById('cron-schedule').value = '';
  document.getElementById('cron-command').value = '';
  document.getElementById('cron-prompt').value = '';
}

async function toggleJob(id) { await api('/cron/jobs/'+id+'/toggle', { method: 'POST' }); loadCronJobs(); }
async function deleteJob(id) { await api('/cron/jobs/'+id, { method: 'DELETE' }); loadCronJobs(); }

// Cyber
async function runPentest() {
  const target = document.getElementById('pentest-target').value;
  const intent = document.getElementById('pentest-intent').value;
  const model = document.getElementById('pentest-model').value || 'openai/gpt-5.4-mini';
  if (!target) return alert('Target required');
  const r = await api('/cyber/pentest', { method: 'POST', body: JSON.stringify({target, intent, model}) });
  let html = '<div class="bg-gray-800 p-4 rounded-lg border border-gray-700 mt-4"><h3 class="font-semibold mb-3">Pentest Results</h3><div class="text-sm">Status: ' + r.status + ' | Duration: ' + r.duration.toFixed(1) + 's | Findings: ' + r.findings_count + '</div>';
  if (r.findings && r.findings.length) {
    html += '<div class="mt-2 space-y-2">';
    r.findings.forEach(f => {
      const colors = {critical:'text-red-400', high:'text-orange-400', medium:'text-yellow-400', low:'text-blue-400', info:'text-gray-400'};
      html += '<div class="bg-gray-700 p-2 rounded text-xs"><span class="' + (colors[f.severity] || '') + ' font-bold">[' + f.severity.toUpperCase() + ']</span> ' + f.title + '<br><span class="text-gray-400">' + (f.description || '').substring(0, 200) + '</span></div>';
    });
    html += '</div>';
  }
  if (r.summary) html += '<div class="mt-2 text-xs text-gray-400">' + r.summary.substring(0, 500) + '</div>';
  html += '</div>';
  show('pentest-results', html);
}

async function runScan() {
  const target = document.getElementById('scan-target').value;
  const command = document.getElementById('scan-command').value || 'nmap -sV';
  if (!target) return alert('Target required');
  const r = await api('/cyber/scan', { method: 'POST', body: JSON.stringify({target, command}) });
  show('pentest-results', '<div class="bg-gray-800 p-4 rounded-lg border border-gray-700 mt-4"><h3 class="font-semibold mb-3">Scan Result</h3><pre class="text-xs whitespace-pre-wrap">' + (r.result || 'No output') + '</pre></div>');
}

async function searchSkills() {
  const q = document.getElementById('skill-query').value;
  const r = await api('/cyber/skills?query=' + encodeURIComponent(q) + '&top_k=20');
  let html = '<div class="font-semibold mb-2">Found ' + r.total + ' skills</div>';
  if (r.skills && r.skills.length) {
    r.skills.forEach(s => { html += '<div class="py-1 border-b border-gray-700 last:border-0"><span class="text-cyan-300">' + (s.name || s.id) + '</span><br><span class="text-gray-400">' + (s.description || '').substring(0, 120) + '</span></div>'; });
  }
  show('skills-results', html);
}

// Reverse Engineering
async function analyzeBinary() {
  const path = document.getElementById('binary-path').value;
  const depth = document.getElementById('binary-depth').value;
  if (!path) return alert('Path required');
  const r = await api('/re/analyze', { method: 'POST', body: JSON.stringify({path, depth}) });
  let html = '<div class="bg-gray-800 p-4 rounded-lg border border-gray-700"><div class="grid grid-cols-2 md:grid-cols-4 gap-3 text-sm">';
  html += '<div><span class="text-gray-400">Format</span><br>' + r.format + '</div>';
  html += '<div><span class="text-gray-400">Arch</span><br>' + r.arch + '</div>';
  html += '<div><span class="text-gray-400">Size</span><br>' + (r.size || 0).toLocaleString() + ' bytes</div>';
  html += '<div><span class="text-gray-400">Entropy</span><br>' + (r.entropy || 0).toFixed(2) + '</div>';
  html += '<div><span class="text-gray-400">Strings</span><br>' + (r.strings || 0) + '</div>';
  html += '<div><span class="text-gray-400">Vulnerabilities</span><br>' + (r.vulnerabilities || 0) + '</div>';
  html += '</div>';
  if (r.hashes) { html += '<div class="mt-3 text-xs font-mono">MD5: ' + r.hashes.md5 + '<br>SHA256: ' + r.hashes.sha256 + '</div>'; }
  html += '<div class="mt-3 text-xs text-gray-400">' + (r.summary || '') + '</div></div>';
  show('binary-results', html);
}

// Pipeline
async function runPipeline() {
  const prompt = document.getElementById('pipeline-prompt').value;
  if (!prompt) return alert('Prompt required');
  const r = await api('/pipeline/run?prompt=' + encodeURIComponent(prompt));
  let html = '<div class="bg-gray-800 p-4 rounded-lg border border-gray-700 text-sm">';
  html += '<div>Request ID: <span class="font-mono">' + r.request_id + '</span></div>';
  html += '<div>Duration: ' + (r.duration_ms || 0).toFixed(0) + 'ms</div>';
  html += '<div>Validation Score: <span class="' + (r.validation_score >= 0.8 ? 'text-green-400' : r.validation_score >= 0.5 ? 'text-yellow-400' : 'text-red-400') + '">' + (r.validation_score * 100).toFixed(0) + '%</span></div>';
  if (r.errors && r.errors.length) { html += '<div class="text-red-400 mt-2">Errors: ' + r.errors.join(', ') + '</div>'; }
  if (r.output) { html += '<pre class="mt-3 bg-gray-900 p-3 rounded text-xs max-h-60 overflow-y-auto">' + r.output.substring(0, 2000) + '</pre>'; }
  html += '</div>';
  show('pipeline-results', html);
}

// Research
async function triggerResearch() {
  const r = await api('/research/cycle', { method: 'POST' });
  show('doctor-results', '<div class="bg-gray-800 p-4 rounded-lg border border-gray-700 text-sm">Research cycle completed<br>Epoch: ' + r.epoch + ' | Accuracy: ' + (r.accuracy * 100).toFixed(1) + '% | Loss: ' + (r.loss || 0).toFixed(3) + '<br>Skills generated: ' + (r.skills_generated || []).join(', ') + '</div>');
}

// Providers
async function loadProviders() {
  try {
    const r = await api('/providers');
    let html = '';
    r.providers.forEach(p => {
      html += '<div class="bg-gray-800 p-4 rounded-lg border border-gray-700"><div class="flex items-center justify-between"><h3 class="font-semibold">' + p.name + '</h3><span class="text-xs px-2 py-1 rounded ' + (p.configured ? 'bg-green-600' : 'bg-gray-600') + '">' + (p.configured ? 'Configured' : 'No key') + '</span></div><div class="text-xs text-gray-400 mt-2">Type: ' + p.api_type + '<br>Models: ' + (p.models || []).join(', ') + '</div></div>';
    });
    document.getElementById('providers-grid').innerHTML = html;
  } catch(e) {}
}

// Logs
async function loadLogs(count) {
  const r = await api('/logs?lines=' + count);
  document.getElementById('log-output').textContent = (r.logs || []).join('\n');
}
</script>
</body></html>"""
