"""Tests for smart-over-time enhancements 1-5:
1. Model warmup on startup
2. Voice switching intent & UI action
3. Instant local memory intent (recent conversation history)
4. Project count semantic routing & response format
5. Local project knowledge RAG search
"""
import asyncio
from pathlib import Path
from unittest.mock import MagicMock
import pytest

from backend.config import Settings
from backend.core.actions import Registry
from backend.core.orchestrator import Orchestrator, Reply
from backend.core.router import Intent, route
from backend.core.semantic_router import (
    SemanticRouter,
    match_semantic_intent,
    warmup_semantic_router,
)
from backend.tools.audit import Audit
from backend.tools.rag import ProjectRAG


@pytest.fixture
def orch(settings, registry):
    audit = Audit(settings.db_path)
    provider = MagicMock()
    return Orchestrator(settings, provider, registry, audit), provider


# =====================================================================
# 1. Warmup
# =====================================================================
def test_warmup_semantic_router():
    # warmup initializes the singleton and does not fail
    assert warmup_semantic_router() is True
    # Once warmed up, match_semantic_intent should return immediately
    matched = match_semantic_intent("who are you again")
    assert matched is not None
    assert matched.kind == "quick_reply"
    assert matched.note_text == "name"


# =====================================================================
# 2. Voice Switching Intent
# =====================================================================
@pytest.mark.parametrize(
    "phrase,expected_gender",
    [
        ("switch voice to female", "female"),
        ("change female voice", "female"),
        ("change voice to female", "female"),
        ("use female voice", "female"),
        ("set voice to female", "female"),
        ("switch to female voice", "female"),
        ("female voice", "female"),
        ("switch voice to male", "male"),
        ("change male voice", "male"),
        ("change voice to male", "male"),
        ("use male voice", "male"),
        ("switch to male voice", "male"),
        ("male voice", "male"),
    ],
)
def test_route_voice_settings(settings: Settings, registry: Registry, phrase: str, expected_gender: str):
    intent = route(phrase, settings, registry)
    assert intent.kind == "voice_settings"
    assert intent.voice_gender == expected_gender


def test_orchestrator_voice_settings(orch):
    o, _ = orch
    intent = Intent("voice_settings", "switch voice to female", voice_gender="female")
    reply = asyncio.run(o._handle_intent(intent, "switch voice to female", "voice_settings", readonly=False))
    assert reply.ok is True
    assert "female" in reply.text.lower()
    assert reply.ui == "voice:female"


# =====================================================================
# 3. Instant Local Memory Intent ("what did we discuss earlier")
# =====================================================================
@pytest.mark.parametrize(
    "phrase",
    [
        "earlier what we have discussed earlier",
        "what did we discuss earlier",
        "what was our previous conversation was",
        "what was our previous conversation",
        "what were we talking about",
        "what did we talk about earlier",
        "what did i ask earlier",
    ],
)
def test_route_conversation_history(settings: Settings, registry: Registry, phrase: str):
    intent = route(phrase, settings, registry)
    assert intent.kind == "conversation_history"


def test_orchestrator_conversation_history(orch):
    o, provider = orch
    audit = o.audit
    # No history yet
    intent = Intent("conversation_history", "what did we discuss earlier")
    reply = asyncio.run(o._handle_intent(intent, "what did we discuss earlier", "conversation_history", readonly=False))
    assert reply.ok is True
    assert "haven't discussed anything" in reply.text.lower() or "no previous conversation" in reply.text.lower()

    # Add 2 turns
    audit.add_turn("what is the weather", "In Calbayog it's 25C with overcast.")
    audit.add_turn("who are you", "I'm Nightmare, your local assistant.")

    reply2 = asyncio.run(o._handle_intent(intent, "what did we discuss earlier", "conversation_history", readonly=False))
    assert reply2.ok is True
    assert "weather" in reply2.text.lower()
    assert "who are you" in reply2.text.lower()
    # Ensure cloud LLM was NOT called
    assert provider.complete.call_count == 0


