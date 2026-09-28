"""Pravidhi configuration loader — multi-layer merge system.

Layers (increasing priority):
1. pravidhi.yaml (package defaults)
2. ~/.pravidhi/pravidhi.yaml (user config)
3. ./.pravidhi.yaml (project-local overrides)
4. Environment variables (PRAVIDHI_*)
5. CLI flags
"""

import os
from pathlib import Path
from typing import Any, Dict, Optional
import yaml
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings


# ── Schema Models ─────────────────────────────────────────────────────────────

class ValidationConfig(BaseModel):
    schema_enabled: bool = True
    behavioral: bool = True
    regression: bool = True
    test_suite: bool = True


class PipelineConfig(BaseModel):
    stages: list[str] = [
        "ingest", "validate_input", "decompose",
        "route", "execute", "validate_output", "learn",
    ]
    enabled: bool = True


class CheckpointConfig(BaseModel):
    enabled: bool = True
    auto_snapshot: bool = True
    max_snapshots: int = 50


class EngineConfig(BaseModel):
    name: str = "pravidhi"
    version: str = "0.1.0"
    description: str = ""
    pipeline: PipelineConfig = PipelineConfig()
    validation: ValidationConfig = ValidationConfig()
    checkpoint: CheckpointConfig = CheckpointConfig()


class RoutingConfig(BaseModel):
    sort: str = "price"
    only: list[str] = []
    ignore: list[str] = []
    order: list[str] = []
    require_parameters: bool = False


class FallbackConfig(BaseModel):
    enabled: bool = True
    max_retries: int = 3


class CredentialPoolConfig(BaseModel):
    enabled: bool = True
    strategy: str = "round_robin"


class ProviderConfig(BaseModel):
    default_model: str = "gpt-5.4-mini"
    routing: RoutingConfig = RoutingConfig()
    fallback: FallbackConfig = FallbackConfig()
    credential_pools: CredentialPoolConfig = CredentialPoolConfig()
    credentials: dict[str, str] = {}


class CronDeliveryConfig(BaseModel):
    default: str = "file"
    retry_attempts: int = 3
    retry_delay: int = 60


class CronJobConfig(BaseModel):
    name: str
    schedule: str
    mode: str = "agent"  # agent | no-agent
    prompt: str = ""
    command: str = ""
    skill: str = ""
    delivery: str = "file"


class CronSchedulerConfig(BaseModel):
    poll_interval: int = 15
    max_concurrent: int = 10
    timezone: str = "UTC"


class CronConfig(BaseModel):
    enabled: bool = True
    daemonize: bool = True
    database: str = "~/.pravidhi/cron.db"
    scheduler: CronSchedulerConfig = CronSchedulerConfig()
    delivery: CronDeliveryConfig = CronDeliveryConfig()
    jobs: list[CronJobConfig] = []


class TrainingLoopConfig(BaseModel):
    max_history: int = 100
    convergence_threshold: float = 0.95
    min_epochs: int = 3
    max_epochs: int = 10


class SkillGenerationConfig(BaseModel):
    enabled: bool = True
    output_dir: str = "~/.codex/skills/"
    from_mistakes: bool = True
    from_successes: bool = True
    from_requests: bool = True


class ExperienceDBConfig(BaseModel):
    enabled: bool = True
    backend: str = "json"
    path: str = "~/.pravidhi/experience/"
    indexing: str = "keyword"


class ResearchConfig(BaseModel):
    enabled: bool = True
    cycle_interval: int = 3600
    training_loop: TrainingLoopConfig = TrainingLoopConfig()
    skill_generation: SkillGenerationConfig = SkillGenerationConfig()
    experience_db: ExperienceDBConfig = ExperienceDBConfig()


class APIServerConfig(BaseModel):
    host: str = "127.0.0.1"
    port: int = 8642
    cors_origins: list[str] = ["http://localhost:3000"]


class TransportConfig(BaseModel):
    cli: bool = True
    api: bool = True
    telegram: bool = False
    discord: bool = False


class GatewayConfig(BaseModel):
    enabled: bool = True
    api_server: APIServerConfig = APIServerConfig()
    transports: TransportConfig = TransportConfig()


class MCPServerEntry(BaseModel):
    command: str = ""
    args: list[str] = []
    enabled: bool = False


class MCPConfig(BaseModel):
    servers: dict[str, MCPServerEntry] = {}


class WorkingMemoryConfig(BaseModel):
    enabled: bool = True
    max_chars: int = 2200
    file: str = "~/.pravidhi/memory.md"


class UserProfileConfig(BaseModel):
    enabled: bool = True
    max_chars: int = 1375
    file: str = "~/.pravidhi/user.md"


class LongTermMemoryConfig(BaseModel):
    enabled: bool = True
    backend: str = "json"
    path: str = "~/.pravidhi/long-term/"


class MemoryConfig(BaseModel):
    working: WorkingMemoryConfig = WorkingMemoryConfig()
    user_profile: UserProfileConfig = UserProfileConfig()
    long_term: LongTermMemoryConfig = LongTermMemoryConfig()


class ContextConfig(BaseModel):
    auto_discover: bool = True
    files: list[str] = [
        "pravidhi.md", "AGENTS.md", "DESIGN.md", "CLAUDE.md", "SOUL.md", ".cursorrules",
    ]
    merge_strategy: str = "deepest_first"


class PersonalityConfig(BaseModel):
    primary: str = "pravidhi"
    skin: str = "default"
    style: str = "concise"


class PravidhiConfig(BaseModel):
    engine: EngineConfig = EngineConfig()
    providers: ProviderConfig = ProviderConfig()
    cron: CronConfig = CronConfig()
    research: ResearchConfig = ResearchConfig()
    gateway: GatewayConfig = GatewayConfig()
    mcp: MCPConfig = MCPConfig()
    memory: MemoryConfig = MemoryConfig()
    context: ContextConfig = ContextConfig()
    personality: PersonalityConfig = PersonalityConfig()


# ── Config Loader ─────────────────────────────────────────────────────────────

DEFAULT_SEARCH_PATHS = [
    Path(__file__).parent.parent / "pravidhi.yaml",
    Path.home() / ".pravidhi" / "pravidhi.yaml",
    Path.cwd() / "pravidhi.yaml",
]

ENV_PREFIX = "PRAVIDHI_"


class PravidhiSettings(BaseSettings):
    """Settings that can be overridden via environment variables."""
    model_config = {"env_prefix": ENV_PREFIX, "case_sensitive": False}

    config_path: Optional[str] = None
    verbose: bool = False
    log_level: str = "INFO"


def load_config(search_paths: Optional[list[Path]] = None) -> PravidhiConfig:
    """Load and merge config from YAML files, env vars, and defaults."""
    paths = search_paths or DEFAULT_SEARCH_PATHS
    raw: Dict[str, Any] = {}

    for path in paths:
        expanded = Path(str(path).replace("~", str(Path.home())))
        if expanded.exists():
            with open(expanded) as f:
                file_data = yaml.safe_load(f)
                if file_data:
                    raw = _deep_merge(raw, file_data)

    return PravidhiConfig(**raw)


def _deep_merge(base: Dict, override: Dict) -> Dict:
    """Deep merge two dicts (override wins)."""
    result = dict(base)
    for key, val in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(val, dict):
            result[key] = _deep_merge(result[key], val)
        else:
            result[key] = val
    return result


# Singleton
_config: Optional[PravidhiConfig] = None


def get_config() -> PravidhiConfig:
    global _config
    if _config is None:
        _config = load_config()
    return _config


def reload_config() -> PravidhiConfig:
    global _config
    _config = load_config()
    return _config
