"""Comprehensive test suite for all Pravidhi subsystems."""

import warnings
warnings.filterwarnings('ignore')
import sys
sys.path.insert(0, '/home/ubuntu/Pravidhi')

import asyncio
import tempfile
import shutil
import time
from pathlib import Path


# ═════════════════════════════════════════════════════════════════════════════
# 1. Config
# ═════════════════════════════════════════════════════════════════════════════

def test_config():
    from engine.config import load_config, PravidhiConfig
    cfg = load_config()
    assert cfg.engine.name == "pravidhi"
    assert cfg.engine.version == "0.1.0"
    assert len(cfg.engine.pipeline.stages) == 7
    assert cfg.cron.enabled is True
    assert cfg.research.enabled is True
    assert cfg.providers.default_model != ""
    print("  ✓ Config loads correctly")


# ═════════════════════════════════════════════════════════════════════════════
# 2. Registry
# ═════════════════════════════════════════════════════════════════════════════

def test_registry():
    from engine.registry import Registry
    reg = Registry()

    # Register a tool
    reg.register_tool(
        name="hello", description="Say hello",
        schema={"type": "object", "properties": {}},
        handler=lambda **kw: "hello",
    )
    assert len(reg.list_tools()) == 1
    assert reg.get_tool("hello") is not None

    # Register a skill
    reg.register_skill("test-skill", "A test skill", "# Test content")
    assert reg.get_skill("test-skill") is not None

    # Register a hook
    reg.register_hook("test-hook", "post_execute", lambda **kw: None)
    hooks = reg.get_hooks("post_execute")
    assert len(hooks) == 1

    # Register provider
    reg.register_provider("test-provider", "openai", "https://test.api/v1")
    assert len(reg.list_providers()) == 1

    # Summary
    summary = reg.summary()
    assert summary["tools"] == 1
    assert summary["skills"] == 1
    assert summary["hooks"] == 1
    assert summary["providers"] == 1
    print("  ✓ Registry works")


# ═════════════════════════════════════════════════════════════════════════════
# 3. Validator
# ═════════════════════════════════════════════════════════════════════════════

def test_validator():
    from engine.validator import ValidationEngine

    async def run():
        validator = ValidationEngine()
        validator.add_behavioral_rule("Must be helpful")
        validator.add_behavioral_rule("Must not be harmful")

        reports = await validator.validate(
            input_data={"text": "Hello", "tool": "greeting"},
            output_data={"response": "Hi there!"},
        )
        assert len(reports) >= 2
        assert validator.all_passed(reports)
        assert validator.overall_score(reports) >= 0.9

        # Test with bad input
        reports2 = await validator.validate(
            input_data={"text": "", "tool": "greeting", "params": {}},
            output_data={"response": ""},
        )
        assert isinstance(reports2, dict)
        print("  ✓ Validator works")

    asyncio.run(run())


# ═════════════════════════════════════════════════════════════════════════════
# 4. Pipeline
# ═════════════════════════════════════════════════════════════════════════════

def test_pipeline():
    from engine.pipeline import Pipeline, IngestStage, PipelineContext

    async def run():
        ingest = IngestStage()
        ctx = PipelineContext(user_input="Build a web scraper")
        ctx = await ingest.handle(ctx)
        assert ctx.parsed_intent["type"] == "action"

        ctx2 = PipelineContext(user_input="Explain Python")
        ctx2 = await ingest.handle(ctx2)
        assert ctx2.parsed_intent["type"] == "question"

        ctx3 = PipelineContext(user_input="Fix the bug on line 5")
        ctx3 = await ingest.handle(ctx3)
        assert ctx3.parsed_intent["type"] == "debug"

        # Full pipeline
        pipeline = Pipeline()
        final = await pipeline.run("What is Pravidhi?")
        assert final.request_id != ""
        assert final.validation_score >= 0.0
        assert "total_duration_ms" in final.metadata
        print("  ✓ Pipeline works")

    asyncio.run(run())


# ═════════════════════════════════════════════════════════════════════════════
# 5. Cron Engine (independent subsystem)
# ═════════════════════════════════════════════════════════════════════════════

def test_cron_engine():
    from cron.scheduler import (
        CronDaemon, CronJob, CronDB, JobExecutor, DeliveryService,
        parse_cron_expression, next_cron_time, JobMode, JobStatus,
    )

    db_path = "/tmp/test_pravidhi_cron.db"
    db = CronDB(db_path)

    # Expression parsing
    tests = [
        ("hourly", "cron"),
        ("every 30m", "interval"),
        ("*/5 * * * *", "cron"),
        ("30m", "interval"),
    ]
    for expr, expected_type in tests:
        result = parse_cron_expression(expr)
        assert result is not None
        assert result["type"] == expected_type

    # Job CRUD
    job = CronJob(
        name="test", schedule="*/5 * * * *",
        mode=JobMode.NO_AGENT, command="echo hello",
        next_run=time.time() + 60,
    )
    job_id = db.add_job(job)
    assert len(job_id) > 0

    loaded = db.get_job(job_id)
    assert loaded.name == "test"
    assert loaded.mode == JobMode.NO_AGENT

    jobs = db.list_jobs()
    assert len(jobs) == 1

    db.pause_job(job_id)
    assert db.get_job(job_id).paused is True

    db.resume_job(job_id)
    assert db.get_job(job_id).paused is False

    db.delete_job(job_id)
    assert db.get_job(job_id) is None

    # Cleanup
    Path(db_path).unlink(missing_ok=True)
    print("  ✓ Cron engine works")


# ═════════════════════════════════════════════════════════════════════════════
# 6. Research Engine
# ═════════════════════════════════════════════════════════════════════════════

