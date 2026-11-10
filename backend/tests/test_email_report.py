"""Tests for Phase 9: Email Report Voice Command, Routing, Clearance, and Orchestrator."""
import asyncio
import json
import time
import pytest

from backend.config import Settings
from backend.core.actions import Registry
from backend.core.clearance import (
    ClearanceManager,
    INTENT_CLEARANCE_MAP,
    LEVEL_5,
)
from backend.core.llm import LLMError
from backend.core.orchestrator import Orchestrator, Reply, _extract_provider_name
from backend.core.router import Intent, route
from backend.tools.audit import Audit


class DummyLLM:
    name = "dummy"

    async def complete(self, prompt: str) -> str:
        return "dummy response"


@pytest.fixture
def dummy_settings(tmp_path):
    desktop = tmp_path / "desktop"
    desktop.mkdir()
    apps_file = tmp_path / "apps.json"
    apps_file.write_text(json.dumps({"apps": {}, "tasks": {}}))
    db_path = tmp_path / "test.db"
    return Settings(
        desktop_root=desktop,
        api_token="test_token",
        db_path=db_path,
        apps_file=apps_file,
    )


@pytest.fixture
def registry():
    return Registry({"apps": {}, "tasks": {}})


def test_provider_name_extraction():
    assert _extract_provider_name("alerts@anthropic.com") == "Anthropic"
    assert _extract_provider_name("notifications@vercel.com") == "Vercel"
    assert _extract_provider_name("support@github.com") == "GitHub"
    assert _extract_provider_name("team@openai.com") == "OpenAI"
    assert _extract_provider_name("Anthropic") == "Anthropic"
    assert _extract_provider_name("Vercel") == "Vercel"
    assert _extract_provider_name("Anthropic <alerts@anthropic.com>") == "Anthropic"
    assert _extract_provider_name("deals@temuemail.com") == "Temu"
    assert _extract_provider_name("newsletter@example.com") == "Example"


def test_email_report_routing(dummy_settings, registry):
    # Required phrases
    phrases = [
        "check my priority emails",
        "read my inbox",
        "do I have any new emails",
        "check priority emails",
        "read inbox",
        "do i have any emails",
        "hey nightmare, check my priority emails",
        "could you please read my inbox?",
        "do I have any new emails?",
        "what's in my inbox",
        "email report",
        "priority email report",
        "inbox report",
    ]
    for phrase in phrases:
        it = route(phrase, dummy_settings, registry)
        assert it.kind == "email_report", f"Failed for phrase: '{phrase}', got {it.kind}"


def test_email_report_clearance_map():
    assert "email_report" in INTENT_CLEARANCE_MAP
    assert INTENT_CLEARANCE_MAP["email_report"] == LEVEL_5


def test_email_report_clearance_enforcement(dummy_settings, registry):
    audit = Audit(dummy_settings.db_path)
    clearance = ClearanceManager()
    orch = Orchestrator(dummy_settings, DummyLLM(), registry, audit, clearance=clearance)

    # 1. Readonly Session: Allowed (reading email status is safe for phone)
    reply_ro = asyncio.run(orch.handle("check my priority emails", session="test_sess", readonly=True))
    assert reply_ro.ok is True
    assert reply_ro.intent == "email_report"

    # 2. Local Level 5 Session: Allowed
    reply_l5 = asyncio.run(orch.handle("check my priority emails", session="test_sess", readonly=False))
    assert reply_l5.ok is True
    assert reply_l5.ui == "team_progress:inbox"


def test_do_email_report_formatting(dummy_settings, registry):
    audit = Audit(dummy_settings.db_path)
    clearance = ClearanceManager()
    orch = Orchestrator(dummy_settings, DummyLLM(), registry, audit, clearance=clearance)

    # Seed emails in sqlite database
    import sqlite3
    with sqlite3.connect(dummy_settings.db_path) as conn:
        conn.execute(
            "CREATE TABLE IF NOT EXISTS email_state (id TEXT, sender TEXT, subject TEXT, category TEXT, status TEXT)"
        )
        conn.execute(
            "INSERT INTO email_state (id, sender, subject, category, status) VALUES (?, ?, ?, ?, ?)",
            ("1", "notifications@vercel.com", "Deployment Ready 1", "Priority", "Pending"),
        )
        conn.execute(
            "INSERT INTO email_state (id, sender, subject, category, status) VALUES (?, ?, ?, ?, ?)",
            ("2", "notifications@vercel.com", "Deployment Ready 2", "Priority", "Pending"),
        )
        conn.execute(
            "INSERT INTO email_state (id, sender, subject, category, status) VALUES (?, ?, ?, ?, ?)",
            ("3", "alerts@anthropic.com", "Claude 3.7 Release", "Priority", "Pending"),
        )
        conn.execute(
            "INSERT INTO email_state (id, sender, subject, category, status) VALUES (?, ?, ?, ?, ?)",
            ("4", "deals@temuemail.com", "90% off coupon", "Temu Spam", "Pending"),
        )
        conn.execute(
            "INSERT INTO email_state (id, sender, subject, category, status) VALUES (?, ?, ?, ?, ?)",
            ("5", "newsletter@example.com", "Weekly news", "Standard", "Read"),
        )
        conn.commit()

    reply = asyncio.run(orch.handle("check my priority emails", session="l5_session"))
    assert reply.ok is True
    assert reply.intent == "email_report"
    assert reply.ui == "team_progress:inbox"
    assert reply.text == "You have 3 pending priority emails: 2 from Vercel and 1 from Anthropic."
    assert reply.data is not None
    assert reply.data["pending_count"] == 3


def test_do_email_report_single_and_zero(dummy_settings, registry):
    audit = Audit(dummy_settings.db_path)
    clearance = ClearanceManager()
    orch = Orchestrator(dummy_settings, DummyLLM(), registry, audit, clearance=clearance)

    # 1. Zero emails
    reply0 = asyncio.run(orch.handle("do I have any new emails", session="l5_session"))
    assert reply0.ok is True
    assert reply0.ui == "team_progress:inbox"
    assert reply0.text == "You have no pending priority emails."

    # 2. Single email
    import sqlite3
    with sqlite3.connect(dummy_settings.db_path) as conn:
        conn.execute(
            "CREATE TABLE IF NOT EXISTS email_state (id TEXT, sender TEXT, subject TEXT, category TEXT, status TEXT)"
        )
        conn.execute(
            "INSERT INTO email_state (id, sender, subject, category, status) VALUES (?, ?, ?, ?, ?)",
            ("v1", "notifications@vercel.com", "Deployment Ready", "Priority", "Pending"),
        )
        conn.commit()

    reply1 = asyncio.run(orch.handle("read my inbox", session="l5_session"))
    assert reply1.ok is True
    assert reply1.ui == "team_progress:inbox"
    assert reply1.text == "You have 1 pending priority email: 1 from Vercel."
