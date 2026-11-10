"""Unit tests for developer identity, origin questions, and portfolio opening intents."""
import asyncio
from pathlib import Path

from backend.config import Settings
from backend.core.actions import Registry
from backend.core.clearance import ClearanceManager
from backend.core.llm import NoLLMProvider
from backend.core.orchestrator import Orchestrator
from backend.core.router import route
from backend.tools.audit import Audit


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
        developer_portfolio_url="https://github.com/Raizel-Codes/MyPortfolioV2",
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
    return orch, settings, registry


def test_route_developer_info(tmp_path):
    _, settings, registry = _make_orch(tmp_path)
    phrases = [
        "who is your developer",
        "who is the developer",
        "who developed you",
        "who made you",
        "who created you",
        "tell me about your developer",
        "who is adrian",
        "who is adrian garcia",
        "nightmare who is your developer",
        "hey nightmare who developed you",
    ]
    for p in phrases:
        intent = route(p, settings, registry)
        assert intent.kind == "developer_info", f"Failed for phrase: '{p}', got: {intent.kind}"


def test_route_developer_why(tmp_path):
    _, settings, registry = _make_orch(tmp_path)
    phrases = [
        "why did adrian develop you",
        "why you are develop",
        "why were you developed",
        "why did adrian make you",
        "why did adrian build you",
        "why did adrian create you",
        "why were you created",
        "why do you exist",
        "nightmare why did adrian develop you",
    ]
    for p in phrases:
        intent = route(p, settings, registry)
        assert intent.kind == "developer_why", f"Failed for phrase: '{p}', got: {intent.kind}"


def test_route_open_portfolio(tmp_path):
    _, settings, registry = _make_orch(tmp_path)
    phrases = [
        "open that link",
        "open the link",
        "open this link",
        "open your developers portfolio web",
        "open your developer's portfolio web",
        "open your developer's portfolio",
        "open adrian portfolio",
        "open adrian's portfolio",
        "open developer portfolio",
        "open that website",
    ]
    for p in phrases:
        intent = route(p, settings, registry)
        assert intent.kind == "open_portfolio", f"Failed for phrase: '{p}', got: {intent.kind}"


def test_route_model_identity_preserved(tmp_path):
    _, settings, registry = _make_orch(tmp_path)
    for p in ["what model powers you", "what model are you", "who powers you", "who trained you"]:
        intent = route(p, settings, registry)
        assert intent.kind == "quick_reply", f"Failed for phrase: '{p}', got: {intent.kind}"
        assert intent.note_text == "model_identity"


def test_orchestrator_developer_info_and_followup(tmp_path):
    orch, _, _ = _make_orch(tmp_path)

    # 1. Ask who is developer
    rep1 = asyncio.run(orch.handle("who is your developer", session="sess1"))
    expected_text = (
        "my developer name is adrian a 4th year bachelor of science in computer science student, "
        "to know more about my developer you can visit his portfolio at https://github.com/Raizel-Codes/MyPortfolioV2"
    )
    assert rep1.text == expected_text
    assert rep1.intent == "developer_info"
    assert rep1.url == "https://github.com/Raizel-Codes/MyPortfolioV2"
    assert rep1.ui == "developer_info"
    assert orch._last_url == "https://github.com/Raizel-Codes/MyPortfolioV2"

    # 2. Follow-up: "open that link"
    rep2 = asyncio.run(orch.handle("open that link", session="sess1"))
    assert rep2.intent == "open_url"
    assert rep2.ui == "open_url"
    assert rep2.url == "https://github.com/Raizel-Codes/MyPortfolioV2"
    assert "Opening Adrian's portfolio in your browser." in rep2.text

    # 3. Explicit "open your developers portfolio web"
    rep3 = asyncio.run(orch.handle("open your developers portfolio web", session="sess1"))
    assert rep3.intent == "open_url"
    assert rep3.ui == "open_url"
    assert rep3.url == "https://github.com/Raizel-Codes/MyPortfolioV2"


def test_orchestrator_developer_why(tmp_path):
    orch, _, _ = _make_orch(tmp_path)

    for q in ["why did adrian develop you", "why you are develop", "why were you developed"]:
        rep = asyncio.run(orch.handle(q, session="sess2"))
        assert rep.intent == "developer_why"
        assert "Adrian developed me as a local, security-hardened voice command assistant" in rep.text
        assert "privacy" in rep.text


def test_developer_skills_and_projects(tmp_path):
    orch, _, _ = _make_orch(tmp_path)

    rep_skills = asyncio.run(orch.handle("what are adrian's skills", session="sess3"))
    assert rep_skills.intent == "developer_skills"
    assert "FastAPI" in rep_skills.text or "Python" in rep_skills.text

    rep_proj = asyncio.run(orch.handle("what other projects did adrian build", session="sess3"))
    assert rep_proj.intent == "developer_projects"
    assert "NexEnroll" in rep_proj.text


def test_readonly_phone_session_allowed(tmp_path):
    orch, _, _ = _make_orch(tmp_path)

    # Level 1 read-only session (e.g. phone) can query developer info and open portfolio
    rep_phone = asyncio.run(orch.handle("who is your developer", readonly=True, session="phone_sess"))
    assert rep_phone.ok
    assert rep_phone.intent == "developer_info"

    rep_why = asyncio.run(orch.handle("why did adrian develop you", readonly=True, session="phone_sess"))
    assert rep_why.ok
    assert rep_why.intent == "developer_why"


def test_contextual_link_memory(tmp_path):
    orch, _, _ = _make_orch(tmp_path)

    # If orchestrator emits a different URL, "open that link" opens that link
    orch._last_url = "https://drive.google.com/drive/folders/test12345"

    rep = asyncio.run(orch.handle("open that link", session="link_sess"))
    assert rep.intent == "open_url"
    assert rep.url == "https://drive.google.com/drive/folders/test12345"
    assert rep.ui == "open_url"


def test_developer_response_latency(tmp_path):
    import time
    orch, _, _ = _make_orch(tmp_path)

    t0 = time.monotonic()
    rep = asyncio.run(orch.handle("who is your developer", session="perf_sess"))
    elapsed_ms = (time.monotonic() - t0) * 1000

    assert rep.intent == "developer_info"
    # Pure Python routing + DB audit should complete in under 50ms, never 8-12 seconds
    assert elapsed_ms < 100, f"Expected <100ms instant reply, took {elapsed_ms:.1f}ms"

