"""Tests for Phase 8A: 3-Tier Security Clearance Architecture (Level 1, Level 3, Level 5)."""
from __future__ import annotations

import time
import pytest
from fastapi.testclient import TestClient

from backend.config import Settings
from backend.core import actions
from backend.core.clearance import (
    ClearanceManager,
    INTENT_CLEARANCE_MAP,
    LEVEL_1,
    LEVEL_3,
    LEVEL_5,
)
from backend.core.llm import LLMError
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
    )


@pytest.fixture
def clear_client(clear_settings):
    # Set L3 PIN and L5 password for testing
    object.__setattr__(clear_settings, "l3_pin", "123456")
    object.__setattr__(clear_settings, "l5_password", "ArcHitect_Secret_99")
    app = create_app(clear_settings, FakeLLM())
    return TestClient(app, base_url="http://127.0.0.1:8000")


# ==============================================================================
# Gate 1: Default startup is Level 1 and blocks MEMORY_WRITE_INTENTS and ACTION_INTENTS
# ==============================================================================

def test_default_startup_level_1_blocks_actions_and_memory_writes(clear_client):
    """Level 1 (Observer) is default on startup and blocks ACTION_INTENTS, MEMORY_WRITE_INTENTS,
    and system mutations even on localhost."""
    # Check status endpoint reports Level 1
    res = clear_client.get("/api/status", headers=HDR)
    assert res.status_code == 200
    data = res.json()
    assert data.get("clearance_level") == 1
    assert "LEVEL 1 (OBSERVER)" in data.get("clearance_label", "")

    # 1. ACTION_INTENTS blocked (open_app: Level 3 required)
    r_act = clear_client.post("/api/chat", json={"text": "open notepad"}, headers=HDR).json()
    assert not r_act["ok"]
    assert "That action requires Level 3 access. Say 'Nightmare open level 3' to unlock." in r_act["reply"]

    # 2. MEMORY_WRITE_INTENTS blocked (remember_fact: Level 3 required)
    r_mem = clear_client.post("/api/chat", json={"text": "remember that my favorite color is crimson"}, headers=HDR).json()
    assert not r_mem["ok"]
    assert "That action requires Level 3 access. Say 'Nightmare open level 3' to unlock." in r_mem["reply"]

    # 3. Reminder writes blocked (add_note: Level 3 required)
    r_note = clear_client.post("/api/chat", json={"text": "remind me to buy groceries"}, headers=HDR).json()
    assert not r_note["ok"]
    assert "That action requires Level 3 access. Say 'Nightmare open level 3' to unlock." in r_note["reply"]

    # 4. Raw shell commands blocked (run_command: Level 5 required)
    r_cmd = clear_client.post("/api/chat", json={"text": "run command: dir"}, headers=HDR).json()
    assert not r_cmd["ok"]
    assert "That action requires Level 5 access. Say 'Nightmare open level 5' to unlock." in r_cmd["reply"]

    # 5. Read-only intents remain allowed at Level 1
    r_wx = clear_client.post("/api/chat", json={"text": "what is the weather"}, headers=HDR).json()
    assert r_wx["ok"]

    r_time = clear_client.post("/api/chat", json={"text": "what time is it"}, headers=HDR).json()
    assert r_time["ok"]

    # Check audit log contains clearance_blocked entries
    audit_res = clear_client.get("/api/audit", headers=HDR).json()
    blocked_actions = [a for a in audit_res["actions"] if a["kind"] == "clearance_blocked"]
    assert len(blocked_actions) >= 4
    for b in blocked_actions:
        assert b["status"] == "blocked"


# ==============================================================================
# Gate 2: Voice commands return exact prompt strings and ui metadata
# ==============================================================================

def test_voice_command_open_level_5_exact_prompt(clear_client):
    """Voice command 'nightmare open level 5' must reply with exact TTS string:
    'Opening Nightmare Level 5 access... please write the password' and return ui='clearance_prompt:5'."""
    # Test canonical phrasing
    r = clear_client.post("/api/chat", json={"text": "nightmare open level 5"}, headers=HDR).json()
    assert r["reply"] == "Opening Nightmare Level 5 access... please write the password"
    assert r["ui"] == "clearance_prompt:5"

    # Test alternate phrasing: "elevate to level 5"
    r2 = clear_client.post("/api/chat", json={"text": "elevate to level 5"}, headers=HDR).json()
    assert r2["reply"] == "Opening Nightmare Level 5 access... please write the password"
    assert r2["ui"] == "clearance_prompt:5"


