"""OpenAI-compatible API server — connect any frontend to Pravidhi.

Endpoints:
- POST /v1/chat/completions — Standard OpenAI Chat Completions
- GET  /v1/models             — List available models
- GET  /health                — Health check

All tool capabilities available through the chat endpoint.
"""

from __future__ import annotations

import logging
import time
import uuid
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from engine.pipeline import Pipeline
from engine.registry import get_registry

logger = logging.getLogger("pravidhi.api")


# ── Pydantic Models ──────────────────────────────────────────────────────────

class ChatMessage(BaseModel):
    role: str
    content: str | List[Dict[str, Any]]


class ChatRequest(BaseModel):
    model: str = "pravidhi-agent"
    messages: List[ChatMessage]
    stream: bool = False
    max_tokens: int = 4096
    temperature: float = 0.7


class ChatChoice(BaseModel):
    index: int = 0
    message: ChatMessage
    finish_reason: str = "stop"


class ChatUsage(BaseModel):
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0


class ChatResponse(BaseModel):
    id: str = ""
    object: str = "chat.completion"
    created: int = 0
    model: str = "pravidhi-agent"
    choices: List[ChatChoice]
    usage: ChatUsage = ChatUsage()


class ModelInfo(BaseModel):
    id: str
    object: str = "model"
    created: int


class ModelsResponse(BaseModel):
    object: str = "list"
    data: List[ModelInfo]


# ── FastAPI App ──────────────────────────────────────────────────────────────

