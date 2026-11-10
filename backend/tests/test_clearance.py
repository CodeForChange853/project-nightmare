"""Tests for Single-Tier Level 5 (Architect) Security Clearance & Remote Read-Only Boundaries."""
from __future__ import annotations

import time
import pytest
from fastapi.testclient import TestClient

from backend.config import Settings
from backend.core import actions
from backend.core.clearance import (
    ClearanceManager,
    INTENT_CLEARANCE_MAP,
    LEVEL_5,
)
from backend.main import create_app

from .conftest import TOKEN

HDR = {"X-Nightmare-Token": TOKEN}
REMOTE_HDR = {"X-Nightmare-Token": TOKEN, "X-Forwarded-For": "100.64.0.99"}


class FakeLLM:
    name = "fake"

    def __init__(self):
        self.prompts = []

    async def complete(self, prompt):
        self.prompts.append(prompt)
        return "Test answer."


@pytest.fixture
def clear_settings(tmp_path, desktop):
    import json
    apps_file = tmp_path / "apps.json"
    apps_file.write_text(json.dumps({
        "apps": {
            "notepad": {"label": "Notepad", "argv": ["notepad.exe"], "aliases": ["notepad"]},
        },
        "tasks": {
            "bims-dev": {"label": "BIMS dev server", "project": "bims", "argv": ["npm", "run", "dev"],
                         "aliases": ["bims dev server"], "confirm": True},
        },
    }))
    return Settings(
        desktop_root=desktop,
        api_token=TOKEN,
        db_path=tmp_path / "clearance_test.db",
        apps_file=apps_file,
        remote_hosts=("laptop.tail1234.ts.net",),
        pin="123456",
        phone_pin="654321",
        allow_raw_commands=True,
    )


@pytest.fixture
def clear_client(clear_settings):
    app = create_app(clear_settings, FakeLLM())
    return TestClient(app, base_url="http://127.0.0.1:8000")


def test_default_startup_is_permanent_level_5_architect(clear_client):
    """Startup defaults directly to permanent Level 5 (Architect) with no decay timer."""
    res = clear_client.get("/api/status", headers=HDR)
    assert res.status_code == 200
    data = res.json()
    assert data.get("clearance_level") == LEVEL_5
    assert "LEVEL 5 (ARCHITECT)" in data.get("clearance_label", "")
    assert data.get("clearance_expires_in") is None
    assert data.get("clearance_timeout") is None

    c_res = clear_client.get("/api/clearance/status", headers=HDR)
    assert c_res.status_code == 200
    c_data = c_res.json()
    assert c_data["level"] == LEVEL_5
    assert "LEVEL 5 (ARCHITECT)" in c_data["label"]


def test_level_5_unlocks_apps_notes_and_memories_immediately(clear_client, monkeypatch):
    """Local desktop session can immediately open allowlisted apps, save reminders, and write memories."""
    ran = []
    monkeypatch.setattr(
        "backend.core.orchestrator.execute",
        lambda plan: ran.append(plan) or actions.ActionResult(True, "ok"),
    )

    # 1. Allowlisted app executes directly
    r_act = clear_client.post("/api/chat", json={"text": "open notepad"}, headers=HDR).json()
    assert r_act["ok"]
    assert ran and ran[0].argv == ["notepad.exe"]

    # 2. Memory write succeeds directly
    r_mem = clear_client.post("/api/chat", json={"text": "remember that my favorite color is crimson"}, headers=HDR).json()
    assert r_mem["ok"]

    # 3. Reminder write succeeds directly
    r_note = clear_client.post("/api/chat", json={"text": "remind me to buy groceries"}, headers=HDR).json()
    assert r_note["ok"]
    assert "#1" in r_note["reply"]

    # 4. High-impact commands still enforce confirmation gate (needs_confirm=True)
    r_cmd = clear_client.post("/api/chat", json={"text": "run command: dir"}, headers=HDR).json()
    assert r_cmd["ok"]
    assert r_cmd["needs_confirm"] is True
    assert r_cmd["pending_id"] is not None


def test_clearance_status_voice_command(clear_client):
    """Asking 'what is my clearance level' describes Level 5 (Architect)."""
    r = clear_client.post("/api/chat", json={"text": "what is my clearance level"}, headers=HDR).json()
    assert r["ok"]
    assert "Level 5" in r["reply"] or "Architect" in r["reply"]


def test_level_5_persistent_across_time_and_sleep(clear_client, monkeypatch):
    """Level 5 Architect remains persistent across idle time and sleep mode."""
    orig_monotonic = time.monotonic
    simulated_now = orig_monotonic() + 7200
    monkeypatch.setattr(time, "monotonic", lambda: simulated_now)

    s2 = clear_client.get("/api/status", headers=HDR).json()
    assert s2["clearance_level"] == LEVEL_5
    assert s2["clearance_expires_in"] is None

    r_sleep = clear_client.post("/api/chat", json={"text": "go to sleep"}, headers=HDR).json()
    assert r_sleep["ui"] == "sleep"
    assert clear_client.get("/api/status", headers=HDR).json()["clearance_level"] == LEVEL_5


def test_remote_session_remains_strictly_readonly(clear_client):
    """Remote Tailscale headers (X-Forwarded-For) remain strictly read-only even with single-tier clearance."""
    s_remote = clear_client.get("/api/status", headers=REMOTE_HDR).json()
    assert s_remote["role"] == "readonly"

    # Remote session cannot launch apps
    r_act = clear_client.post("/api/chat", json={"text": "open notepad"}, headers=REMOTE_HDR).json()
    assert not r_act["ok"]
    assert "read-only" in r_act["reply"].lower()

    # Remote session cannot mutate memories
    r_mem = clear_client.post("/api/chat", json={"text": "remember that secret is 42"}, headers=REMOTE_HDR).json()
    assert not r_mem["ok"]
    assert "laptop" in r_mem["reply"].lower()


def test_clearance_manager_unit():
    """Unit test ClearanceManager single-tier behavior."""
    cm = ClearanceManager()
    assert cm.get_level("any_session") == LEVEL_5
    assert INTENT_CLEARANCE_MAP["system_authority"] == LEVEL_5