def test_voice_command_open_level_3_exact_prompt(clear_client):
    """Voice command 'nightmare open level 3' or 'elevate to level 3' prompts
    'Opening Nightmare Level 3 access. Please enter your PIN.' and return ui='clearance_prompt:3'."""
    r = clear_client.post("/api/chat", json={"text": "nightmare open level 3"}, headers=HDR).json()
    assert r["reply"] == "Opening Nightmare Level 3 access. Please enter your PIN."
    assert r["ui"] == "clearance_prompt:3"

    r2 = clear_client.post("/api/chat", json={"text": "elevate to level 3"}, headers=HDR).json()
    assert r2["reply"] == "Opening Nightmare Level 3 access. Please enter your PIN."
    assert r2["ui"] == "clearance_prompt:3"


def test_clearance_status_voice_command(clear_client):
    """Asking 'what is my clearance level' describes the current level."""
    r = clear_client.post("/api/chat", json={"text": "what is my clearance level"}, headers=HDR).json()
    assert r["ok"]
    assert "Level 1" in r["reply"] or "Observer" in r["reply"]


# ==============================================================================
# Gate 3: Elevation, Password verification, and Rate Limiting
# ==============================================================================

def test_elevation_valid_level_5_unlocks_architect(clear_client, monkeypatch):
    """Valid password elevates to Level 5 and unlocks system operations."""
    # Elevate to Level 5
    el = clear_client.post(
        "/api/clearance/elevate",
        json={"level": 5, "password": "ArcHitect_Secret_99"},
        headers=HDR,
    )
    assert el.status_code == 200
    assert el.json()["ok"] is True
    assert el.json()["level"] == 5

    # Check status endpoint reflects Level 5
    s = clear_client.get("/api/status", headers=HDR).json()
    assert s["clearance_level"] == 5
    assert "LEVEL 5 (ARCHITECT)" in s["clearance_label"]

    # Now open notepad (which needs Level 3) is allowed past clearance!
    ran = []
    monkeypatch.setattr(
        "backend.core.orchestrator.execute",
        lambda plan: ran.append(plan) or actions.ActionResult(True, "ok"),
    )
    r_act = clear_client.post("/api/chat", json={"text": "open notepad"}, headers=HDR).json()
    assert r_act["ok"]
    assert ran and ran[0].argv == ["notepad.exe"]


def test_elevation_valid_level_3_unlocks_operator(clear_client):
    """Valid PIN elevates to Level 3 and unlocks memory and allowlisted apps."""
    el = clear_client.post(
        "/api/clearance/elevate",
        json={"level": 3, "pin": "123456"},
        headers=HDR,
    )
    assert el.status_code == 200
    assert el.json()["ok"] is True
    assert el.json()["level"] == 3

    # Adding a note now succeeds
    r_note = clear_client.post("/api/chat", json={"text": "remind me to write tests"}, headers=HDR).json()
    assert r_note["ok"]
    assert "Reminder #1 saved" in r_note["reply"] or "#1" in r_note["reply"]

    # Level 5 actions still blocked!
    r_cmd = clear_client.post("/api/chat", json={"text": "run command: dir"}, headers=HDR).json()
    assert not r_cmd["ok"]
    assert "That action requires Level 5 access. Say 'Nightmare open level 5' to unlock." in r_cmd["reply"]


def test_elevation_wrong_password_and_rate_limiting(clear_client):
    """Wrong password fails and logs to Audit; 5 failures triggers rate limiting (429)."""
    for i in range(5):
        r = clear_client.post(
            "/api/clearance/elevate",
            json={"level": 5, "password": f"wrong_{i}"},
            headers=HDR,
        )
        assert r.status_code == 401

    # 6th attempt should be rate limited (429)
    r6 = clear_client.post(
        "/api/clearance/elevate",
        json={"level": 5, "password": "wrong_6"},
        headers=HDR,
    )
    assert r6.status_code == 429
    assert "Too many failed clearance attempts" in r6.json()["detail"]

    # Verify audit log recorded failures and rate limit
    audit_res = clear_client.get("/api/audit", headers=HDR).json()
    elevate_logs = [a for a in audit_res["actions"] if a["kind"] == "clearance_elevate"]
    assert any(l["status"] == "failed" for l in elevate_logs)
    assert any(l["status"] == "rate_limited" for l in elevate_logs)


