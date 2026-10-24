"""3-Tier Security Clearance Architecture (Phase 8A): Level 1, Level 3, Level 5.

- Level 1 (Observer - Default): Default on startup for both laptop and remote sessions.
  Strictly read-only (blocks all ACTION_INTENTS, MEMORY_WRITE_INTENTS, file opening, and system mutations).
- Level 3 (Operator): Activated via PIN. Unlocks MEMORY_WRITE_INTENTS (facts/reminders),
  allowlisted apps.json launches, and detect_dev_tasks. Decays to Level 1 after 30 min of inactivity.
- Level 5 (Architect): Activated via secret password. Constant-time hmac.compare_digest.
  Decays to Level 1 after 10 min of inactivity or immediately on lockdown / sleep mode.
- Remote Guard: Standard remote Tailscale sessions are hard-capped at Level 1 unless
  a valid Defense Pairing Token is active.
"""
from __future__ import annotations

import hmac
import time
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..config import Settings

LEVEL_1 = 1  # Observer
LEVEL_3 = 3  # Operator
LEVEL_5 = 5  # Architect

CLEARANCE_LABELS: dict[int, str] = {
    LEVEL_1: "LEVEL 1 (OBSERVER)",
    LEVEL_3: "LEVEL 3 (OPERATOR)",
    LEVEL_5: "LEVEL 5 (ARCHITECT)",
}

# Inactivity decay timeouts in seconds
LEVEL_TIMEOUTS: dict[int, float] = {
    LEVEL_3: 30 * 60,  # 30 minutes
    LEVEL_5: 10 * 60,  # 10 minutes
}

INTENT_CLEARANCE_MAP: dict[str, int] = {
    # Level 1 (Observer - Read-only queries, briefings, time, weather, chat)
    "quick_reply": LEVEL_1,
    "voice_settings": LEVEL_1,
    "conversation_history": LEVEL_1,
    "search_projects": LEVEL_1,
    "list_projects": LEVEL_1,
    "cross_project": LEVEL_1,
    "read_doc": LEVEL_1,
    "about": LEVEL_1,
    "progress": LEVEL_1,
    "git_status": LEVEL_1,
    "list_notes": LEVEL_1,
    "list_facts": LEVEL_1,
    "weather": LEVEL_1,
    "usage": LEVEL_1,
    "workspace_briefing": LEVEL_1,
    "workspace_changes": LEVEL_1,
    "work_priorities": LEVEL_1,
    "open_url": LEVEL_1,
    "reset_session": LEVEL_1,
    "chat": LEVEL_1,
    "clearance_status": LEVEL_1,
    "clearance_prompt": LEVEL_1,
    "clearance_lockdown": LEVEL_1,
    "db_open": LEVEL_1,
    "db_close": LEVEL_1,
    "settings_open": LEVEL_1,
    "settings_close": LEVEL_1,
    "clear_cache": LEVEL_1,
    "empty": LEVEL_1,

    # Level 3 (Operator - Reminders, memory writes, allowlisted apps, dev tasks, file navigator, github checks)
    "add_note": LEVEL_3,
    "delete_note": LEVEL_3,
    "complete_note": LEVEL_3,
    "remember_fact": LEVEL_3,
    "forget_fact": LEVEL_3,
    "open_app": LEVEL_3,
    "open_folder": LEVEL_3,
    "open_project_in": LEVEL_3,
    "run_task": LEVEL_3,
    "run_dev_task": LEVEL_3,
    "rerun_task": LEVEL_3,
    "open_file": LEVEL_3,
    "github_check": LEVEL_3,

    # Level 5 (Architect - Raw shell commands, PowerPoint COM control, System Authority, Shared Drive Timeline & Quotas)
    "run_command": LEVEL_5,
    "ppt_open_slide": LEVEL_5,
    "ppt_control": LEVEL_5,
    "system_authority": LEVEL_5,
    "team_progress": LEVEL_5,
    "timeline_diff": LEVEL_5,
    "approve_email": LEVEL_5,
    "send_team_nudge": LEVEL_5,
}