app = FastAPI(title="Pravidhi API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
async def startup():
    """Initialize Pravidhi engine on API startup."""
    from engine.registry import get_registry
    registry = get_registry()
    registry.discover_skills()
    # Mount control UI dashboard
    try:
        from gateway.control_ui.dashboard import mount_dashboard
        mount_dashboard(app)
        logger.info("Control UI dashboard mounted at /")
    except Exception as e:
        logger.warning(f"Control UI not available: {e}")

    # Mount Chat Control UI
    try:
        from gateway.chat.routes import mount_chat_ui
        mount_chat_ui(app)
        logger.info("Chat Control UI mounted at /chat")
    except Exception as e:
        logger.warning(f"Chat Control UI not available: {e}")
# ── Provider Discovery Route ─────────────────────────────────────────

@app.get("/api/discover/providers")
async def discover_providers():
    """Auto-discover and return all available model providers."""
    from engine.provider_discovery import discover_all
    result = await discover_all()
    return result

# ── UltraWorker Routes ───────────────────────────────────────────────

@app.post("/api/ultraworker/start")
async def ultraworker_start(num_workers: int = 3):
    """Start the ultraworker pool with N parallel workers."""
    from engine.ultraworker import start_pool
    pool = await start_pool(num_workers)
    return {"status": "started", "workers": num_workers, "pool": pool.get_status()}


@app.post("/api/ultraworker/stop")
async def ultraworker_stop():
    """Stop the ultraworker pool."""
    from engine.ultraworker import get_pool
    await get_pool().stop()
    return {"status": "stopped"}

# ── Latest Technologies Routes ──────────────────────────────────────────

@app.get("/api/latest/technologies")
async def latest_technologies():
    """Discover and return all latest integrated technologies status."""
    from engine.latest_tech import discover_all_technologies, MCPManager
    from engine.context_window import CONTEXT_WINDOW_CONFIG
    result = await discover_all_technologies()
    return {
        "status": "ok",
        "discovered": result,
        "features": {
            "1m_context_window": True,
            "context_compression": True,
            "mcp_protocol": True,
            "a2a_agent_network": True,
            "streaming_multiplexer": True,
            "multi_modal_input": True,
            "self_hosted_models": True,
            "tool_dependency_scanner": True,
            "prompt_caching": True,
            "adaptive_rate_limiting": True,
            "rag_integration": True,
            "parallel_tool_execution": True,
        },
        "context_config": CONTEXT_WINDOW_CONFIG,
    }


@app.post("/api/latest/mcp/discover")
async def mcp_discover():
    """Discover MCP servers."""
    from engine.latest_tech import get_mcp_manager
    mcp = get_mcp_manager()
    count = await mcp.discover()
    return {"servers_discovered": count, "total": len(mcp.servers), "servers": {k: {"command": v.command, "enabled": v.enabled} for k, v in mcp.servers.items()}}


@app.get("/api/latest/self-hosted")
async def self_hosted_models():
    """Discover self-hosted model endpoints."""
    from engine.latest_tech import get_self_hosted
    sh = get_self_hosted()
    models = await sh.discover()
    return {"models": [{"name": m.name, "provider": m.provider, "url": m.url, "healthy": m.healthy} for m in models]}


@app.post("/api/latest/rag/index")
async def rag_index(data: dict):
    """Index documents into RAG store."""
    documents = data.get("documents", [])
    from engine.latest_tech import get_rag
    rag = get_rag()
    count = await rag.index(documents)
    return {"indexed": count, "total": len(rag._store)}


@app.post("/api/latest/rag/search")
async def rag_search(query: str, top_k: int = 5):
    """Search RAG index."""
    from engine.latest_tech import get_rag
    rag = get_rag()
    results = await rag.search(query, top_k)
    return {"results": results, "count": len(results)}



# ── Bounty System Routes ────────────────────────────────────────────────

@app.get("/api/bounty/list")
async def bounty_list(status: str = "", category: str = "", hunter: str = ""):
    """List bounties with optional filters."""
    from engine.bounty import BountyBoard
    board = BountyBoard()
    bounties = await board.list_bounties(status, category, hunter)
    stats = await board.get_stats()
    return {"bounties": bounties[:50], "total": len(bounties), "stats": stats}


@app.post("/api/bounty/create")
async def bounty_create(title: str = "Untitled", description: str = "",
                         category: str = "feature", reward_amount: float = 0,
                         severity: str = "medium", created_by: str = "anonymous"):
    """Create a new bounty."""
    from engine.bounty import BountyBoard
    board = BountyBoard()
    b = await board.create_bounty(title, description, category, "vibe", reward_amount,
                                    created_by, severity)
    return {"id": b.id[:8], "title": b.title, "reward": f"{b.reward_amount} VIBE", "status": b.status}


@app.post("/api/bounty/claim")
async def bounty_claim(bounty_id: str, hunter: str):
    """Claim a bounty."""
    from engine.bounty import BountyBoard
    board = BountyBoard()
    success, msg = await board.claim_bounty(bounty_id, hunter)
    return {"success": success, "message": msg}


@app.post("/api/bounty/complete")
async def bounty_complete(bounty_id: str, hunter: str, notes: str = "", pr_url: str = ""):
    """Submit bounty completion."""
    from engine.bounty import BountyBoard
    board = BountyBoard()
    success, msg = await board.submit_completion(bounty_id, hunter, notes, pr_url)
    return {"success": success, "message": msg}


@app.get("/api/bounty/stats")
async def bounty_stats():
    """Get bounty board statistics."""
    from engine.bounty import BountyBoard
    board = BountyBoard()
    return await board.get_stats()


# ── Publisher Routes ────────────────────────────────────────────────────────

@app.post("/api/publish/chat")
async def publish_chat(title: str = "Pravidhi Neural Chat",
                        description: str = "Advanced AI ecosystem controller.",
                        app_id: str = "pravidhi-chat"):
    """Publish the Pravidhi Chat SPA to Anyclaw."""
    from engine.publisher import AppPublisher
    result = await AppPublisher.publish_chat_ui(title=title, description=description, app_id=app_id)
    if result.success:
        return {"success": True, "app_id": result.app_id, "claim_url": result.claim_url}
    return {"success": False, "error": result.error}


@app.get("/api/publish/apps")
async def list_published_apps():
    """List apps published via Anyclaw."""
    from engine.publisher import AppPublisher
    publisher = AppPublisher()
    apps = await publisher.list_apps()
    return {"apps": apps, "total": len(apps)}


# ── UltraWorker Routes ──────────────────────────────────────────────────────

@app.get("/api/ultraworker/status")
async def ultraworker_status():
    """Get ultraworker pool status."""
    from engine.ultraworker import get_pool
    return {"status": get_pool().get_status()}


@app.post("/api/ultraworker/pipeline")
async def ultraworker_pipeline(prompt: str, parallel: int = 3):
    """Run pipeline in parallel across multiple models."""
    from engine.ultraworker import get_pool
    pool = get_pool()
    if not pool._running:
        await pool.start(num_workers=parallel)
    result = await pool.run_parallel_pipeline(prompt, parallel)
    return result


@app.post("/api/ultraworker/chat")
async def ultraworker_chat(messages: List[Dict[str, Any]], parallel: int = 3):
    """Run chat in parallel across multiple models with fusion."""
    from engine.ultraworker import get_pool, WorkItem, WorkItemType
    pool = get_pool()
    if not pool._running:
        await pool.start(num_workers=parallel)
    item = WorkItem(type=WorkItemType.LLM_CHAT, payload={"messages": messages})
    fused = await pool.run_parallel(item, parallel)
    return {
        "type": "ultra_chat",
        "strategy": fused.strategy.value,
        "consensus_score": fused.consensus_score,
        "workers_used": fused.workers_used,
        "total_latency_ms": round(fused.total_latency_ms, 1),
        "content": fused.content,
        "primary_model": fused.primary.model if fused.primary else None,
    }


    logger.info("Pravidhi API server started")


@app.get("/health")
async def health():
    return {
        "status": "ok",
        "service": "pravidhi",
        "version": "0.1.0",
        "timestamp": time.time(),
    }


@app.get("/v1/models", response_model=ModelsResponse)
async def list_models():
    """List available models (OpenAI-compatible)."""
    from engine.provider_router import BUILTIN_PROVIDERS
    models = []
    now = int(time.time())
    for provider_name, info in BUILTIN_PROVIDERS.items():
        for model_name in info.get("models", {}):
            models.append(ModelInfo(
                id=f"{provider_name}/{model_name}",
                created=now,
            ))
    return ModelsResponse(data=models)


@app.post("/v1/chat/completions", response_model=ChatResponse)
async def chat_completions(request: ChatRequest):
    """Standard OpenAI Chat Completions endpoint with full tool access."""
    # Extract user message
    user_message = ""
    for msg in request.messages:
        if msg.role == "user":
            if isinstance(msg.content, str):
                user_message = msg.content
            elif isinstance(msg.content, list):
                texts = [p.get("text", "") for p in msg.content if "text" in p]
                user_message = " ".join(texts)

    if not user_message:
        raise HTTPException(status_code=400, detail="No user message found")

    # Run through Pravidhi pipeline
    pipeline = Pipeline()
    ctx = await pipeline.run(user_message)

    response_content = ""
    if ctx.final_output:
        response_content = ctx.final_output.get("content", str(ctx.final_output))
    if not response_content:
        response_content = "I processed your request through the Pravidhi pipeline."

    if ctx.errors:
        response_content += f"\n\n[Pipeline completed with {len(ctx.errors)} warnings]"

    return ChatResponse(
        id=f"pravidhi-{ctx.request_id}",
        created=int(ctx.start_time),
        model=request.model,
        choices=[
            ChatChoice(
                index=0,
                message=ChatMessage(role="assistant", content=response_content),
                finish_reason="stop",
            )
        ],
        usage=ChatUsage(total_tokens=len(user_message.split()) + len(response_content.split())),
    )


# ── Standalone Runner ────────────────────────────────────────────────────────

def start_server(host: str = "127.0.0.1", port: int = 8642):
    """Start the API server with uvicorn."""
    import uvicorn
    logger.info(f"Starting Pravidhi API server on http://{host}:{port}")
    uvicorn.run(app, host=host, port=port, log_level="info")