# ==============================================================================
# Gate 4: Inactivity Timeout and Lockdown
# ==============================================================================

def test_lockdown_voice_command_resets_to_level_1(clear_client):
    """'nightmare lock down' or 'drop to level 1' resets clearance immediately to Level 1."""
    # First elevate to Level 5
    el = clear_client.post(
        "/api/clearance/elevate",
        json={"level": 5, "password": "ArcHitect_Secret_99"},
        headers=HDR,
    )
    assert el.status_code == 200

    # Issue voice command "nightmare lock down"
    r_lock = clear_client.post("/api/chat", json={"text": "nightmare lock down"}, headers=HDR).json()
    assert r_lock["ok"]
    assert "locked down" in r_lock["reply"].lower() or "level 1" in r_lock["reply"].lower()

    # Now verify Level 3 action is blocked again
    r_act = clear_client.post("/api/chat", json={"text": "open notepad"}, headers=HDR).json()
    assert not r_act["ok"]
    assert "That action requires Level 3 access" in r_act["reply"]


def test_level_5_inactivity_timeout_decay(clear_client, monkeypatch):
    """Level 5 decays to Level 1 after 10 minutes (600s) of inactivity."""
    # Elevate to Level 5
    clear_client.post(
        "/api/clearance/elevate",
        json={"level": 5, "password": "ArcHitect_Secret_99"},
        headers=HDR,
    )

    s = clear_client.get("/api/status", headers=HDR).json()
    assert s["clearance_level"] == 5

    # Simulate 10 minutes and 1 second passing
    orig_monotonic = time.monotonic
    simulated_now = orig_monotonic() + 601
    monkeypatch.setattr(time, "monotonic", lambda: simulated_now)

    # Next status call should show decayed to Level 1
    s2 = clear_client.get("/api/status", headers=HDR).json()
    assert s2["clearance_level"] == 1

    # And action is blocked
    r_act = clear_client.post("/api/chat", json={"text": "open notepad"}, headers=HDR).json()
    assert not r_act["ok"]
    assert "That action requires Level 3 access" in r_act["reply"]


def test_level_3_inactivity_timeout_decay(clear_client, monkeypatch):
    """Level 3 decays to Level 1 after 30 minutes (1800s) of inactivity."""
    clear_client.post(
        "/api/clearance/elevate",
        json={"level": 3, "pin": "123456"},
        headers=HDR,
    )

    s = clear_client.get("/api/status", headers=HDR).json()
    assert s["clearance_level"] == 3

    # Fast forward 29 minutes: still Level 3
    orig_monotonic = time.monotonic
    simulated_29m = orig_monotonic() + 1740
    monkeypatch.setattr(time, "monotonic", lambda: simulated_29m)
    assert clear_client.get("/api/status", headers=HDR).json()["clearance_level"] == 3

    # Fast forward past 30 minutes: decays to Level 1
    simulated_31m = orig_monotonic() + 1801
    monkeypatch.setattr(time, "monotonic", lambda: simulated_31m)
    assert clear_client.get("/api/status", headers=HDR).json()["clearance_level"] == 1


# ==============================================================================
# Gate 5: Remote Tailscale Sessions Hard-Capped at Level 1
# ==============================================================================

def test_remote_session_cannot_elevate_past_level_1(clear_client):
    """Unpaired remote Tailscale headers (X-Forwarded-For / remote Host) cannot elevate
    past Level 1 even with the correct password."""
    # Attempt Level 5 elevation from remote
    r5 = clear_client.post(
        "/api/clearance/elevate",
        json={"level": 5, "password": "ArcHitect_Secret_99"},
        headers=REMOTE_HDR,
    )
    assert r5.status_code == 403
    assert "Remote sessions are hard-capped at Level 1" in r5.json()["detail"]

    # Attempt Level 3 elevation from remote
    r3 = clear_client.post(
        "/api/clearance/elevate",
        json={"level": 3, "pin": "123456"},
        headers=REMOTE_HDR,
    )
    assert r3.status_code == 403
    assert "Remote sessions are hard-capped at Level 1" in r3.json()["detail"]

    # Attempting to check status with remote headers returns Level 1
    s_remote = clear_client.get("/api/status", headers=REMOTE_HDR).json()
    assert s_remote["clearance_level"] == 1
    assert "LEVEL 1 (OBSERVER)" in s_remote["clearance_label"]
