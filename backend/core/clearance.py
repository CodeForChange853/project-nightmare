"""Single-Tier Security Clearance Architecture: Level 5 (Architect).

Project Nightmare operates as a dedicated single-user system on localhost with
permanent Level 5 (Architect) authority. Multi-tier PIN/password elevation hurdles
and inactivity decay timers have been eliminated.

Destructive system mutations (PC reboot, shutdown, Nightmare restart, SMTP emails)
remain protected by mandatory confirmation gates (`needs_confirm=True`), and
remote Tailscale sessions remain protected by read-only guards.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..config import Settings

LEVEL_5 = 5  # Architect (Single-Tier Full System Authority)

CLEARANCE_LABELS: dict[int, str] = {
    LEVEL_5: "LEVEL 5 (ARCHITECT)",
}

INTENT_CLEARANCE_MAP: dict[str, int] = {
    "quick_reply": LEVEL_5,
    "voice_settings": LEVEL_5,
    "conversation_history": LEVEL_5,
    "search_projects": LEVEL_5,
    "list_projects": LEVEL_5,
    "cross_project": LEVEL_5,
    "read_doc": LEVEL_5,
    "about": LEVEL_5,
    "progress": LEVEL_5,
    "git_status": LEVEL_5,
    "list_notes": LEVEL_5,
    "list_facts": LEVEL_5,
    "weather": LEVEL_5,
    "usage": LEVEL_5,
    "workspace_briefing": LEVEL_5,
    "workspace_changes": LEVEL_5,
    "work_priorities": LEVEL_5,
    "open_url": LEVEL_5,
    "reset_session": LEVEL_5,
    "chat": LEVEL_5,
    "clearance_status": LEVEL_5,
    "db_open": LEVEL_5,
    "db_close": LEVEL_5,
    "settings_open": LEVEL_5,
    "settings_close": LEVEL_5,
    "clear_cache": LEVEL_5,
    "calendar_query": LEVEL_5,
    "calendar_create": LEVEL_5,
    "measurable_task": LEVEL_5,
    "developer_info": LEVEL_5,
    "developer_why": LEVEL_5,
    "open_portfolio": LEVEL_5,
    "developer_skills": LEVEL_5,
    "developer_projects": LEVEL_5,
    "system_telemetry": LEVEL_5,
    "system_battery": LEVEL_5,
    "system_processes": LEVEL_5,
    "defense_question": LEVEL_5,
    "defense_status": LEVEL_5,
    "defense_stop": LEVEL_5,
    "empty": LEVEL_5,
    "add_note": LEVEL_5,
    "delete_note": LEVEL_5,
    "complete_note": LEVEL_5,
    "remember_fact": LEVEL_5,
    "forget_fact": LEVEL_5,
    "open_app": LEVEL_5,
    "open_folder": LEVEL_5,
    "open_project_in": LEVEL_5,
    "run_task": LEVEL_5,
    "run_dev_task": LEVEL_5,
    "rerun_task": LEVEL_5,
    "open_file": LEVEL_5,
    "github_check": LEVEL_5,
    "run_command": LEVEL_5,
    "ppt_open_slide": LEVEL_5,
    "ppt_control": LEVEL_5,
    "system_authority": LEVEL_5,
    "team_progress": LEVEL_5,
    "timeline_diff": LEVEL_5,
    "open_team_excel": LEVEL_5,
    "approve_email": LEVEL_5,
    "send_team_nudge": LEVEL_5,
    "email_report": LEVEL_5,
    "defense_start": LEVEL_5,
}


class ClearanceManager:
    """Manages permanent Level 5 (Architect) clearance."""

    def get_label(self, level: int = LEVEL_5) -> str:
        return CLEARANCE_LABELS.get(LEVEL_5, "LEVEL 5 (ARCHITECT)")

    def get_level(self, session_id: str = "default", is_remote: bool = False) -> int:
        """Always returns Level 5 (Architect)."""
        return LEVEL_5

    def get_timeout_seconds(self, level: int = LEVEL_5) -> int | None:
        """Level 5 is persistent and never decays."""
        return None

    def get_remaining_seconds(self, session_id: str = "default", is_remote: bool = False) -> int | None:
        """Level 5 is persistent and never decays."""
        return None

    def touch(self, session_id: str = "default") -> None:
        """No-op: Level 5 is persistent."""

    def set_level(self, session_id: str, level: int = LEVEL_5) -> None:
        """No-op: Level 5 is permanent."""

    def lock_down(self, session_id: str | None = None) -> None:
        """No-op: Level 5 is permanent."""

    def elevate(
        self,
        session_id: str,
        target_level: int = LEVEL_5,
        candidate: str = "",
        settings: Settings | None = None,
        is_remote: bool = False,
        key: str = "",
    ) -> tuple[bool, str]:
        """Returns immediate success since clearance is permanently Level 5."""
        return True, f"Clearance is permanently set to {self.get_label(LEVEL_5)}."
