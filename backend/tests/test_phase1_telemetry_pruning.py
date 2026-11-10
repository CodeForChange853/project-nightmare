import asyncio
from datetime import datetime, timedelta
from pathlib import Path
import time
import pytest

from backend.config import Settings
from backend.core.actions import Registry
from backend.core.llm import LLMProvider
from backend.core.orchestrator import Orchestrator
from backend.core.router import Intent
from backend.tools.audit import Audit
from backend.tools.file_navigator import scan_safe_files
from backend.tools.fs_reader import _iter_safe_docs, is_safe_doc_name
from backend.tools.rag import ProjectRAG


class FakeLLM(LLMProvider):
    name = "fake"

    async def complete(self, prompt: str, **kw) -> str:
        return "Fake completion reply."


@pytest.fixture
def audit_db(tmp_path):
    db_file = tmp_path / "test_nightmare.db"
    return Audit(db_file)


# ---------------------------------------------------------------------------
# Task 2: Turns Table & is_repeat_ask Detection
# ---------------------------------------------------------------------------

def test_turns_table_schema_and_record(audit_db):
    """Test creation and recording of rows into turns table."""
    rec = audit_db.record_turn(
        utterance="check weather in Calbayog",
        router_path="fast_path",
        confidence_margin=1.0,
        intent="weather",
        router_ms=2,
        tool_ms=45,
        model_ms=0,
        total_ms=47,
        outcome="ok",
    )
    assert rec["turn_id"] == 1
    assert rec["utterance"] == "check weather in Calbayog"
    assert rec["normalized_utterance"] == "check weather in calbayog"
    assert rec["router_path"] == "fast_path"
    assert rec["confidence_margin"] == 1.0
    assert rec["intent"] == "weather"
    assert rec["router_ms"] == 2
    assert rec["tool_ms"] == 45
    assert rec["model_ms"] == 0
    assert rec["total_ms"] == 47
    assert rec["is_repeat_ask"] == 0
    assert rec["outcome"] == "ok"

    # Verify queryable from list_turns
    turns = audit_db.list_turns(limit=10)
    assert len(turns) == 1
    assert turns[0]["turn_id"] == 1
    assert turns[0]["intent"] == "weather"

    # Verify table_counts includes turns
    counts = audit_db.table_counts()
    assert "turns" in counts
    assert counts["turns"] == 1


def test_is_repeat_ask_detection_120s(audit_db):
    """Test repeat ask calculation across normalized utterance and resolved intent."""
    base_time = datetime(2026, 10, 26, 14, 0, 0).astimezone()
    t0_iso = base_time.isoformat()

    # Turn 1: original query
    r1 = audit_db.record_turn(
        utterance="What is the weather in Calbayog?",
        router_path="fast_path",
        confidence_margin=1.0,
        intent="weather",
        router_ms=1,
        tool_ms=10,
        model_ms=0,
        total_ms=11,
        outcome="ok",
        timestamp=t0_iso,
    )
    assert r1["is_repeat_ask"] == 0

    # Turn 2: Exact same normalized utterance within 30 seconds -> repeat
    t2_iso = (base_time + timedelta(seconds=30)).isoformat()
    r2 = audit_db.record_turn(
        utterance="what is the weather in calbayog",
        router_path="fast_path",
        confidence_margin=1.0,
        intent="weather",
        router_ms=1,
        tool_ms=10,
        model_ms=0,
        total_ms=11,
        outcome="ok",
        timestamp=t2_iso,
    )
    assert r2["is_repeat_ask"] == 1

    # Turn 3: Different utterance but same resolved intent within 60s -> repeat
    t3_iso = (base_time + timedelta(seconds=60)).isoformat()
    r3 = audit_db.record_turn(
        utterance="check weather forecast",
        router_path="fast_path",
        confidence_margin=1.0,
        intent="weather",
        router_ms=1,
        tool_ms=10,
        model_ms=0,
        total_ms=11,
        outcome="ok",
        timestamp=t3_iso,
    )
    assert r3["is_repeat_ask"] == 1

    # Turn 4: Different utterance and different intent within 90s -> not a repeat
    t4_iso = (base_time + timedelta(seconds=90)).isoformat()
    r4 = audit_db.record_turn(
        utterance="who is your developer",
        router_path="fast_path",
        confidence_margin=1.0,
        intent="developer_info",
        router_ms=1,
        tool_ms=5,
        model_ms=0,
        total_ms=6,
        outcome="ok",
        timestamp=t4_iso,
    )
    assert r4["is_repeat_ask"] == 0

    # Turn 5: Same utterance as Turn 4 but after 150 seconds (>120s window) -> not a repeat
    t5_iso = (base_time + timedelta(seconds=90 + 150)).isoformat()
    r5 = audit_db.record_turn(
        utterance="who is your developer",
        router_path="fast_path",
        confidence_margin=1.0,
        intent="developer_info",
        router_ms=1,
        tool_ms=5,
        model_ms=0,
        total_ms=6,
        outcome="ok",
        timestamp=t5_iso,
    )
    assert r5["is_repeat_ask"] == 0


# ---------------------------------------------------------------------------
# Task 1: Directory Pruning & Stopwatch Bug Fix
# ---------------------------------------------------------------------------