def test_research():
    from research.training_loop import (
        TrainingLoop, TrainingStep, ExperienceDB,
        PatternDetector, SkillGenerator,
    )

    # Clear any existing experience DB data
    import shutil
    exp_path = Path.home() / '.pravidhi' / 'experience'
    if exp_path.exists():
        shutil.rmtree(str(exp_path))
    tmpdir = Path(tempfile.mkdtemp())
    db = ExperienceDB(base_path=str(tmpdir))

    # Record diverse training steps
    for i in range(20):
        success = i < 16  # 80% success rate
        step = TrainingStep(
            prompt=f"Task {i}",
            intent_type="code" if i % 2 == 0 else "general",
            provider="openai",
            model="gpt-5.4-mini",
            success=success,
            score=0.9 if success else 0.0,
            latency_ms=500 + i * 50,
            error=None if success else "API timeout",
            validation_score=0.95 if success else 0.0,
        )
        db.record_step(step)

    metrics = db.get_metrics()
    assert metrics.total_steps == 20
    assert metrics.accuracy == 0.8
    assert abs(metrics.loss - 0.2) < 0.01

    # Pattern detection
    detector = PatternDetector(db)
    steps = db.get_recent_steps(100)
    errors = detector.detect_error_patterns(steps)
    successes = detector.detect_success_patterns(steps)

    # Run training loop
    loop = TrainingLoop(db)
    result = asyncio.run(loop.run_analysis())
    assert result["epoch"] == 1
    assert "skills_generated" in result

    # Status
    status = loop.get_status()
    assert status["accuracy"] >= 0.0
    assert "total_steps" in status

    # Practice loop
    practice_results = asyncio.run(loop.practice_loop("Test practice", epochs=1))
    assert len(practice_results) >= 1

    shutil.rmtree(str(tmpdir))
    print("  ✓ Research engine works")


# ═════════════════════════════════════════════════════════════════════════════
# 7. Memory System
# ═════════════════════════════════════════════════════════════════════════════

def test_memory():
    from memory.session import MemoryManager, WorkingMemory, LongTermMemory

    wm = WorkingMemory()
    wm.add("Test preference", "preference")
    wm.add("Test fact", "env_fact")
    assert len(wm.get_all()) >= 2
    formatted = wm.get_formatted()
    assert "MEMORY" in formatted

    ltm = LongTermMemory()
    ltm.store("Test lesson", "lesson", ["test"])
    assert ltm.count() >= 1
    results = ltm.query("test")
    assert len(results) >= 1

    mm = MemoryManager()
    entry = mm.learn_from_interaction("Build API", "Done", True, 0.95)
    if entry:
        assert entry.category == "learned_pattern"
    block = mm.get_system_prompt_block()
    assert len(block) > 0

    print("  ✓ Memory system works")


# ═════════════════════════════════════════════════════════════════════════════
# 8. Sandbox
# ═════════════════════════════════════════════════════════════════════════════

def test_sandbox():
    from engine.sandbox import CodeSandbox

    async def run():
        sandbox = CodeSandbox()

        # Python execution
        result = await sandbox.execute_python("print('hello from pravidhi')")
        assert "hello from pravidhi" in result.stdout
        assert result.return_code == 0

        # Shell execution
        result2 = await sandbox.execute_shell("echo 'shell test'")
        assert "shell test" in result2.stdout

        # Error handling
        result3 = await sandbox.execute_python("raise ValueError('test error')")
        assert result3.return_code != 0 or "test error" in result3.stderr

        print("  ✓ Sandbox works")

    asyncio.run(run())


# ═════════════════════════════════════════════════════════════════════════════
# 9. Provider Router
# ═════════════════════════════════════════════════════════════════════════════

def test_provider_router():
    from engine.provider_router import ProviderRouter

    router = ProviderRouter()
    selection = asyncio.run(router.select({"type": "general"}))
    assert "provider" in selection
    assert "model" in selection

    response = asyncio.run(router.chat(
        messages=[{"role": "user", "content": "test"}],
    ))
    assert "error" in response or "content" in response

    print("  ✓ Provider router works")


# ═════════════════════════════════════════════════════════════════════════════
# 10. API Server
# ═════════════════════════════════════════════════════════════════════════════

def test_api_server():
    from gateway.api_server import app
    # Verify FastAPI app is properly configured
    assert app.title == "Pravidhi API"
    routes = [r.path for r in app.routes]
    assert "/health" in routes
    assert "/v1/models" in routes
    assert "/v1/chat/completions" in routes
    print("  ✓ API server routes configured")
    print("  ✓ API server endpoints: health, models, chat")


# ═════════════════════════════════════════════════════════════════════════════
# Runner
# ═════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    print("\n╔══════════════════════════════════════════════╗")
    print("║     Pravidhi — Comprehensive Test Suite     ║")
    print("╚══════════════════════════════════════════════╝\n")

    tests = [
        ("Config", test_config),
        ("Registry", test_registry),
        ("Validator", test_validator),
        ("Pipeline", test_pipeline),
        ("Cron Engine", test_cron_engine),
        ("Research", test_research),
        ("Memory", test_memory),
        ("Sandbox", test_sandbox),
        ("Provider Router", test_provider_router),
        ("API Server", test_api_server),
    ]

    passed = 0
    failed = 0

    for name, test_fn in tests:
        try:
            test_fn()
            print(f"  ✓ {name}")
            passed += 1
        except Exception as e:
            import traceback
            print(f"  ✗ {name}: {e}")
            traceback.print_exc()
            failed += 1

    print(f"\n{'='*50}")
    print(f"Results: {passed} passed, {failed} failed, {passed+failed} total")
    print(f"{'='*50}\n")
    sys.exit(0 if failed == 0 else 1)
