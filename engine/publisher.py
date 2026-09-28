"""OpenClaw Web App Publisher — Build & deploy Pravidhi apps to Anyclaw hosting.

Capabilities:
- Package any web app directory into a deployable ZIP
- Deploy to Anyclaw production (https://anyclaw.store)
- List deployed apps
- Generate app.json manifests, icons, screenshots
"""

from __future__ import annotations

import base64
import json
import logging
import os
import shutil
import tempfile
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

import httpx

logger = logging.getLogger("pravidhi.publisher")

# ── Config ───────────────────────────────────────────────────────────────────

ANYCLAW_PRODUCTION_URL = "https://anyclaw.store"
ANYCLAW_LOCAL_URL = "http://localhost:3000"

DEFAULT_CATEGORIES = [
    "Productivity", "Developer Tools", "AI", "Chat",
    "Security", "Data", "Analytics", "Education",
    "Entertainment", "Business", "Other",
]

APP_TYPES = ["web_app", "website", "game"]


@dataclass
class AppManifest:
    """Application metadata matching Anyclaw's app.json schema."""
    title: str
    description: str
    category: str = "Developer Tools"
    icon: str = "icon.svg"
    screenshots: List[str] = field(default_factory=list)
    version: str = "1.0.0"
    author: str = "Pravidhi"


@dataclass
class DeployResult:
    """Result of an Anyclaw deployment."""
    app_id: str
    claim_url: str
    claim_token: str
    success: bool = True
    error: str = ""


class AppPublisher:
    """Package and deploy web apps to Anyclaw hosting."""

    def __init__(self, base_url: str = ANYCLAW_PRODUCTION_URL):
        self.base_url = base_url

    async def deploy_app(
        self,
        app_dir: str | Path,
        app_id: str,
        app_type: str = "web_app",
        site_map: Optional[List[str]] = None,
        manifest: Optional[AppManifest] = None,
    ) -> DeployResult:
        """Package a directory and deploy to Anyclaw."""
        app_dir = Path(app_dir)
        if not app_dir.exists():
            return DeployResult(app_id=app_id, claim_url="", claim_token="",
                                success=False, error=f"Directory not found: {app_dir}")

        # Create ZIP
        zip_path = await self._create_zip(app_dir, manifest)
        if not zip_path:
            return DeployResult(app_id=app_id, claim_url="", claim_token="",
                                success=False, error="Failed to create ZIP")

        # Encode and deploy
        try:
            with open(zip_path, "rb") as f:
                zip_b64 = base64.b64encode(f.read()).decode("utf-8")

            async with httpx.AsyncClient(timeout=60) as client:
                payload = {
                    "app_id": app_id,
                    "zip_b64": zip_b64,
                    "app_type": app_type,
                }
                if site_map:
                    payload["site_map"] = site_map

                resp = await client.post(
                    f"{self.base_url}/api/deploy",
                    json=payload,
                )
                if resp.status_code == 200:
                    data = resp.json()
                    result = DeployResult(
                        app_id=data.get("app_id", app_id),
                        claim_url=data.get("claim_url", ""),
                        claim_token=data.get("claim_token", ""),
                    )
                    logger.info(f"Deployed {app_id} → {result.claim_url}")
                else:
                    result = DeployResult(
                        app_id=app_id, claim_url="", claim_token="",
                        success=False,
                        error=f"Deploy failed ({resp.status_code}): {resp.text[:500]}",
                    )
        except Exception as e:
            result = DeployResult(
                app_id=app_id, claim_url="", claim_token="",
                success=False, error=str(e),
            )
        finally:
            # Cleanup
            if zip_path.exists():
                zip_path.unlink()

        return result

    async def list_apps(self) -> List[Dict[str, Any]]:
        """List deployed apps from Anyclaw."""
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                resp = await client.get(f"{self.base_url}/api/apps")
                if resp.status_code == 200:
                    return resp.json().get("apps", [])
                return []
        except Exception as e:
            logger.error(f"Failed to list apps: {e}")
            return []

    async def _create_zip(self, app_dir: Path, manifest: Optional[AppManifest] = None) -> Optional[Path]:
        """Create a ZIP file from an app directory with required assets."""
        tmp_dir = Path(tempfile.mkdtemp(prefix="pravidhi_app_"))
        zip_path = tmp_dir / "app.zip"

        try:
            with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
                # Add all files from app directory
                for file_path in app_dir.rglob("*"):
                    if file_path.is_file() and file_path.name != ".gitkeep":
                        arcname = str(file_path.relative_to(app_dir))
                        zf.write(file_path, arcname)

                # Add/update app.json
                if manifest:
                    app_json_data = {
                        "title": manifest.title,
                        "description": manifest.description,
                        "category": manifest.category,
                        "icon": manifest.icon,
                        "version": manifest.version,
                        "author": manifest.author,
                    }
                    if manifest.screenshots:
                        app_json_data["screenshots"] = manifest.screenshots
                    zf.writestr("app.json", json.dumps(app_json_data, indent=2))

                # Generate SVG icon if none exists
                has_icon = any(
                    p.name in ("icon.svg", "icon.png") or p.name.startswith("icon.")
                    for p in app_dir.iterdir()
                )
                if not has_icon:
                    svg_icon = self._generate_icon(app_id=app_dir.name)
                    zf.writestr("icon.svg", svg_icon)

            return zip_path
        except Exception as e:
            logger.error(f"ZIP creation failed: {e}")
            if zip_path.exists():
                zip_path.unlink()
            return None

    def _generate_icon(self, app_id: str = "app") -> str:
        """Generate a vibrant SVG icon for the app."""
        colors = ["#6366f1", "#8b5cf6", "#a855f7", "#3b82f6", "#06b6d4"]
        color = colors[hash(app_id) % len(colors)]
        letter = app_id[0].upper() if app_id else "A"
        return f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100">
  <rect width="100" height="100" rx="20" fill="{color}"/>
  <text x="50" y="68" font-family="system-ui,sans-serif" font-size="52"
        font-weight="bold" fill="white" text-anchor="middle">{letter}</text>
</svg>'''

    @staticmethod
    async def publish_chat_ui(
        api_base_url: str = "",
        title: str = "Pravidhi Neural Chat",
        description: str = "Advanced AI ecosystem controller with pipeline execution, pentesting, reverse engineering, research, and more.",
        app_id: str = "pravidhi-chat",
    ) -> DeployResult:
        """Build and publish the Pravidhi Chat SPA as a standalone web app."""
        chat_static = Path(__file__).parent.parent / "gateway" / "chat" / "static"
        if not chat_static.exists():
            return DeployResult(app_id=app_id, claim_url="", claim_token="",
                                success=False, error="Chat static directory not found")

        publisher = AppPublisher()
        manifest = AppManifest(
            title=title,
            description=description,
            category="AI",
            version="0.1.0",
            author="Pravidhi",
        )

        return await publisher.deploy_app(
            app_dir=chat_static,
            app_id=app_id,
            app_type="web_app",
            site_map=["/"],
            manifest=manifest,
        )


# ── Global Singleton ─────────────────────────────────────────────────────────

_publisher: Optional[AppPublisher] = None


def get_publisher() -> AppPublisher:
    global _publisher
    if _publisher is None:
        _publisher = AppPublisher()
    return _publisher
