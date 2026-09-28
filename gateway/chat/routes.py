"""FastAPI routes & WebSocket for the Chat Control UI.

Endpoints:
- POST /api/chat/sessions — Create session
- GET /api/chat/sessions — List sessions
- GET /api/chat/sessions/{id} — Get session
- DELETE /api/chat/sessions/{id} — Delete session
- GET /api/chat/sessions/{id}/history — Get message history
- WS /api/chat/ws/{session_id} — WebSocket for streaming chat
- GET /chat — Serve the chat SPA
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, FastAPI, HTTPException, Query, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

from gateway.chat.manager import ChatManager, MessageRole

logger = logging.getLogger("pravidhi.chat.routes")

# Global chat manager
_chat_manager: Optional[ChatManager] = None


def get_chat_manager() -> ChatManager:
    global _chat_manager
    if _chat_manager is None:
        _chat_manager = ChatManager()
    return _chat_manager


# ── Pydantic Models ──────────────────────────────────────────────────────────

class CreateSessionRequest(BaseModel):
    settings: Optional[Dict[str, Any]] = None


class MessageRequest(BaseModel):
    text: str
    session_id: Optional[str] = None


# ── Router ───────────────────────────────────────────────────────────────────

router = APIRouter(prefix="/api/chat", tags=["chat"])


@router.post("/sessions")
async def create_session(req: Optional[CreateSessionRequest] = None):
    """Create a new chat session."""
    manager = get_chat_manager()
    settings = req.settings if req else None
    # Map frontend camelCase keys to backend snake_case
    if settings:
        key_map = {
            "maxTokens": "max_tokens",
            "systemPrompt": "system_prompt",
            "autoRotate": "auto_rotate",
            "opencodeUrl": "opencode_url",
            "routerUrl": "router_url",
        }
        for front_key, back_key in key_map.items():
            if front_key in settings:
                settings[back_key] = settings.pop(front_key)
    session = manager.create_session(settings)
    return {
        "session_id": session.id,
        "created_at": session.created_at,
        "message": "Chat session created",
    }


@router.get("/sessions")
async def list_sessions():
    """List all active chat sessions."""
    manager = get_chat_manager()
    return {"sessions": manager.list_sessions()}


@router.get("/sessions/{session_id}")
async def get_session(session_id: str):
    """Get session details."""
    manager = get_chat_manager()
    session = manager.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    return {
        "session_id": session.id,
        "created_at": session.created_at,
        "updated_at": session.updated_at,
        "message_count": len(session.messages),
        "settings": session.settings,
    }


@router.delete("/sessions/{session_id}")
async def delete_session(session_id: str):
    """Delete a chat session."""
    manager = get_chat_manager()
    if manager.delete_session(session_id):
        return {"status": "deleted", "session_id": session_id}
    raise HTTPException(status_code=404, detail="Session not found")


@router.get("/sessions/{session_id}/history")
async def get_history(session_id: str, limit: int = Query(50, ge=1, le=200)):
    """Get message history for a session."""
    manager = get_chat_manager()
    history = manager.get_history(session_id, limit)
    return {"session_id": session_id, "messages": history, "total": len(history)}


# ── WebSocket for Streaming Chat ─────────────────────────────────────────────

@router.websocket("/ws/{session_id}")
async def chat_websocket(websocket: WebSocket, session_id: str):
    """WebSocket endpoint for streaming chat responses."""
    await websocket.accept()
    manager = get_chat_manager()

    # Create session if it doesn't exist
    session = manager.get_session(session_id)
    if not session:
        session = manager.create_session()
        session_id = session.id
        await websocket.send_json({
            "type": "session_created",
            "session_id": session_id,
        })

    try:
        while True:
            # Receive message from client
            data = await websocket.receive_json()
            text = data.get("text", "").strip()
            action = data.get("action", "message")

            if action == "message" and text:
                # Process and stream response
                async for chunk in manager.process_message(session_id, text):
                    await websocket.send_json(chunk)
                    await asyncio.sleep(0.05)  # Small delay for streaming feel

            elif action == "clear":
                # Clear session history
                session.messages = [session.messages[0]] if session.messages else []
                await websocket.send_json({"type": "cleared"})

            elif action == "settings":
                # Update settings with key mapping (camelCase → snake_case)
                if "settings" in data:
                    raw = data["settings"]
                    # Map frontend camelCase keys to backend snake_case
                    key_map = {
                        "maxTokens": "max_tokens",
                        "systemPrompt": "system_prompt",
                        "autoRotate": "auto_rotate",
                        "opencodeUrl": "opencode_url",
                        "routerUrl": "router_url",
                    }
                    for front_key, back_key in key_map.items():
                        if front_key in raw:
                            raw[back_key] = raw.pop(front_key)
                    session.settings.update(raw)
                    await websocket.send_json({"type": "settings_updated", "settings": session.settings})

            elif action == "ping":
                await websocket.send_json({"type": "pong"})

    except WebSocketDisconnect:
        logger.debug(f"WebSocket disconnected: {session_id}")
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
        try:
            await websocket.send_json({"type": "error", "content": str(e)})
        except Exception:
            pass


# ── Mount to App ──────────────────────────────────────────────────────────────

def mount_chat_ui(app: FastAPI):
    """Mount chat control UI routes and serve the SPA."""
    app.include_router(router)

    # Serve the chat SPA
    from pathlib import Path as _Path
    chat_static = _Path(__file__).parent / "static"
    chat_static.mkdir(parents=True, exist_ok=True)
    html_file = chat_static / "index.html"

    if html_file.exists():
        html_content = html_file.read_text()
    else:
        html_content = _generate_chat_html()

    @app.get("/chat", response_class=HTMLResponse, include_in_schema=False)
    async def serve_chat_ui():
        """Serve the Chat Control UI SPA."""
        return HTMLResponse(content=html_content)

    logger.info("Chat Control UI mounted at /chat")


def _generate_chat_html() -> str:
    """Return the chat SPA HTML with embedded CSS/JS."""
    return Path(__file__).parent / "static" / "index.html"