class ClearanceManager:
    """Manages session clearance levels with inactivity decay, rate limiting, and remote guard."""

    def __init__(self, max_failures: int = 5, window_sec: int = 60):
        self.max_failures = max_failures
        self.window_sec = window_sec
        # session_id -> (level, last_active_monotonic)
        self._sessions: dict[str, tuple[int, float]] = {}
        # key -> [monotonic_ts]
        self._failures: dict[str, list[float]] = {}

    def get_label(self, level: int) -> str:
        return CLEARANCE_LABELS.get(level, f"LEVEL {level}")

    def check_rate_limit(self, key: str) -> bool:
        now = time.monotonic()
        recent = [t for t in self._failures.get(key, []) if now - t < self.window_sec]
        self._failures[key] = recent
        return len(recent) < self.max_failures

    def record_failure(self, key: str) -> None:
        now = time.monotonic()
        recent = [t for t in self._failures.get(key, []) if now - t < self.window_sec]
        recent.append(now)
        self._failures[key] = recent

    def clear_failures(self, key: str) -> None:
        self._failures.pop(key, None)

    def get_level(self, session_id: str, is_remote: bool = False) -> int:
        """Returns the current clearance level (1, 3, or 5).
        Remote sessions without defense pairing are hard-capped at Level 1.
        Sessions decay to Level 1 after inactivity."""
        if is_remote:
            return LEVEL_1

        entry = self._sessions.get(session_id)
        if not entry:
            return LEVEL_1

        level, last_active = entry
        timeout = LEVEL_TIMEOUTS.get(level)
        if timeout is not None and (time.monotonic() - last_active) > timeout:
            # Inactivity decay to Level 1
            self._sessions[session_id] = (LEVEL_1, time.monotonic())
            return LEVEL_1

        return level

    def get_timeout_seconds(self, level: int) -> int | None:
        """Return total inactivity timeout in seconds for a given level, or None for L1."""
        t = LEVEL_TIMEOUTS.get(level)
        return int(t) if t is not None else None

    def get_remaining_seconds(self, session_id: str, is_remote: bool = False) -> int | None:
        """Return remaining seconds before inactivity decay to Level 1, or None if at Level 1."""
        if is_remote:
            return None
        entry = self._sessions.get(session_id)
        if not entry:
            return None
        level, last_active = entry
        timeout = LEVEL_TIMEOUTS.get(level)
        if timeout is None:
            return None
        remaining = timeout - (time.monotonic() - last_active)
        if remaining <= 0:
            self._sessions[session_id] = (LEVEL_1, time.monotonic())
            return None
        return int(remaining)

    def touch(self, session_id: str) -> None:
        """Update last active timestamp for an elevated session."""
        entry = self._sessions.get(session_id)
        if entry:
            level, _ = entry
            self._sessions[session_id] = (level, time.monotonic())

    def set_level(self, session_id: str, level: int) -> None:
        """Directly set a session clearance level (used in tests and internal resets)."""
        self._sessions[session_id] = (level, time.monotonic())

    def lock_down(self, session_id: str | None = None) -> None:
        """Reset clearance to Level 1 immediately (emergency lockdown, drop to level 1, or sleep)."""
        if session_id is None:
            self._sessions.clear()
        else:
            self._sessions[session_id] = (LEVEL_1, time.monotonic())

    def elevate(
        self,
        session_id: str,
        target_level: int,
        candidate: str,
        settings: Settings,
        is_remote: bool = False,
        key: str = "",
    ) -> tuple[bool, str]:
        """Elevate clearance level with constant-time secret comparison and rate limiting."""
        if is_remote:
            return False, "Remote sessions are hard-capped at Level 1."

        if target_level not in (LEVEL_3, LEVEL_5):
            return False, f"Invalid target clearance level: {target_level}"

        if key and not self.check_rate_limit(key):
            return False, "Too many failed clearance attempts. Wait 60 seconds."

        cand_bytes = candidate.strip().encode()

        if target_level == LEVEL_3:
            expected = getattr(settings, "l3_pin", "") or settings.pin or settings.api_token
            if not expected or not hmac.compare_digest(cand_bytes, expected.encode()):
                if key:
                    self.record_failure(key)
                return False, "Invalid Level 3 PIN."

        elif target_level == LEVEL_5:
            expected = getattr(settings, "l5_password", "") or settings.api_token
            if not expected or not hmac.compare_digest(cand_bytes, expected.encode()):
                if key:
                    self.record_failure(key)
                return False, "Invalid Level 5 password."

        if key:
            self.clear_failures(key)

        self._sessions[session_id] = (target_level, time.monotonic())
        return True, f"Clearance elevated to {self.get_label(target_level)}."
