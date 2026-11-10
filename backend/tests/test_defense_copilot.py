"""Unit tests for Phase 8F Academic Thesis Defense Co-Pilot & Mock Panelist Mode."""
import asyncio
from pathlib import Path

from backend.config import Settings
from backend.core.actions import Registry
from backend.core.clearance import ClearanceManager, LEVEL_5
from backend.core.llm import NoLLMProvider
from backend.core.orchestrator import Orchestrator
from backend.core.router import route
from backend.tools.audit import Audit
from backend.tools.defense_copilot import DefenseCoPilot


def _make_orch(tmp_path: Path):
    desktop = tmp_path / "desktop"
    desktop.mkdir(exist_ok=True)
    db_path = tmp_path / "n.db"
    apps_file = tmp_path / "apps.json"
    apps_file.write_text('{"apps": {}, "tasks": {}}')
    settings = Settings(
        desktop_root=desktop,
        api_token="t" * 32,
        db_path=db_path,
        apps_file=apps_file,
    )
    registry = Registry({"apps": {}, "tasks": {}})
    clearance = ClearanceManager()
    audit = Audit(db_path)
    orch = Orchestrator(
        settings=settings,
        provider=NoLLMProvider(),
        registry=registry,
        audit=audit,
        clearance=clearance,
    )
    return orch, settings, registry, audit, clearance


def test_defense_session_lifecycle(tmp_path):
    copilot = DefenseCoPilot()
    ppt = tmp_path / "TitleHearing.pptx"
    ppt.write_bytes(b"dummy")

    # Start
    sess = copilot.start_session(ppt, total_slides=10, target_duration_s=720)
    assert sess.active_slide == 1
    assert sess.elapsed_seconds >= 0

    # Advance
    copilot.advance_slide(2)
    assert copilot.current_session.active_slide == 2
    assert 2 in copilot.current_session.slide_timestamps

    # Pacing
    pacing = copilot.get_pacing_status()
    assert pacing["status"] == "on_pace"
    assert pacing["slide"] == 2

    # Question
    q = copilot.generate_panelist_question(slide_topic="Methodology", slide_text="AST and return-trip validation")
    assert isinstance(q, str)
    assert len(q) > 20
    assert len(copilot.current_session.questions_asked) == 1

    # Stop
    summary = copilot.stop_session()
    assert summary["slides_count"] >= 1
    assert summary["questions_count"] == 1
    assert copilot.current_session is None


def test_question_generator_topics():
    copilot = DefenseCoPilot()

    q_meth = copilot.generate_panelist_question(slide_topic="Algorithm and Methodology")
    assert any(term in q_meth.lower() for term in ["methodology", "return-trip", "ast", "objective", "graph"])

    q_sec = copilot.generate_panelist_question(slide_topic="3-Tier Security Clearance and FastAPI")
    assert any(term in q_sec.lower() for term in ["clearance", "security", "fastapi", "tier", "architecture"])


def test_audit_defense_sessions(tmp_path):
    audit = Audit(tmp_path / "audit.db")

    row_id = audit.add_defense_session(
        presentation_name="TitleHearing.pptx",
        duration_seconds=650,
        slides_count=10,
        questions_count=4,
        pacing_summary="On Pace",
    )
    assert row_id > 0

    sessions = audit.list_defense_sessions(limit=5)
    assert len(sessions) == 1
    assert sessions[0]["presentation_name"] == "TitleHearing.pptx"
    assert sessions[0]["duration_seconds"] == 650
    assert sessions[0]["questions_count"] == 4


def test_router_defense_intents(tmp_path):
    _, settings, registry, _, _ = _make_orch(tmp_path)

    for p in ["start defense rehearsal", "activate defense mode", "start mock defense", "begin thesis rehearsal"]:
        intent = route(p, settings, registry)
        assert intent.kind == "defense_start", f"Failed for '{p}', got {intent.kind}"

    for p in ["stop defense rehearsal", "stop defense mode", "end defense rehearsal", "finish rehearsal"]:
        intent = route(p, settings, registry)
        assert intent.kind == "defense_stop", f"Failed for '{p}', got {intent.kind}"

    for p in ["ask defense question", "panelist question", "ask me a defense question", "panelist interrogation"]:
        intent = route(p, settings, registry)
        assert intent.kind == "defense_question", f"Failed for '{p}', got {intent.kind}"

    for p in ["defense timing", "how is my defense pace", "rehearsal timing"]:
        intent = route(p, settings, registry)
        assert intent.kind == "defense_status", f"Failed for '{p}', got {intent.kind}"


def test_orchestrator_defense_flow_and_clearance(tmp_path):
    orch, settings, _, audit, clearance = _make_orch(tmp_path)

    # 1. Remote read-only: defense_start blocked
    rep_ro = asyncio.run(orch.handle("start defense rehearsal", session="s_test", readonly=True))
    assert not rep_ro.ok
    assert "read-only" in rep_ro.text.lower()

    # Create dummy presentation
    ppt = tmp_path / "desktop" / "TitleHearing.pptx"
    ppt.write_bytes(b"dummy_ppt_content")
    orch._last_ppt_path = ppt

    # 2. Defense Start (Local Level 5 authorized)
    # Note: open_ppt_at_slide won't find COM in headless pytest, but orchestrator handles error gracefully
    rep_start = asyncio.run(orch.handle("start defense rehearsal", session="s_test"))
    assert rep_start.intent == "defense_start"
    # Even if COM fails in CI, intent routes cleanly
    if rep_start.ok:
        assert "Thesis defense rehearsal activated" in rep_start.text

    # 3. Defense Question (Level 1 allowed)
    rep_q = asyncio.run(orch.handle("ask defense question", session="s_test"))
    assert rep_q.intent == "defense_question"
    assert rep_q.ok
    assert "Panelist interrogation" in rep_q.text

    # 4. Defense Status (Level 1 allowed)
    # If session was started:
    if orch.defense_copilot.current_session:
        rep_stat = asyncio.run(orch.handle("defense timing", session="s_test"))
        assert rep_stat.intent == "defense_status"
        assert rep_stat.ok
        assert "rehearsal time" in rep_stat.text.lower() or "pace" in rep_stat.text.lower()

    # 5. Defense Stop
    rep_stop = asyncio.run(orch.handle("stop defense rehearsal", session="s_test"))
    assert rep_stop.intent == "defense_stop"