def test_directory_pruning_iter_safe_docs(tmp_path):
    """Ensure node_modules, .venv, .git, dist, build, __pycache__, data, and *.db are pruned."""
    project = tmp_path / "sample_project"
    project.mkdir()

    # Valid doc
    (project / "README.md").write_text("# Sample Project")

    # Forbidden directories containing files
    for forbidden_dir in ["node_modules", ".venv", ".git", "dist", "build", "__pycache__", "data", "cache.db"]:
        f_dir = project / forbidden_dir
        f_dir.mkdir(parents=True)
        (f_dir / "doc_inside.md").write_text("should be ignored")
        (f_dir / "notes.txt").write_text("should be ignored")

    # Forbidden .db files
    (project / "database.db").write_text("binary content")
    (project / "local.sqlite").write_text("binary content")

    docs = _iter_safe_docs(project, tmp_path)
    doc_names = [d.name for d in docs]

    assert "README.md" in doc_names
    assert "doc_inside.md" not in doc_names
    assert "notes.txt" not in doc_names
    assert "database.db" not in doc_names
    assert "local.sqlite" not in doc_names

    # Direct filename check
    assert is_safe_doc_name("readme.md") is True
    assert is_safe_doc_name("notes.txt") is True
    assert is_safe_doc_name("nightmare.db") is False
    assert is_safe_doc_name(".env") is False


def test_directory_pruning_scan_safe_files(tmp_path):
    """Ensure file_navigator.scan_safe_files strictly prunes data/ and *.db."""
    root = tmp_path / "UserRoot"
    root.mkdir()

    (root / "valid_presentation.pptx").write_text("dummy presentation")
    (root / "data").mkdir()
    (root / "data" / "nested_doc.docx").write_text("dummy doc")
    (root / "node_modules").mkdir()
    (root / "node_modules" / "pkg_doc.pdf").write_text("dummy pdf")
    (root / "state.db").write_text("sqlite db")

    records = scan_safe_files([root])
    indexed_filenames = [r[0] for r in records]

    assert "valid_presentation.pptx" in indexed_filenames
    assert "nested_doc.docx" not in indexed_filenames
    assert "pkg_doc.pdf" not in indexed_filenames
    assert "state.db" not in indexed_filenames


def test_rag_pruning_and_search_timeout(tmp_path):
    """Test ProjectRAG indexing directory pruning."""
    desktop = tmp_path / "Desktop"
    proj = desktop / "citizengraph"
    proj.mkdir(parents=True)
    (proj / "handoff.md").write_text("CitizenGraph: knowledge graph engine.")

    # Data directory (Neo4j data)
    (proj / "data").mkdir()
    (proj / "data" / "neo4j_dump.txt").write_text("mass graph dump")

    rag = ProjectRAG(desktop_root=desktop)
    count = rag.index_all()
    assert count >= 1

    chunks = rag._chunks
    for ch in chunks:
        assert "data" not in Path(ch.rel_path).parts
        assert not ch.rel_path.endswith(".db")


def test_orchestrator_search_projects_timeout_guard(tmp_path):
    """Verify that search_projects enforces a hard 3.0s timeout guard and doesn't block."""
    desktop = tmp_path / "Desktop"
    desktop.mkdir(parents=True)
    settings = Settings(
        desktop_root=desktop,
        api_token="t" * 32,
        db_path=tmp_path / "nightmare.db",
        apps_file=tmp_path / "apps.json",
    )
    provider = FakeLLM()
    registry = Registry()
    audit = Audit(settings.db_path)
    orch = Orchestrator(settings, provider, registry, audit)

    # Mock RAG search to hang for 5 seconds
    async def slow_search(query: str, top_k: int = 2):
        await asyncio.sleep(5.0)
        return []

    orch.rag.search = slow_search

    intent = Intent("search_projects", "search projects for authentication", query="authentication")
    t0 = time.perf_counter()
    reply = asyncio.run(orch._do_search_projects(intent))
    elapsed = time.perf_counter() - t0

    # Ensure timeout fired within ~3.0s - 3.5s and did not hang for 5s
    assert elapsed < 4.0
    assert reply.ok is False
    assert "timed out" in reply.text.lower()

    # Verify action was logged with timeout status
    recent = audit.recent_actions(limit=5)
    assert any(a["kind"] == "search_projects" and a["status"] == "timeout" for a in recent)


def test_orchestrator_turns_telemetry_no_timing_bloat(tmp_path, monkeypatch):
    """Verify orchestrator logs turn telemetry into turns table without bloating actions table."""
    monkeypatch.setattr("backend.tools.weather.fetch_weather", lambda: "Sunny and 28°C in Calbayog.")
    desktop = tmp_path / "Desktop"
    desktop.mkdir(parents=True)
    settings = Settings(
        desktop_root=desktop,
        api_token="t" * 32,
        db_path=tmp_path / "nightmare.db",
        apps_file=tmp_path / "apps.json",
    )
    provider = FakeLLM()
    registry = Registry()
    audit = Audit(settings.db_path)
    orch = Orchestrator(settings, provider, registry, audit)

    reply = asyncio.run(orch.handle("what is the weather"))
    assert reply.ok is True

    # Check turns table has recorded the turn
    turns = audit.list_turns(limit=5)
    assert len(turns) == 1
    t = turns[0]
    assert t["intent"] == "weather"
    assert t["utterance"] == "what is the weather"
    assert t["router_path"] == "fast_path"
    assert t["total_ms"] >= 0
    assert t["router_ms"] >= 0

    # Verify actions table does NOT contain a "timing" row
    actions = audit.recent_actions(limit=10)
    assert not any(a["kind"] == "timing" for a in actions)
