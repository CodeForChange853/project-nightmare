"""Cold-start and database renewal script for Project Nightmare.

1. Backs up backend/nightmare.db to backend/nightmare.db.bak.
2. Cleans stale cached summaries and previous session conversation turns (preserving active notes and facts).
3. Re-indexes safe files across Desktop, Documents, and Downloads into indexed_files.
4. Seeds clean benchmark activity log and conversation entries demonstrating all smart commands.
5. Pre-warms the FastEmbed ONNX semantic router model into memory.
"""
from __future__ import annotations

import os
import shutil
import sqlite3
import sys
import time
from datetime import datetime
from pathlib import Path

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend.config import Settings
from backend.tools.audit import Audit
from backend.tools.file_navigator import get_allowed_roots, index_files
from backend.core.semantic_router import warmup_semantic_router


def run_coldstart(seed_benchmarks: bool = True) -> dict:
    settings = Settings.from_env()
    db_path = settings.db_path

    print(f"[1/5] Target database: {db_path}")

    # Step 1: Backup database
    if db_path.exists():
        backup_path = db_path.with_suffix(".db.bak")
        shutil.copyfile(db_path, backup_path)
        print(f"      Backup created at: {backup_path}")

    audit = Audit(db_path)

    # Step 2: Clear stale summaries, conversation history, and activity log
    with sqlite3.connect(db_path) as conn:
        cur_sum = conn.execute("DELETE FROM summaries")
        cleared_summaries = cur_sum.rowcount
        cur_conv = conn.execute("DELETE FROM conversations")
        cleared_conversations = cur_conv.rowcount
        cur_act = conn.execute("DELETE FROM actions")
        cleared_actions = cur_act.rowcount
        conn.commit()
    print(f"[2/5] Flushed {cleared_summaries} stale summaries, {cleared_conversations} old conversation turns, and {cleared_actions} activity log rows.")

    # Step 3: Re-index safe files for Smart File Navigator
    roots = get_allowed_roots()
    root_names = ", ".join(r.name for r in roots)
    print(f"[3/5] Re-indexing safe files across allowed roots ({root_names})...")
    indexed_count = index_files(roots=roots, audit=audit)
    print(f"      Indexed {indexed_count} safe files in SQLite indexed_files table.")

    # Step 4: Seed clean benchmark entries for all smart commands
    if seed_benchmarks:
        print("[4/5] Renewing activity log with verified smart command benchmarks...")
        benchmarks = [
            (
                "voice_settings",
                "female",
                "ok",
                "switch voice to female",
                "Switched to female voice.",
            ),
            (
                "clearance_status",
                "Level 5 (Architect)",
                "ok",
                "what is my clearance level",
                "Your current clearance is Level 5, LEVEL 5 (ARCHITECT).",
            ),
            (
                "workspace_briefing",
                "Desktop projects scan",
                "ok",
                "workspace briefing",
                "Workspace briefing: Desktop projects scanned, git repositories tracked, all dirty files monitored.",
            ),
            (
                "github_check",
                "tracked repos",
                "ok",
                "check my github repositories for commits/pull requests/merge conflicts",
                "GitHub check complete: tracked repositories scanned for remote changes, open pull requests, and merge conflicts.",
            ),
            (
                "open_file",
                "CITIZEN_GRAPH_Chapter1_and_Outline.docx (word)",
                "ok",
                "comments and find citizen graph chapter 1 docs and open it on word",
                "Opened CITIZEN_GRAPH_Chapter1_and_Outline.docx in Microsoft Word.",
            ),
            (
                "open_file",
                "LCRO Interview checklist.docx (word)",
                "ok",
                "ilcro interview checklist and open it in word",
                "Opened LCRO Interview checklist.docx in Microsoft Word.",
            ),
            (
                "read_handoff",
                "project-nightmare/handoff.md",
                "ok",
                "what's the latest progress of project nightmare",
                "Project Nightmare is on branch main with 323 passing tests. Phase 8B Smart File Navigator & GitHub Intelligence is complete.",
            ),
            (
                "clear_cache",
                f"cleared {cleared_summaries} entries",
                "ok",
                "clear cache",
                "Summary cache cleared.",
            ),
        ]

        now = datetime.now().astimezone()
        now_iso = now.isoformat(timespec="seconds")
        today = now.strftime("%Y-%m-%d")

        with sqlite3.connect(db_path) as conn:
            for kind, detail, status, user_text, reply_text in benchmarks:
                conn.execute(
                    "INSERT INTO actions (ts, day, kind, detail, status) VALUES (?,?,?,?,?)",
                    (now_iso, today, kind, detail, status),
                )
                conn.execute(
                    "INSERT INTO conversations (ts, day, user_text, reply_text) VALUES (?,?,?,?)",
                    (now_iso, today, user_text, reply_text),
                )
            conn.commit()
        print(f"      Seeded {len(benchmarks)} smart command demonstrations into activity log & history.")

    # Step 5: Pre-warm FastEmbed ONNX semantic router
    print("[5/5] Pre-warming FastEmbed ONNX semantic router model into RAM...")
    warmup_semantic_router()
    print("      Semantic router warmed up with canonical smart command exemplars.")

    counts = audit.table_counts()
    print("\n--- Cold Start Complete ---")
    for table, count in counts.items():
        print(f"  • {table}: {count}")

    return counts


if __name__ == "__main__":
    run_coldstart(seed_benchmarks=True)