# =====================================================================
# 4. Project Count Semantic Exemplar & Count Response
# =====================================================================
@pytest.mark.parametrize(
    "phrase",
    [
        "how many active projects i have",
        "how many projects do i have",
        "how many projects i have",
        "count my projects",
        "how many projects are there",
    ],
)
def test_route_project_count(settings: Settings, registry: Registry, phrase: str):
    intent = route(phrase, settings, registry)
    assert intent.kind == "list_projects"


def test_orchestrator_project_count_reply(orch, desktop: Path):
    o, _ = orch
    intent = Intent("list_projects", "how many active projects i have")
    reply = asyncio.run(o._handle_intent(intent, "how many active projects i have", "list_projects", readonly=False))
    assert reply.ok is True
    # desktop fixture in conftest has bims, citizengraph, other, node_modules (which are desktop folders)
    assert "projects on your desktop" in reply.text.lower()


# =====================================================================
# 5. Local Project Knowledge RAG
# =====================================================================
@pytest.mark.parametrize(
    "phrase,expected_query",
    [
        ("search projects for authentication", "authentication"),
        ("find in projects neo4j database", "neo4j database"),
        ("search project docs for docker", "docker"),
        ("search all projects for api keys", "api keys"),
    ],
)
def test_route_search_projects(settings: Settings, registry: Registry, phrase: str, expected_query: str):
    intent = route(phrase, settings, registry)
    assert intent.kind == "search_projects"
    assert intent.query == expected_query


def test_rag_indexing_and_search(tmp_path: Path):
    d = tmp_path / "Desktop"
    d.mkdir()
    proj_a = d / "citizengraph"
    proj_a.mkdir()
    (proj_a / "handoff.md").write_text(
        "# CitizenGraph\nWe use Neo4j graph database and fine-tuned Llama 3 8B model for citizen profiling.",
        encoding="utf-8"
    )

    proj_b = d / "bims"
    proj_b.mkdir()
    (proj_b / "README.md").write_text(
        "# BIMS\nBarangay Information Management System built with PHP Laravel and MySQL.",
        encoding="utf-8"
    )

    rag = ProjectRAG(desktop_root=d)
    # Search for Neo4j / graph
    hits = asyncio.run(rag.search("graph database and llama model", top_k=2))
    assert len(hits) >= 1
    assert hits[0].project == "citizengraph"
    assert "Neo4j" in hits[0].snippet

    # Search for barangay
    hits_b = asyncio.run(rag.search("barangay information management", top_k=2))
    assert len(hits_b) >= 1
    assert hits_b[0].project == "bims"


def test_orchestrator_search_projects(orch, desktop: Path):
    o, provider = orch
    # desktop has bims with handoff: "Done: login page. Next: reports. Blocker: none."
    intent = Intent("search_projects", "search projects for login page", query="login page")
    reply = asyncio.run(o._handle_intent(intent, "search projects for login page", "search_projects", readonly=False))
    assert reply.ok is True
    assert "bims" in reply.text.lower()
    # Local search, no LLM provider call needed
    assert provider.complete.call_count == 0


# =====================================================================
# 6. Helper Function & UI Intent
# =====================================================================
@pytest.mark.parametrize(
    "phrase",
    [
        "open helper function",
        "nightmare open helper function",
        "open developer helper function",
        "developer helper function",
        "open helper",
        "nightmare open helper ui",
    ],
)
def test_route_open_helper_function(settings: Settings, registry: Registry, phrase: str):
    intent = route(phrase, settings, registry)
    assert intent.kind == "quick_reply"
    assert intent.note_text == "helper"


def test_orchestrator_open_helper_reply(orch):
    o, _ = orch
    intent = Intent("quick_reply", "open helper function", note_text="helper")
    reply = asyncio.run(o._handle_intent(intent, "open helper function", "quick_reply", readonly=False))
    assert reply.ok is True
    assert reply.text == "Opening developer helper function."
    assert reply.ui == "help"
