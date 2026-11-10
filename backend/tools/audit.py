"""SQLite audit log, LLM call counter, and local notes/reminders store.

Counts calls made through Nightmare. It cannot see your Google AI Pro quota,
because agy does not report that in print mode.
"""
from __future__ import annotations

from contextlib import closing
from datetime import datetime, timedelta
from pathlib import Path
import json
import sqlite3
import time

from .fs_reader import normalize

SCHEMA = """
CREATE TABLE IF NOT EXISTS actions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT NOT NULL, day TEXT NOT NULL,
    kind TEXT NOT NULL, detail TEXT NOT NULL, status TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS llm_calls (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT NOT NULL, day TEXT NOT NULL,
    provider TEXT NOT NULL, ok INTEGER NOT NULL,
    duration_ms INTEGER NOT NULL, chars_in INTEGER NOT NULL, chars_out INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS summaries (
    key TEXT PRIMARY KEY, mtime_ns INTEGER NOT NULL,
    text TEXT NOT NULL, ts TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS facts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT NOT NULL,
    text TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS conversations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT NOT NULL, day TEXT NOT NULL,
    user_text TEXT NOT NULL, reply_text TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS day_summaries (
    day TEXT PRIMARY KEY, text TEXT NOT NULL, ts TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS notes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT NOT NULL,
    text TEXT NOT NULL,
    done INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS workspace_state (
    project TEXT PRIMARY KEY,
    first_dirty_ts INTEGER NOT NULL DEFAULT 0,
    dirty INTEGER NOT NULL DEFAULT 0,
    updated_ts INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS indexed_files (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    filename TEXT NOT NULL,
    stem_lower TEXT NOT NULL,
    ext TEXT NOT NULL,
    full_path TEXT NOT NULL UNIQUE,
    mtime_ns INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_indexed_files_stem ON indexed_files(stem_lower);
CREATE INDEX IF NOT EXISTS idx_indexed_files_ext ON indexed_files(ext);
CREATE TABLE IF NOT EXISTS team_task_state (
    task_id TEXT PRIMARY KEY,
    assigned_team TEXT NOT NULL,
    owner_email TEXT NOT NULL,
    task_name TEXT NOT NULL,
    current_count REAL NOT NULL DEFAULT 0,
    target_count REAL NOT NULL DEFAULT 0,
    last_change_ts INTEGER NOT NULL DEFAULT 0,
    last_notified_ts INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS timeline_state (
    item_key TEXT NOT NULL,
    sheet_name TEXT NOT NULL,
    title TEXT NOT NULL,
    phase TEXT NOT NULL,
    status TEXT NOT NULL,
    period TEXT NOT NULL,
    deliverable TEXT NOT NULL,
    updated_at INTEGER NOT NULL,
    source_hash TEXT NOT NULL,
    is_baseline INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY(item_key, sheet_name, is_baseline)
);
CREATE INDEX IF NOT EXISTS idx_timeline_state_baseline ON timeline_state(is_baseline);
CREATE TABLE IF NOT EXISTS email_state (
    id TEXT,
    sender TEXT,
    subject TEXT,
    category TEXT,
    status TEXT
);
CREATE TABLE IF NOT EXISTS calendar_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    event_type TEXT NOT NULL,
    start_date TEXT NOT NULL,
    end_date TEXT
);
CREATE TABLE IF NOT EXISTS measurable_tasks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    current_progress INTEGER NOT NULL DEFAULT 0,
    target_progress INTEGER NOT NULL DEFAULT 0,
    unit TEXT NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS defense_sessions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT NOT NULL,
    presentation_name TEXT NOT NULL,
    duration_seconds INTEGER NOT NULL,
    slides_count INTEGER NOT NULL,
    questions_count INTEGER NOT NULL,
    pacing_summary TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS turns (
    turn_id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT NOT NULL,
    utterance TEXT NOT NULL,
    normalized_utterance TEXT NOT NULL,
    router_path TEXT NOT NULL,
    confidence_margin REAL NOT NULL DEFAULT 0.0,
    intent TEXT NOT NULL,
    router_ms INTEGER NOT NULL DEFAULT 0,
    tool_ms INTEGER NOT NULL DEFAULT 0,
    model_ms INTEGER NOT NULL DEFAULT 0,
    total_ms INTEGER NOT NULL DEFAULT 0,
    is_repeat_ask INTEGER NOT NULL DEFAULT 0,
    outcome TEXT NOT NULL DEFAULT 'ok'
);
CREATE INDEX IF NOT EXISTS idx_turns_timestamp ON turns(timestamp);
CREATE INDEX IF NOT EXISTS idx_turns_normalized ON turns(normalized_utterance);
CREATE INDEX IF NOT EXISTS idx_turns_intent ON turns(intent);
CREATE TABLE IF NOT EXISTS router_miss_queue (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT NOT NULL,
    utterance TEXT NOT NULL,
    nearest_intent TEXT NOT NULL,
    similarity_score REAL NOT NULL,
    reviewed INTEGER NOT NULL DEFAULT 0,
    approved_intent TEXT
);
CREATE INDEX IF NOT EXISTS idx_miss_queue_reviewed ON router_miss_queue(reviewed);
CREATE TABLE IF NOT EXISTS custom_exemplars (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    intent TEXT NOT NULL,
    phrase TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_custom_exemplars_intent ON custom_exemplars(intent);
CREATE TABLE IF NOT EXISTS semantic_cache (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    query_text TEXT NOT NULL,
    embedding_blob BLOB NOT NULL,
    response_text TEXT NOT NULL,
    created_at REAL NOT NULL,
    ttl_seconds INTEGER NOT NULL DEFAULT 86400
);
CREATE INDEX IF NOT EXISTS idx_semantic_cache_created ON semantic_cache(created_at);
CREATE TABLE IF NOT EXISTS defense_qa_bank (
    id TEXT PRIMARY KEY,
    category TEXT NOT NULL,
    question TEXT NOT NULL,
    reference_answer TEXT NOT NULL,
    key_points TEXT NOT NULL,
    embedding_blob BLOB,
    created_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_defense_qa_category ON defense_qa_bank(category);
"""


# activity-log filter groups; anything not listed counts as a question (summaries, weather, chat...)
ACTION_GROUPS = {
    "access": [
        "login",
        "db_open",
        "db_close",
        "settings_open",
        "settings_save",
        "confirm",
        "clearance_elevate",
        "clearance_lockdown",
        "clearance_blocked",
    ],
    "defense": [
        "defense_start",
        "defense_stop",
        "defense_question",
        "defense_status",
    ],
    "telemetry": [
        "system_telemetry",
        "system_battery",
        "system_processes",
    ],
    "actions": [
        "open_app",
        "open_folder",
        "open_project_in",
        "run_task",
        "run_command",
        "open_url",
        "run_dev_task",
        "rerun_task",
        "open_file",
        "open_excel",
        "open_team_excel",
        "send_team_nudge",
        "team_progress",
        "timeline_diff",
        "team_sync",
        "ppt_open_slide",
        "ppt_control",
        "system_authority",
        "approve_email",
        "delete_calendar_event",
        "delete_measurable_task",
        "email_report",
        "priority_emails",
    ],
    "reminders": [
        "add_note",
        "complete_note",
        "delete_note",
        "calendar_query",
        "calendar_create",
        "measurable_task",
    ],
    "timing": ["timing"],  # per-answer router/model/total milliseconds (no user text)
}
PROBLEM_WORDS = ("fail", "error", "block", "limit", "cancel")


def _now():
    now = datetime.now().astimezone()
    return now.isoformat(timespec="seconds"), now.strftime("%Y-%m-%d")


class Audit:
    def __init__(self, db_path: Path):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with closing(sqlite3.connect(self.db_path)) as conn:
            conn.executescript(SCHEMA)
            conn.commit()

    def _connect(self):
        return closing(sqlite3.connect(self.db_path))

    def log_action(self, kind: str, detail: str, status: str) -> None:
        ts, day = _now()
        with closing(sqlite3.connect(self.db_path)) as conn:
            conn.execute(
                "INSERT INTO actions (ts, day, kind, detail, status) VALUES (?,?,?,?,?)",
                (ts, day, kind, detail[:500], status),
            )
            conn.commit()

    def log_llm(self, provider: str, ok: bool, duration_ms: int, chars_in: int, chars_out: int) -> None:
        ts, day = _now()
        with closing(sqlite3.connect(self.db_path)) as conn:
            conn.execute(
                "INSERT INTO llm_calls (ts, day, provider, ok, duration_ms, chars_in, chars_out)"
                " VALUES (?,?,?,?,?,?,?)",
                (ts, day, provider, int(ok), duration_ms, chars_in, chars_out),
            )
            conn.commit()

    def llm_counts(self) -> dict:
        _, day = _now()
        with closing(sqlite3.connect(self.db_path)) as conn:
            def count(where, args=()):
                return conn.execute(f"SELECT COUNT(*) FROM llm_calls WHERE {where}", args).fetchone()[0]

            avg_row = conn.execute("SELECT AVG(duration_ms) FROM llm_calls WHERE ok = 1").fetchone()
            avg_ms = int(avg_row[0]) if avg_row and avg_row[0] is not None else 0

            return {
                "today_ok": count("day = ? AND ok = 1", (day,)),
                "today_failed": count("day = ? AND ok = 0", (day,)),
                "total": count("1 = 1"),
                "avg_ms": avg_ms,
            }

    # ---- cached summaries (survive restarts; valid only for the file's mtime) ----

    def get_summary(self, key: str, mtime_ns: int) -> str | None:
        with closing(sqlite3.connect(self.db_path)) as conn:
            row = conn.execute("SELECT text FROM summaries WHERE key = ? AND mtime_ns = ?",
                               (key, mtime_ns)).fetchone()
        return row[0] if row else None

    def put_summary(self, key: str, mtime_ns: int, text: str) -> None:
        ts, _ = _now()
        with closing(sqlite3.connect(self.db_path)) as conn:
            conn.execute("INSERT OR REPLACE INTO summaries (key, mtime_ns, text, ts) VALUES (?,?,?,?)",
                         (key, mtime_ns, text, ts))
            conn.commit()

    def delete_summary(self, key: str) -> None:
        with closing(sqlite3.connect(self.db_path)) as conn:
            conn.execute("DELETE FROM summaries WHERE key = ?", (key,))
            conn.commit()

    def clear_summaries(self) -> int:
        with closing(sqlite3.connect(self.db_path)) as conn:
            cur = conn.execute("DELETE FROM summaries")
            conn.commit()
            return cur.rowcount

    def prune_actions(self, older_than_days: int) -> int:
        """Drop old activity-log rows. Reminders and model-call counts are kept.

        SQLite reuses the freed pages for new rows, so the file stops growing; it does not
        shrink on disk unless VACUUM runs, which isn't needed at this size.
        """
        if older_than_days <= 0:
            return 0
        cutoff = (datetime.now().astimezone() - timedelta(days=older_than_days)).strftime("%Y-%m-%d")
        with closing(sqlite3.connect(self.db_path)) as conn:
            cur = conn.execute("DELETE FROM actions WHERE day < ?", (cutoff,))
            conn.commit()
            return cur.rowcount

    def recent_actions(self, limit: int = 20) -> list[dict]:
        with closing(sqlite3.connect(self.db_path)) as conn:
            rows = conn.execute(
                "SELECT ts, kind, detail, status FROM actions ORDER BY id DESC LIMIT ?", (limit,)
            ).fetchall()
        return [dict(ts=r[0], kind=r[1], detail=r[2], status=r[3]) for r in rows]

    def search_actions(self, group: str = "", outcome: str = "", query: str = "",
                       before: int | None = None, limit: int = 100) -> dict:
        """Activity log viewer: filter by group and outcome, search the text, page with `before`."""
        where, args = [], []
        if group in ACTION_GROUPS:
            kinds = ACTION_GROUPS[group]
            where.append(f"kind IN ({','.join('?' * len(kinds))})")
            args += kinds
        elif group == "questions":  # everything that is not in another group
            kinds = [k for ks in ACTION_GROUPS.values() for k in ks]
            where.append(f"kind NOT IN ({','.join('?' * len(kinds))})")
            args += kinds
        if outcome == "problems":
            where.append("(" + " OR ".join("status LIKE ?" for _ in PROBLEM_WORDS) + ")")
            args += [f"%{w}%" for w in PROBLEM_WORDS]
        elif outcome == "ok":
            where.append("status = 'ok'")
        if query.strip():
            # LIKE wildcards in the search text are matched literally
            text = query.strip()[:100].replace("!", "!!").replace("%", "!%").replace("_", "!_")
            like = f"%{text}%"
            where.append("(detail LIKE ? ESCAPE '!' OR kind LIKE ? ESCAPE '!')")
            args += [like, like]
        if before is not None:
            where.append("id < ?")
            args.append(before)
        sql = "SELECT id, ts, kind, detail, status FROM actions"
        if where:
            sql += " WHERE " + " AND ".join(where)
        sql += " ORDER BY id DESC LIMIT ?"
        with closing(sqlite3.connect(self.db_path)) as conn:
            rows = conn.execute(sql, (*args, limit + 1)).fetchall()
        items = [dict(id=r[0], ts=r[1], kind=r[2], detail=r[3], status=r[4]) for r in rows[:limit]]
        return {"items": items, "more": len(rows) > limit}

    # ---- notes / reminders --------------------------------------------

    def add_note(self, text: str) -> dict:
        ts, _ = _now()
        clean = text.strip()[:300]
        with closing(sqlite3.connect(self.db_path)) as conn:
            cur = conn.execute(
                "INSERT INTO notes (ts, text, done) VALUES (?, ?, 0)",
                (ts, clean),
            )
            conn.commit()
            note_id = cur.lastrowid
        return {"id": note_id, "ts": ts, "text": clean, "done": False}

    def list_notes(self, include_done: bool = False) -> list[dict]:
        where = "1 = 1" if include_done else "done = 0"
        with closing(sqlite3.connect(self.db_path)) as conn:
            rows = conn.execute(
                f"SELECT id, ts, text, done FROM notes WHERE {where} ORDER BY id ASC"
            ).fetchall()
        return [{"id": r[0], "ts": r[1], "text": r[2], "done": bool(r[3])} for r in rows]

    def complete_note(self, note_id: int) -> bool:
        with closing(sqlite3.connect(self.db_path)) as conn:
            cur = conn.execute("UPDATE notes SET done = 1 WHERE id = ? AND done = 0", (note_id,))
            conn.commit()
            return cur.rowcount > 0

    def delete_note(self, note_id: int) -> dict | None:
        """Remove the row for good (not just mark it done). Returns the deleted note, or None."""
        with closing(sqlite3.connect(self.db_path)) as conn:
            row = conn.execute("SELECT id, ts, text, done FROM notes WHERE id = ?", (note_id,)).fetchone()
            if row is None:
                return None
            conn.execute("DELETE FROM notes WHERE id = ?", (note_id,))
            conn.commit()
        return {"id": row[0], "ts": row[1], "text": row[2], "done": bool(row[3])}

    # ---- remembered facts ("remember that ...") ---------------------------

    def add_fact(self, text: str) -> dict:
        ts, _ = _now()
        clean = " ".join(text.split())[:300]
        with closing(sqlite3.connect(self.db_path)) as conn:
            row = conn.execute("SELECT id, ts, text FROM facts WHERE lower(text) = lower(?)", (clean,)).fetchone()
            if row:  # telling it the same thing twice keeps one copy
                return {"id": row[0], "ts": row[1], "text": row[2], "duplicate": True}
            cur = conn.execute("INSERT INTO facts (ts, text) VALUES (?, ?)", (ts, clean))
            conn.commit()
            return {"id": cur.lastrowid, "ts": ts, "text": clean, "duplicate": False}

    def list_facts(self) -> list[dict]:
        with closing(sqlite3.connect(self.db_path)) as conn:
            rows = conn.execute("SELECT id, ts, text FROM facts ORDER BY id ASC").fetchall()
        return [{"id": r[0], "ts": r[1], "text": r[2]} for r in rows]

    def delete_fact(self, fact_id: int) -> dict | None:
        with closing(sqlite3.connect(self.db_path)) as conn:
            row = conn.execute("SELECT id, ts, text FROM facts WHERE id = ?", (fact_id,)).fetchone()
            if row is None:
                return None
            conn.execute("DELETE FROM facts WHERE id = ?", (fact_id,))
            conn.commit()
        return {"id": row[0], "ts": row[1], "text": row[2]}

    # ---- saved conversations and their daily condensed summaries -----------

    def add_turn(self, user_text: str, reply_text: str) -> None:
        ts, day = _now()
        with closing(sqlite3.connect(self.db_path)) as conn:
            conn.execute(
                "INSERT INTO conversations (ts, day, user_text, reply_text) VALUES (?,?,?,?)",
                (ts, day, user_text[:500], reply_text[:800]),
            )
            conn.commit()

    def record_turn(
        self,
        utterance: str,
        router_path: str,
        confidence_margin: float,
        intent: str,
        router_ms: int,
        tool_ms: int,
        model_ms: int,
        total_ms: int,
        outcome: str = "ok",
        timestamp: str | None = None,
    ) -> dict:
        ts, _ = _now()
        if timestamp is not None:
            ts = timestamp

        norm_utt = normalize(utterance)

        try:
            curr_dt = datetime.fromisoformat(ts)
            if curr_dt.tzinfo is None:
                curr_dt = curr_dt.replace(tzinfo=datetime.now().astimezone().tzinfo)
        except Exception:
            curr_dt = datetime.now().astimezone()

        is_repeat = 0
        with closing(sqlite3.connect(self.db_path)) as conn:
            # Check recent turns within previous 120 seconds
            rows = conn.execute(
                "SELECT timestamp, normalized_utterance, intent FROM turns ORDER BY turn_id DESC LIMIT 50"
            ).fetchall()
            for row_ts, row_norm, row_intent in rows:
                try:
                    prev_dt = datetime.fromisoformat(row_ts)
                    if prev_dt.tzinfo is None:
                        prev_dt = prev_dt.replace(tzinfo=curr_dt.tzinfo)
                    diff_sec = abs((curr_dt - prev_dt).total_seconds())
                except Exception:
                    diff_sec = 999999.0

                if diff_sec <= 120.0:
                    if (norm_utt and row_norm == norm_utt) or (intent and row_intent == intent):
                        is_repeat = 1
                        break

            cur = conn.execute(
                """INSERT INTO turns (
                    timestamp, utterance, normalized_utterance, router_path,
                    confidence_margin, intent, router_ms, tool_ms, model_ms,
                    total_ms, is_repeat_ask, outcome
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    ts,
                    utterance[:500],
                    norm_utt[:500],
                    router_path,
                    float(confidence_margin),
                    intent,
                    int(router_ms),
                    int(tool_ms),
                    int(model_ms),
                    int(total_ms),
                    int(is_repeat),
                    outcome,
                ),
            )
            conn.commit()
            turn_id = cur.lastrowid

        return {
            "turn_id": turn_id,
            "timestamp": ts,
            "utterance": utterance,
            "normalized_utterance": norm_utt,
            "router_path": router_path,
            "confidence_margin": float(confidence_margin),
            "intent": intent,
            "router_ms": int(router_ms),
            "tool_ms": int(tool_ms),
            "model_ms": int(model_ms),
            "total_ms": int(total_ms),
            "is_repeat_ask": is_repeat,
            "outcome": outcome,
        }

    def list_turns(self, limit: int = 100, before_id: int | None = None) -> list[dict]:
        with closing(sqlite3.connect(self.db_path)) as conn:
            if before_id is not None:
                rows = conn.execute(
                    """SELECT turn_id, timestamp, utterance, normalized_utterance,
                              router_path, confidence_margin, intent, router_ms,
                              tool_ms, model_ms, total_ms, is_repeat_ask, outcome
                       FROM turns WHERE turn_id < ? ORDER BY turn_id DESC LIMIT ?""",
                    (before_id, limit),
                ).fetchall()
            else:
                rows = conn.execute(
                    """SELECT turn_id, timestamp, utterance, normalized_utterance,
                              router_path, confidence_margin, intent, router_ms,
                              tool_ms, model_ms, total_ms, is_repeat_ask, outcome
                       FROM turns ORDER BY turn_id DESC LIMIT ?""",
                    (limit,),
                ).fetchall()
        return [
            {
                "turn_id": r[0],
                "timestamp": r[1],
                "utterance": r[2],
                "normalized_utterance": r[3],
                "router_path": r[4],
                "confidence_margin": r[5],
                "intent": r[6],
                "router_ms": r[7],
                "tool_ms": r[8],
                "model_ms": r[9],
                "total_ms": r[10],
                "is_repeat_ask": r[11],
                "outcome": r[12],
            }
            for r in rows
        ]

    def recent_turns(self, limit: int = 400) -> list[dict]:
        with closing(sqlite3.connect(self.db_path)) as conn:
            rows = conn.execute(
                "SELECT id, ts, user_text, reply_text FROM conversations ORDER BY id DESC LIMIT ?", (limit,)
            ).fetchall()
        return [{"id": r[0], "ts": r[1], "user": r[2], "reply": r[3]} for r in rows]

    def days_to_condense(self, before_day: str) -> list[str]:
        """Past days that have saved turns but no summary yet, oldest first."""
        with closing(sqlite3.connect(self.db_path)) as conn:
            rows = conn.execute(
                "SELECT DISTINCT day FROM conversations WHERE day < ? AND day NOT IN (SELECT day FROM day_summaries)"
                " ORDER BY day ASC", (before_day,),
            ).fetchall()
        return [r[0] for r in rows]

    def turns_for_day(self, day: str, limit: int = 40) -> list[dict]:
        with closing(sqlite3.connect(self.db_path)) as conn:
            rows = conn.execute(
                "SELECT user_text, reply_text FROM conversations WHERE day = ? ORDER BY id ASC LIMIT ?", (day, limit)
            ).fetchall()
        return [{"user": r[0], "reply": r[1]} for r in rows]

    def put_day_summary(self, day: str, text: str) -> None:
        ts, _ = _now()
        with closing(sqlite3.connect(self.db_path)) as conn:
            conn.execute("INSERT OR REPLACE INTO day_summaries (day, text, ts) VALUES (?,?,?)", (day, text[:1200], ts))
            conn.commit()

    def list_day_summaries(self, limit: int = 60) -> list[dict]:
        with closing(sqlite3.connect(self.db_path)) as conn:
            rows = conn.execute("SELECT day, text FROM day_summaries ORDER BY day DESC LIMIT ?", (limit,)).fetchall()
        return [{"day": r[0], "text": r[1]} for r in rows]

    def prune_conversations(self, older_than_days: int) -> int:
        """Raw saved conversations expire; condensed day summaries and facts stay."""
        if older_than_days <= 0:
            return 0
        cutoff = (datetime.now().astimezone() - timedelta(days=older_than_days)).strftime("%Y-%m-%d")
        with closing(sqlite3.connect(self.db_path)) as conn:
            cur = conn.execute("DELETE FROM conversations WHERE day < ?", (cutoff,))
            conn.commit()
            return cur.rowcount

    # ---- database viewer (PIN-gated in main.py) --------------------------

    def recent_llm_calls(self, limit: int = 200) -> list[dict]:
        with closing(sqlite3.connect(self.db_path)) as conn:
            rows = conn.execute(
                "SELECT ts, provider, ok, duration_ms, chars_in, chars_out FROM llm_calls ORDER BY id DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [
            dict(ts=r[0], provider=r[1], ok=bool(r[2]), duration_ms=r[3], chars_in=r[4], chars_out=r[5])
            for r in rows
        ]

    def table_counts(self) -> dict:
        with closing(sqlite3.connect(self.db_path)) as conn:
            def count(sql):
                return conn.execute(sql).fetchone()[0]

            return {
                "notes": count("SELECT COUNT(*) FROM notes"),
                "notes_active": count("SELECT COUNT(*) FROM notes WHERE done = 0"),
                "facts": count("SELECT COUNT(*) FROM facts"),
                "conversations": count("SELECT COUNT(*) FROM conversations"),
                "day_summaries": count("SELECT COUNT(*) FROM day_summaries"),
                "actions": count("SELECT COUNT(*) FROM actions"),
                "llm_calls": count("SELECT COUNT(*) FROM llm_calls"),
                "workspace_state": count("SELECT COUNT(*) FROM workspace_state"),
                "indexed_files": count("SELECT COUNT(*) FROM indexed_files"),
                "team_task_state": count("SELECT COUNT(*) FROM team_task_state"),
                "calendar_events": count("SELECT COUNT(*) FROM calendar_events"),
                "measurable_tasks": count("SELECT COUNT(*) FROM measurable_tasks"),
                "turns": count("SELECT COUNT(*) FROM turns"),
            }

    # ---- workspace awareness state (dirty files & dirty days tracking) -------

    def update_workspace_dirty(self, project: str, dirty: int, now_ts: int | None = None) -> float:
        """Track when uncommitted files first appeared to measure dirty_days accurately."""
        import time
        now = int(time.time()) if now_ts is None else int(now_ts)
        with closing(sqlite3.connect(self.db_path)) as conn:
            row = conn.execute(
                "SELECT first_dirty_ts, dirty FROM workspace_state WHERE project = ?", (project,)
            ).fetchone()
            if dirty > 0:
                if row and row[0] > 0 and row[1] > 0:
                    first_dirty_ts = row[0]
                else:
                    first_dirty_ts = now
                dirty_days = max(0.0, (now - first_dirty_ts) / 86400.0)
            else:
                first_dirty_ts = 0
                dirty_days = 0.0

            conn.execute(
                "INSERT INTO workspace_state (project, first_dirty_ts, dirty, updated_ts) VALUES (?,?,?,?)"
                " ON CONFLICT(project) DO UPDATE SET first_dirty_ts=excluded.first_dirty_ts, dirty=excluded.dirty, updated_ts=excluded.updated_ts",
                (project, first_dirty_ts, dirty, now),
            )
            conn.commit()
            return dirty_days

    def get_dirty_days_map(self) -> dict[str, float]:
        import time
        now = int(time.time())
        with closing(sqlite3.connect(self.db_path)) as conn:
            rows = conn.execute(
                "SELECT project, first_dirty_ts, dirty FROM workspace_state WHERE dirty > 0 AND first_dirty_ts > 0"
            ).fetchall()
        return {r[0]: max(0.0, (now - r[1]) / 86400.0) for r in rows}

    # ---- file navigator indexed files (Phase 8B) -----------------------------

    def upsert_indexed_files(self, records: list[tuple[str, str, str, str, int]]) -> int:
        if not records:
            return 0
        with closing(sqlite3.connect(self.db_path)) as conn:
            conn.executemany(
                "INSERT INTO indexed_files (filename, stem_lower, ext, full_path, mtime_ns) VALUES (?,?,?,?,?)"
                " ON CONFLICT(full_path) DO UPDATE SET filename=excluded.filename, stem_lower=excluded.stem_lower, "
                "ext=excluded.ext, mtime_ns=excluded.mtime_ns",
                records,
            )
            conn.commit()
            return len(records)

    def prune_indexed_files(self, valid_paths: set[str]) -> int:
        with closing(sqlite3.connect(self.db_path)) as conn:
            if not valid_paths:
                cur = conn.execute("DELETE FROM indexed_files")
                conn.commit()
                return cur.rowcount
            rows = conn.execute("SELECT full_path FROM indexed_files").fetchall()
            to_delete = [r[0] for r in rows if r[0] not in valid_paths]
            if to_delete:
                conn.executemany("DELETE FROM indexed_files WHERE full_path = ?", [(p,) for p in to_delete])
                conn.commit()
                return len(to_delete)
            return 0

    def get_indexed_files(self, ext_filter: set[str] | list[str] | None = None) -> list[dict]:
        with closing(sqlite3.connect(self.db_path)) as conn:
            if ext_filter:
                placeholders = ",".join("?" for _ in ext_filter)
                rows = conn.execute(
                    f"SELECT id, filename, stem_lower, ext, full_path, mtime_ns FROM indexed_files WHERE lower(ext) IN ({placeholders})",
                    list(ext_filter),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT id, filename, stem_lower, ext, full_path, mtime_ns FROM indexed_files"
                ).fetchall()
        return [
            {
                "id": r[0],
                "filename": r[1],
                "stem_lower": r[2],
                "ext": r[3],
                "full_path": r[4],
                "mtime_ns": r[5],
            }
            for r in rows
        ]

    def list_recent_files(self, limit: int = 4) -> list[dict]:
        """Returns the most recently modified indexed files for the Level 5 Recent Activity bar."""
        with closing(sqlite3.connect(self.db_path)) as conn:
            rows = conn.execute(
                "SELECT id, filename, stem_lower, ext, full_path, mtime_ns FROM indexed_files ORDER BY mtime_ns DESC LIMIT ?",
                (int(limit),),
            ).fetchall()
        now_s = time.time()
        out = []
        for r in rows:
            mtime_s = (r[5] or 0) / 1_000_000_000.0
            diff_s = max(60.0, now_s - mtime_s) if mtime_s > 0 else 3600.0
            if diff_s < 3600:
                age = f"{max(1, int(diff_s // 60))}m ago"
            elif diff_s < 86400:
                age = f"{max(1, int(diff_s // 3600))}h ago"
            else:
                age = f"{max(1, int(diff_s // 86400))}d ago"
            ext_clean = (r[3] or "").lower().lstrip(".")
            verb = (
                "Opened"
                if ext_clean in ("pptx", "ppt", "xlsx")
                else "Viewed"
                if ext_clean in ("pdf", "png", "jpg")
                else "Played"
                if ext_clean in ("mp4", "mp3", "wav")
                else "Edited"
            )
            out.append({
                "id": r[0],
                "filename": r[1],
                "stem": r[2],
                "ext": ext_clean or "doc",
                "subtitle": f"{verb} {age}",
            })
        return out

    def list_recent_apps(self, registry_apps: dict | None = None, limit: int = 4) -> list[dict]:
        """Returns the most recently opened allowlisted applications for the Level 5 Recent Activity bar."""
        apps_map = registry_apps or {}
        # Build lookup from app_id, label, and aliases to canonical app_id
        lookup: dict[str, tuple[str, str]] = {}
        for app_id, spec in apps_map.items():
            label = spec.get("label", app_id) if isinstance(spec, dict) else str(app_id)
            lookup[app_id.lower()] = (app_id, label)
            lookup[label.lower()] = (app_id, label)
            if isinstance(spec, dict):
                for alias in spec.get("aliases", []):
                    lookup[str(alias).lower()] = (app_id, label)

        with closing(sqlite3.connect(self.db_path)) as conn:
            rows = conn.execute(
                """SELECT id, ts, kind, detail FROM actions
                   WHERE kind IN ('open_app', 'open_project_in', 'open_excel', 'open_team_excel', 'ppt_open_slide', 'defense_start')
                     AND status = 'ok'
                   ORDER BY id DESC LIMIT 60"""
            ).fetchall()

        now_dt = datetime.now().astimezone()
        seen_apps: set[str] = set()
        out: list[dict] = []

        for r_id, r_ts, r_kind, r_detail in rows:
            detail_low = (r_detail or "").lower().strip()
            matched_id = None
            matched_label = None
            command = None

            if r_kind in ("open_excel", "open_team_excel") and "excel" in lookup:
                matched_id, matched_label = lookup["excel"]
                command = f"open {matched_id}"
            elif r_kind in ("ppt_open_slide", "defense_start") and "powerpoint" in lookup:
                matched_id, matched_label = lookup["powerpoint"]
                command = f"open {matched_id}"
            elif detail_low.startswith("open "):
                rest = detail_low[5:].strip()
                if " in " in rest and r_kind == "open_project_in":
                    proj_part, app_part = rest.rsplit(" in ", 1)
                    hit = lookup.get(app_part.strip())
                    if hit:
                        matched_id, matched_label = hit
                        command = f"open {proj_part.strip()} in {matched_id}"
                else:
                    hit = lookup.get(rest)
                    if hit:
                        matched_id, matched_label = hit
                        command = f"open {matched_id}"

            if not matched_id:
                for key_str, (aid, alabel) in lookup.items():
                    if key_str and key_str in detail_low:
                        matched_id, matched_label = aid, alabel
                        command = f"open {aid}"
                        break

            if not matched_id or matched_id in seen_apps:
                continue

            seen_apps.add(matched_id)
            age_str = "Recently"
            try:
                dt = datetime.fromisoformat(r_ts)
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=now_dt.tzinfo)
                diff_s = max(1.0, (now_dt - dt).total_seconds())
                if diff_s < 60:
                    age_str = "Just now"
                elif diff_s < 3600:
                    age_str = f"{int(diff_s // 60)}m ago"
                elif diff_s < 86400:
                    age_str = f"{int(diff_s // 3600)}h ago"
                else:
                    age_str = f"{int(diff_s // 86400)}d ago"
            except Exception:
                pass

            out.append({
                "id": f"recent-app-{r_id}",
                "app_id": matched_id,
                "label": matched_label,
                "command": command or f"open {matched_id}",
                "subtitle": f"Opened {age_str}",
                "launched": True,
            })
            if len(out) >= limit:
                return out

        # Fill remaining slots with priority allowlisted apps from apps.json so they are ready to launch
        priority_order = ["powerpoint", "word", "excel", "terminal", "vscode", "chrome", "antigravity-ide", "notepad"]
        ordered_keys = [k for k in priority_order if k in apps_map] + [k for k in apps_map if k not in priority_order]
        for app_id in ordered_keys:
            if len(out) >= limit:
                break
            if app_id in seen_apps:
                continue
            spec = apps_map[app_id]
            label = spec.get("label", app_id) if isinstance(spec, dict) else str(app_id)
            seen_apps.add(app_id)
            out.append({
                "id": f"allowlist-app-{app_id}",
                "app_id": app_id,
                "label": label,
                "command": f"open {app_id}",
                "subtitle": "Allowlisted · Click to open",
                "launched": False,
            })

        return out


    # ---- team tracker state (Phase 8D) ---------------------------------------

    def sync_team_task_state(
        self,
        task_id: str,
        assigned_team: str,
        owner_email: str,
        task_name: str,
        current_count: float,
        target_count: float,
        last_updated: str | int | float | None = None,
        now_ts: int | None = None,
    ) -> dict:
        import time
        now = int(time.time()) if now_ts is None else int(now_ts)
        excel_ts = _parse_date_ts(last_updated, fallback=0) if last_updated is not None else 0

        with closing(sqlite3.connect(self.db_path)) as conn:
            row = conn.execute(
                "SELECT current_count, target_count, last_change_ts, last_notified_ts FROM team_task_state WHERE task_id = ?",
                (task_id,),
            ).fetchone()

            if row:
                stored_current, stored_target, stored_change_ts, stored_notified_ts = row
                if abs(current_count - stored_current) > 1e-6:
                    last_change_ts = excel_ts if (excel_ts > 0 and excel_ts <= now) else now
                else:
                    if excel_ts > 0 and (stored_change_ts == 0 or excel_ts < stored_change_ts):
                        last_change_ts = excel_ts
                    else:
                        last_change_ts = stored_change_ts
                last_notified_ts = stored_notified_ts
            else:
                last_change_ts = excel_ts if excel_ts > 0 else now
                last_notified_ts = 0

            days_stale = max(0.0, (now - last_change_ts) / 86400.0)
            is_stale = (current_count < target_count) and (days_stale >= 3.0)
            is_snoozed = (last_notified_ts > 0) and ((now - last_notified_ts) < 86400)

            conn.execute(
                "INSERT INTO team_task_state (task_id, assigned_team, owner_email, task_name, current_count, target_count, last_change_ts, last_notified_ts) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?) "
                "ON CONFLICT(task_id) DO UPDATE SET "
                "assigned_team=excluded.assigned_team, "
                "owner_email=excluded.owner_email, "
                "task_name=excluded.task_name, "
                "current_count=excluded.current_count, "
                "target_count=excluded.target_count, "
                "last_change_ts=excluded.last_change_ts, "
                "last_notified_ts=excluded.last_notified_ts",
                (task_id, assigned_team, owner_email, task_name, current_count, target_count, last_change_ts, last_notified_ts),
            )
            conn.commit()

        pct = round((current_count / target_count) * 100, 1) if target_count > 0 else 0.0
        return {
            "task_id": task_id,
            "assigned_team": assigned_team,
            "owner_email": owner_email,
            "task_name": task_name,
            "current_count": current_count,
            "target_count": target_count,
            "progress_pct": pct,
            "last_change_ts": last_change_ts,
            "last_notified_ts": last_notified_ts,
            "days_since_update": round(days_stale, 1),
            "stale": is_stale,
            "snoozed": is_snoozed,
        }

    def update_team_task_notified(self, task_id: str, notified_ts: int | None = None) -> None:
        import time
        ts = int(time.time()) if notified_ts is None else int(notified_ts)
        with closing(sqlite3.connect(self.db_path)) as conn:
            conn.execute(
                "UPDATE team_task_state SET last_notified_ts = ? WHERE task_id = ?",
                (ts, task_id),
            )
            conn.commit()

    def get_team_task_state(self, task_id: str, now_ts: int | None = None) -> dict | None:
        import time
        now = int(time.time()) if now_ts is None else int(now_ts)
        with closing(sqlite3.connect(self.db_path)) as conn:
            row = conn.execute(
                "SELECT task_id, assigned_team, owner_email, task_name, current_count, target_count, last_change_ts, last_notified_ts FROM team_task_state WHERE task_id = ?",
                (task_id,),
            ).fetchone()
        if not row:
            return None
        days_stale = max(0.0, (now - row[6]) / 86400.0)
        pct = round((row[4] / row[5]) * 100, 1) if row[5] > 0 else 0.0
        return {
            "task_id": row[0],
            "assigned_team": row[1],
            "owner_email": row[2],
            "task_name": row[3],
            "current_count": row[4],
            "target_count": row[5],
            "progress_pct": pct,
            "last_change_ts": row[6],
            "last_notified_ts": row[7],
            "days_since_update": round(days_stale, 1),
            "stale": (row[4] < row[5]) and (days_stale >= 3.0),
            "snoozed": (row[7] > 0) and ((now - row[7]) < 86400),
        }

    def get_all_team_tasks_state(self, now_ts: int | None = None) -> list[dict]:
        import time
        now = int(time.time()) if now_ts is None else int(now_ts)
        with closing(sqlite3.connect(self.db_path)) as conn:
            rows = conn.execute(
                "SELECT task_id, assigned_team, owner_email, task_name, current_count, target_count, last_change_ts, last_notified_ts FROM team_task_state"
            ).fetchall()
        out = []
        for row in rows:
            days_stale = max(0.0, (now - row[6]) / 86400.0)
            pct = round((row[4] / row[5]) * 100, 1) if row[5] > 0 else 0.0
            out.append({
                "task_id": row[0],
                "assigned_team": row[1],
                "owner_email": row[2],
                "task_name": row[3],
                "current_count": row[4],
                "target_count": row[5],
                "progress_pct": pct,
                "last_change_ts": row[6],
                "last_notified_ts": row[7],
                "days_since_update": round(days_stale, 1),
                "stale": (row[4] < row[5]) and (days_stale >= 3.0),
                "snoozed": (row[7] > 0) and ((now - row[7]) < 86400),
            })
        return out

    # ---- timeline snapshot & baseline (Phase 8D-2) ---------------------------

    def upsert_timeline_state(self, items: list[dict], is_baseline: int = 0) -> int:
        if not items:
            return 0
        with closing(sqlite3.connect(self.db_path)) as conn:
            conn.execute("DELETE FROM timeline_state WHERE is_baseline = ?", (int(is_baseline),))
            records = [
                (
                    str(item.get("item_key", "")),
                    str(item.get("sheet_name", "")),
                    str(item.get("title", "")),
                    str(item.get("phase", "")),
                    str(item.get("status", "")),
                    str(item.get("period", "")),
                    str(item.get("deliverable", "")),
                    int(item.get("updated_at", 0)),
                    str(item.get("source_hash", "")),
                    int(is_baseline),
                )
                for item in items
            ]
            conn.executemany(
                "INSERT INTO timeline_state (item_key, sheet_name, title, phase, status, period, deliverable, updated_at, source_hash, is_baseline) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?) "
                "ON CONFLICT(item_key, sheet_name, is_baseline) DO UPDATE SET "
                "title=excluded.title, phase=excluded.phase, status=excluded.status, "
                "period=excluded.period, deliverable=excluded.deliverable, "
                "updated_at=excluded.updated_at, source_hash=excluded.source_hash",
                records,
            )
            conn.commit()
            return len(records)

    def get_timeline_snapshot(self, is_baseline: int = 0) -> list[dict]:
        with closing(sqlite3.connect(self.db_path)) as conn:
            rows = conn.execute(
                "SELECT item_key, sheet_name, title, phase, status, period, deliverable, updated_at, source_hash FROM timeline_state WHERE is_baseline = ?",
                (is_baseline,),
            ).fetchall()
        return [
            {
                "item_key": r[0],
                "sheet_name": r[1],
                "title": r[2],
                "phase": r[3],
                "status": r[4],
                "period": r[5],
                "deliverable": r[6],
                "updated_at": r[7],
                "source_hash": r[8],
            }
            for r in rows
        ]

    def commit_timeline_baseline(self, items: list[dict] | None = None) -> int:
        with closing(sqlite3.connect(self.db_path)) as conn:
            conn.execute("DELETE FROM timeline_state WHERE is_baseline = 1")
            if items is not None:
                conn.execute("DELETE FROM timeline_state WHERE is_baseline = 0")
                records_base = [
                    (
                        str(item.get("item_key", "")),
                        str(item.get("sheet_name", "")),
                        str(item.get("title", "")),
                        str(item.get("phase", "")),
                        str(item.get("status", "")),
                        str(item.get("period", "")),
                        str(item.get("deliverable", "")),
                        int(item.get("updated_at", 0)),
                        str(item.get("source_hash", "")),
                        1,
                    )
                    for item in items
                ]
                records_curr = [
                    (r[0], r[1], r[2], r[3], r[4], r[5], r[6], r[7], r[8], 0)
                    for r in records_base
                ]
                if records_base:
                    conn.executemany(
                        "INSERT INTO timeline_state (item_key, sheet_name, title, phase, status, period, deliverable, updated_at, source_hash, is_baseline) "
                        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                        records_base + records_curr,
                    )
                conn.commit()
                return len(records_base)
            else:
                rows = conn.execute(
                    "SELECT item_key, sheet_name, title, phase, status, period, deliverable, updated_at, source_hash FROM timeline_state WHERE is_baseline = 0"
                ).fetchall()
                records = [(r[0], r[1], r[2], r[3], r[4], r[5], r[6], r[7], r[8], 1) for r in rows]
                if records:
                    conn.executemany(
                        "INSERT INTO timeline_state (item_key, sheet_name, title, phase, status, period, deliverable, updated_at, source_hash, is_baseline) "
                        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                        records,
                    )
                conn.commit()
                return len(records)

    def get_timeline_baseline(self) -> list[dict]:
        return self.get_timeline_snapshot(is_baseline=1)

    # ---- Priority Email Push Notifications (Pub/Sub) ---------------------

    def get_priority_emails(
        self, limit: int = 50, status: str | None = None, category: str | None = None
    ) -> list[dict]:
        with closing(sqlite3.connect(self.db_path)) as conn:
            conn.row_factory = sqlite3.Row
            conn.execute(
                "CREATE TABLE IF NOT EXISTS email_state (id TEXT, sender TEXT, subject TEXT, category TEXT, status TEXT)"
            )
            conditions: list[str] = []
            params: list[object] = []

            if status and status.lower() != "all":
                conditions.append("LOWER(status) = LOWER(?)")
                params.append(status)

            if category and category.lower() != "all":
                if category.lower() == "priority":
                    conditions.append(
                        "(LOWER(category) = 'priority' OR (category IS NULL AND (status IS NULL OR LOWER(status) IN ('pending', 'unread'))))"
                    )
                else:
                    conditions.append("LOWER(category) = LOWER(?)")
                    params.append(category)
            elif not category:
                # Default behavior when no category specified: priority view
                if status and status.lower() != "all":
                    conditions.append(
                        "(LOWER(category) = 'priority' OR category IS NULL OR LOWER(category) NOT IN ('standard', 'temu spam'))"
                    )
                else:
                    conditions.append(
                        "(LOWER(category) = 'priority' OR (LOWER(status) IN ('pending', 'unread') AND (category IS NULL OR LOWER(category) NOT IN ('standard', 'temu spam'))))"
                    )

            where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""
            sql = f"""
                SELECT rowid as row_id, id, sender, subject, category, status
                FROM email_state
                {where_clause}
                ORDER BY rowid DESC
                LIMIT ?
            """
            params.append(limit)
            rows = conn.execute(sql, params).fetchall()
            return [
                {
                    "id": str(r["id"] or r["row_id"]),
                    "sender": r["sender"] or "Unknown Sender",
                    "subject": r["subject"] or "No Subject",
                    "category": r["category"] or "Priority",
                    "status": r["status"] or "Pending",
                    "row_id": r["row_id"],
                }
                for r in rows
            ]

    def update_email_status(self, email_id: str, status: str = "Read") -> bool:
        with closing(sqlite3.connect(self.db_path)) as conn:
            conn.execute(
                "CREATE TABLE IF NOT EXISTS email_state (id TEXT, sender TEXT, subject TEXT, category TEXT, status TEXT)"
            )
            cur = conn.execute(
                "UPDATE email_state SET status = ? WHERE id = ? OR rowid = ?",
                (status, email_id, int(email_id) if email_id.isdigit() else -1),
            )
            conn.commit()
            return cur.rowcount > 0

    # ---- Calendar Events & Measurable Tasks ------------------------------

    def add_calendar_event(
        self, title: str, event_type: str, start_date: str, end_date: str | None = None
    ) -> dict:
        with closing(sqlite3.connect(self.db_path)) as conn:
            conn.execute(
                "CREATE TABLE IF NOT EXISTS calendar_events (id INTEGER PRIMARY KEY AUTOINCREMENT, title TEXT NOT NULL, event_type TEXT NOT NULL, start_date TEXT NOT NULL, end_date TEXT)"
            )
            cur = conn.execute(
                "INSERT INTO calendar_events (title, event_type, start_date, end_date) VALUES (?, ?, ?, ?)",
                (title.strip(), event_type.strip(), str(start_date).strip(), str(end_date).strip() if end_date else None),
            )
            conn.commit()
            event_id = cur.lastrowid
        return {
            "id": event_id,
            "title": title.strip(),
            "event_type": event_type.strip(),
            "start_date": str(start_date).strip(),
            "end_date": str(end_date).strip() if end_date else None,
        }

    def list_calendar_events(
        self, start_date: str | None = None, end_date: str | None = None, event_type: str | None = None
    ) -> list[dict]:
        with closing(sqlite3.connect(self.db_path)) as conn:
            conn.row_factory = sqlite3.Row
            conn.execute(
                "CREATE TABLE IF NOT EXISTS calendar_events (id INTEGER PRIMARY KEY AUTOINCREMENT, title TEXT NOT NULL, event_type TEXT NOT NULL, start_date TEXT NOT NULL, end_date TEXT)"
            )
            conds: list[str] = []
            params: list[object] = []
            if event_type:
                conds.append("LOWER(event_type) = LOWER(?)")
                params.append(event_type.strip())
            if start_date:
                conds.append("start_date >= ?")
                params.append(str(start_date).strip())
            if end_date:
                conds.append("start_date <= ?")
                params.append(str(end_date).strip())
            where = f"WHERE {' AND '.join(conds)}" if conds else ""
            rows = conn.execute(
                f"SELECT id, title, event_type, start_date, end_date FROM calendar_events {where} ORDER BY start_date ASC",
                params,
            ).fetchall()
        return [dict(r) for r in rows]

    def get_calendar_events_in_range(self, start_iso: str, end_iso: str) -> list[dict]:
        """Queries events whose start_date falls within [start_iso, end_iso] with datetime parsing."""
        all_events = self.list_calendar_events()
        try:
            start_dt = datetime.fromisoformat(start_iso)
            end_dt = datetime.fromisoformat(end_iso)
        except Exception:
            return [e for e in all_events if start_iso[:10] <= e["start_date"][:10] <= end_iso[:10]]

        matched = []
        for ev in all_events:
            raw = ev["start_date"]
            try:
                ev_dt = datetime.fromisoformat(raw)
                if ev_dt.tzinfo is None and start_dt.tzinfo is not None:
                    ev_dt = ev_dt.replace(tzinfo=start_dt.tzinfo)
                elif ev_dt.tzinfo is not None and start_dt.tzinfo is None:
                    start_dt = start_dt.replace(tzinfo=ev_dt.tzinfo)
                    end_dt = end_dt.replace(tzinfo=ev_dt.tzinfo)
                if start_dt <= ev_dt <= end_dt:
                    matched.append(ev)
            except Exception:
                if start_iso[:10] <= raw[:10] <= end_iso[:10]:
                    matched.append(ev)
        return matched

    def delete_calendar_event(self, event_id: int) -> bool:
        with closing(sqlite3.connect(self.db_path)) as conn:
            cur = conn.execute("DELETE FROM calendar_events WHERE id = ?", (event_id,))
            conn.commit()
            return cur.rowcount > 0

    def add_measurable_task(
        self, title: str, current_progress: int = 0, target_progress: int = 0, unit: str = ""
    ) -> dict:
        with closing(sqlite3.connect(self.db_path)) as conn:
            conn.execute(
                "CREATE TABLE IF NOT EXISTS measurable_tasks (id INTEGER PRIMARY KEY AUTOINCREMENT, title TEXT NOT NULL, current_progress INTEGER NOT NULL DEFAULT 0, target_progress INTEGER NOT NULL DEFAULT 0, unit TEXT NOT NULL DEFAULT '')"
            )
            cur = conn.execute(
                "INSERT INTO measurable_tasks (title, current_progress, target_progress, unit) VALUES (?, ?, ?, ?)",
                (title.strip(), int(current_progress), int(target_progress), unit.strip()),
            )
            conn.commit()
            task_id = cur.lastrowid
        return {
            "id": task_id,
            "title": title.strip(),
            "current_progress": int(current_progress),
            "target_progress": int(target_progress),
            "unit": unit.strip(),
        }

    def list_measurable_tasks(self) -> list[dict]:
        with closing(sqlite3.connect(self.db_path)) as conn:
            conn.row_factory = sqlite3.Row
            conn.execute(
                "CREATE TABLE IF NOT EXISTS measurable_tasks (id INTEGER PRIMARY KEY AUTOINCREMENT, title TEXT NOT NULL, current_progress INTEGER NOT NULL DEFAULT 0, target_progress INTEGER NOT NULL DEFAULT 0, unit TEXT NOT NULL DEFAULT '')"
            )
            rows = conn.execute(
                "SELECT id, title, current_progress, target_progress, unit FROM measurable_tasks ORDER BY id ASC"
            ).fetchall()
        return [dict(r) for r in rows]

    def get_measurable_task(self, task_id: int | None = None, title: str | None = None) -> dict | None:
        with closing(sqlite3.connect(self.db_path)) as conn:
            conn.row_factory = sqlite3.Row
            conn.execute(
                "CREATE TABLE IF NOT EXISTS measurable_tasks (id INTEGER PRIMARY KEY AUTOINCREMENT, title TEXT NOT NULL, current_progress INTEGER NOT NULL DEFAULT 0, target_progress INTEGER NOT NULL DEFAULT 0, unit TEXT NOT NULL DEFAULT '')"
            )
            if task_id is not None:
                row = conn.execute(
                    "SELECT id, title, current_progress, target_progress, unit FROM measurable_tasks WHERE id = ?",
                    (task_id,),
                ).fetchone()
                return dict(row) if row else None
            if title:
                row = conn.execute(
                    "SELECT id, title, current_progress, target_progress, unit FROM measurable_tasks WHERE LOWER(title) = LOWER(?)",
                    (title.strip(),),
                ).fetchone()
                if row:
                    return dict(row)
                rows = conn.execute(
                    "SELECT id, title, current_progress, target_progress, unit FROM measurable_tasks WHERE LOWER(title) LIKE LOWER(?) ORDER BY id ASC",
                    (f"%{title.strip()}%",),
                ).fetchall()
                if rows:
                    return dict(rows[0])
        return None

    def update_measurable_task_progress(
        self,
        task_id_or_title: int | str,
        current_progress: int,
        target_progress: int | None = None,
        unit: str | None = None,
    ) -> dict | None:
        task = None
        if isinstance(task_id_or_title, int) or (isinstance(task_id_or_title, str) and task_id_or_title.isdigit()):
            task = self.get_measurable_task(task_id=int(task_id_or_title))
        if not task and isinstance(task_id_or_title, str):
            task = self.get_measurable_task(title=task_id_or_title)

        with closing(sqlite3.connect(self.db_path)) as conn:
            conn.execute(
                "CREATE TABLE IF NOT EXISTS measurable_tasks (id INTEGER PRIMARY KEY AUTOINCREMENT, title TEXT NOT NULL, current_progress INTEGER NOT NULL DEFAULT 0, target_progress INTEGER NOT NULL DEFAULT 0, unit TEXT NOT NULL DEFAULT '')"
            )
            if task:
                tid = task["id"]
                updates = ["current_progress = ?"]
                params: list[object] = [int(current_progress)]
                if target_progress is not None:
                    updates.append("target_progress = ?")
                    params.append(int(target_progress))
                if unit is not None:
                    updates.append("unit = ?")
                    params.append(str(unit).strip())
                params.append(tid)
                conn.execute(
                    f"UPDATE measurable_tasks SET {', '.join(updates)} WHERE id = ?",
                    params,
                )
                conn.commit()
                return self.get_measurable_task(task_id=tid)
            else:
                title_str = str(task_id_or_title).strip()
                tgt = int(target_progress) if target_progress is not None else int(current_progress)
                u = unit.strip() if unit else ""
                cur = conn.execute(
                    "INSERT INTO measurable_tasks (title, current_progress, target_progress, unit) VALUES (?, ?, ?, ?)",
                    (title_str, int(current_progress), tgt, u),
                )
                conn.commit()
                return {
                    "id": cur.lastrowid,
                    "title": title_str,
                    "current_progress": int(current_progress),
                    "target_progress": tgt,
                    "unit": u,
                }

    def delete_measurable_task(self, task_id: int) -> bool:
        with closing(sqlite3.connect(self.db_path)) as conn:
            cur = conn.execute("DELETE FROM measurable_tasks WHERE id = ?", (task_id,))
            conn.commit()
            return cur.rowcount > 0

    def add_defense_session(
        self,
        presentation_name: str,
        duration_seconds: int,
        slides_count: int,
        questions_count: int,
        pacing_summary: str,
    ) -> int:
        now = datetime.now().isoformat()
        with closing(sqlite3.connect(self.db_path)) as conn:
            conn.execute(
                """CREATE TABLE IF NOT EXISTS defense_sessions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    ts TEXT NOT NULL,
                    presentation_name TEXT NOT NULL,
                    duration_seconds INTEGER NOT NULL,
                    slides_count INTEGER NOT NULL,
                    questions_count INTEGER NOT NULL,
                    pacing_summary TEXT NOT NULL
                )"""
            )
            cur = conn.execute(
                """INSERT INTO defense_sessions
                   (ts, presentation_name, duration_seconds, slides_count, questions_count, pacing_summary)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (now, presentation_name, duration_seconds, slides_count, questions_count, pacing_summary),
            )
            conn.commit()
            return cur.lastrowid

    def list_defense_sessions(self, limit: int = 20) -> list[dict]:
        with closing(sqlite3.connect(self.db_path)) as conn:
            conn.execute(
                """CREATE TABLE IF NOT EXISTS defense_sessions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    ts TEXT NOT NULL,
                    presentation_name TEXT NOT NULL,
                    duration_seconds INTEGER NOT NULL,
                    slides_count INTEGER NOT NULL,
                    questions_count INTEGER NOT NULL,
                    pacing_summary TEXT NOT NULL
                )"""
            )
            rows = conn.execute(
                "SELECT id, ts, presentation_name, duration_seconds, slides_count, questions_count, pacing_summary "
                "FROM defense_sessions ORDER BY id DESC LIMIT ?",
                (limit,),
            ).fetchall()
            return [
                {
                    "id": r[0],
                    "ts": r[1],
                    "presentation_name": r[2],
                    "duration_seconds": r[3],
                    "slides_count": r[4],
                    "questions_count": r[5],
                    "pacing_summary": r[6],
                }
                for r in rows
            ]

    def log_router_miss(self, utterance: str, nearest_intent: str, similarity_score: float) -> int:
        """Logs an unrecognized chat turn to the router_miss_queue table."""
        now = datetime.now().astimezone().isoformat()
        with closing(sqlite3.connect(self.db_path)) as conn:
            conn.execute(
                """CREATE TABLE IF NOT EXISTS router_miss_queue (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    ts TEXT NOT NULL,
                    utterance TEXT NOT NULL,
                    nearest_intent TEXT NOT NULL,
                    similarity_score REAL NOT NULL,
                    reviewed INTEGER NOT NULL DEFAULT 0,
                    approved_intent TEXT
                )"""
            )
            # Check if already in queue unreviewed
            existing = conn.execute(
                "SELECT id FROM router_miss_queue WHERE utterance = ? AND reviewed = 0",
                (utterance,),
            ).fetchone()
            if existing:
                return existing[0]
            cur = conn.execute(
                """INSERT INTO router_miss_queue (ts, utterance, nearest_intent, similarity_score, reviewed)
                   VALUES (?, ?, ?, ?, 0)""",
                (now, utterance, nearest_intent, float(similarity_score)),
            )
            conn.commit()
            return cur.lastrowid

    def get_router_misses(self, unreviewed_only: bool = True, limit: int = 50) -> list[dict]:
        """Fetches queued misses for the /review command."""
        with closing(sqlite3.connect(self.db_path)) as conn:
            conn.execute(
                """CREATE TABLE IF NOT EXISTS router_miss_queue (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    ts TEXT NOT NULL,
                    utterance TEXT NOT NULL,
                    nearest_intent TEXT NOT NULL,
                    similarity_score REAL NOT NULL,
                    reviewed INTEGER NOT NULL DEFAULT 0,
                    approved_intent TEXT
                )"""
            )
            query = "SELECT id, ts, utterance, nearest_intent, similarity_score, reviewed, approved_intent FROM router_miss_queue"
            if unreviewed_only:
                query += " WHERE reviewed = 0"
            query += " ORDER BY id DESC LIMIT ?"
            rows = conn.execute(query, (limit,)).fetchall()
            return [
                {
                    "id": r[0],
                    "ts": r[1],
                    "utterance": r[2],
                    "nearest_intent": r[3],
                    "similarity_score": round(float(r[4]), 4),
                    "reviewed": bool(r[5]),
                    "approved_intent": r[6],
                }
                for r in rows
            ]

    def approve_router_miss(self, miss_id: int, approved_intent: str) -> bool:
        """Approves a queued miss and converts it into a permanent custom FastEmbed exemplar."""
        now = datetime.now().astimezone().isoformat()
        with closing(sqlite3.connect(self.db_path)) as conn:
            conn.execute(
                """CREATE TABLE IF NOT EXISTS custom_exemplars (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    intent TEXT NOT NULL,
                    phrase TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )"""
            )
            row = conn.execute("SELECT utterance FROM router_miss_queue WHERE id = ?", (miss_id,)).fetchone()
            if not row:
                return False
            utterance = row[0]
            conn.execute(
                "UPDATE router_miss_queue SET reviewed = 1, approved_intent = ?, ts = ? WHERE id = ?",
                (approved_intent, now, miss_id),
            )
            conn.execute(
                "INSERT INTO custom_exemplars (intent, phrase, created_at) VALUES (?, ?, ?)",
                (approved_intent, utterance, now),
            )
            conn.commit()

        # Dynamically register exemplar in SemanticRouter if initialized
        try:
            from ..core.semantic_router import get_semantic_router
            get_semantic_router().add_custom_exemplar(approved_intent, utterance)
        except Exception:
            pass
        return True

    def get_custom_exemplars(self) -> list[tuple[str, str]]:
        """Fetches all permanently approved FastEmbed exemplars."""
        with closing(sqlite3.connect(self.db_path)) as conn:
            conn.execute(
                """CREATE TABLE IF NOT EXISTS custom_exemplars (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    intent TEXT NOT NULL,
                    phrase TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )"""
            )
            rows = conn.execute("SELECT intent, phrase FROM custom_exemplars ORDER BY id ASC").fetchall()
            return [(r[0], r[1]) for r in rows]

    # ---- FastEmbed Semantic Response Cache ----

    def put_semantic_cache(
        self,
        query_text: str,
        embedding_blob: bytes,
        response_text: str,
        ttl_seconds: int = 86400,
        created_at: float | None = None,
    ) -> int:
        """Stores a query embedding and response in the semantic cache."""
        ts = time.time() if created_at is None else created_at
        with self._connect() as conn:
            cur = conn.execute(
                """INSERT INTO semantic_cache (query_text, embedding_blob, response_text, created_at, ttl_seconds)
                   VALUES (?, ?, ?, ?, ?)""",
                (query_text.strip(), embedding_blob, response_text.strip(), ts, ttl_seconds),
            )
            conn.commit()
            return cur.lastrowid

    def get_semantic_cache_entries(self, now: float | None = None) -> list[dict]:
        """Returns all unexpired semantic cache entries."""
        curr = time.time() if now is None else now
        with self._connect() as conn:
            rows = conn.execute(
                """SELECT id, query_text, embedding_blob, response_text, created_at, ttl_seconds
                   FROM semantic_cache
                   WHERE (created_at + ttl_seconds) > ?
                   ORDER BY id DESC""",
                (curr,),
            ).fetchall()
            return [
                {
                    "id": r[0],
                    "query_text": r[1],
                    "embedding_blob": r[2],
                    "response_text": r[3],
                    "created_at": r[4],
                    "ttl_seconds": r[5],
                }
                for r in rows
            ]

    def prune_semantic_cache(self, now: float | None = None) -> int:
        """Deletes expired entries from semantic_cache."""
        curr = time.time() if now is None else now
        with self._connect() as conn:
            cur = conn.execute(
                "DELETE FROM semantic_cache WHERE (created_at + ttl_seconds) <= ?",
                (curr,),
            )
            conn.commit()
            return cur.rowcount

    def clear_semantic_cache(self) -> None:
        """Empties the semantic_cache table."""
        with self._connect() as conn:
            conn.execute("DELETE FROM semantic_cache")
            conn.commit()

    # ---- Pre-Computed Offline CitizenGraph Defense Bank ----

    def init_defense_qa_bank(self, items: list[dict]) -> int:
        """Initializes or inserts missing defense Q&A records into SQLite."""
        inserted = 0
        with self._connect() as conn:
            for item in items:
                existing = conn.execute("SELECT id FROM defense_qa_bank WHERE id = ?", (item["id"],)).fetchone()
                if not existing:
                    key_pts = item.get("key_points", [])
                    key_pts_json = json.dumps(key_pts) if isinstance(key_pts, list) else str(key_pts)
                    conn.execute(
                        """INSERT INTO defense_qa_bank (id, category, question, reference_answer, key_points, embedding_blob, created_at)
                           VALUES (?, ?, ?, ?, ?, ?, ?)""",
                        (
                            item["id"],
                            item["category"],
                            item["question"],
                            item["reference_answer"],
                            key_pts_json,
                            item.get("embedding_blob"),
                            item.get("created_at", time.time()),
                        ),
                    )
                    inserted += 1
            conn.commit()
        return inserted

    def get_defense_qa_bank(self, category: str | None = None) -> list[dict]:
        """Returns defense Q&A items, optionally filtered by category."""
        with self._connect() as conn:
            if category:
                rows = conn.execute(
                    """SELECT id, category, question, reference_answer, key_points, embedding_blob, created_at
                       FROM defense_qa_bank WHERE category = ? ORDER BY id ASC""",
                    (category,),
                ).fetchall()
            else:
                rows = conn.execute(
                    """SELECT id, category, question, reference_answer, key_points, embedding_blob, created_at
                       FROM defense_qa_bank ORDER BY id ASC"""
                ).fetchall()
            result = []
            for r in rows:
                try:
                    pts = json.loads(r[4])
                except Exception:
                    pts = [r[4]]
                result.append({
                    "id": r[0],
                    "category": r[1],
                    "question": r[2],
                    "reference_answer": r[3],
                    "key_points": pts,
                    "embedding_blob": r[5],
                    "created_at": r[6],
                })
            return result

    def get_defense_qa_by_id(self, qa_id: str) -> dict | None:
        """Retrieves a single defense Q&A entry by ID."""
        with self._connect() as conn:
            row = conn.execute(
                """SELECT id, category, question, reference_answer, key_points, embedding_blob, created_at
                   FROM defense_qa_bank WHERE id = ?""",
                (qa_id,),
            ).fetchone()
            if not row:
                return None
            try:
                pts = json.loads(row[4])
            except Exception:
                pts = [row[4]]
            return {
                "id": row[0],
                "category": row[1],
                "question": row[2],
                "reference_answer": row[3],
                "key_points": pts,
                "embedding_blob": row[5],
                "created_at": row[6],
            }

    def update_defense_qa_embedding(self, qa_id: str, embedding_blob: bytes) -> None:
        """Stores the pre-computed FastEmbed vector blob for a defense Q&A item."""
        with self._connect() as conn:
            conn.execute(
                "UPDATE defense_qa_bank SET embedding_blob = ? WHERE id = ?",
                (embedding_blob, qa_id),
            )
            conn.commit()



def _parse_date_ts(val: str | int | float | None, fallback: int = 0) -> int:
    if val is None:
        return fallback
    if isinstance(val, (int, float)):
        if val > 1_000_000_000:
            return int(val)
        if 30000 <= val <= 60000:
            dt = datetime(1899, 12, 30) + timedelta(days=val)
            return int(dt.timestamp())
        return fallback
    s = str(val).strip()
    if not s:
        return fallback
    try:
        f = float(s)
        return _parse_date_ts(f, fallback)
    except ValueError:
        pass
    for fmt in ("%Y-%m-%d", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S", "%m/%d/%Y", "%d/%m/%Y"):
        try:
            dt = datetime.strptime(s, fmt)
            return int(dt.timestamp())
        except ValueError:
            continue
    try:
        dt = datetime.fromisoformat(s)
        return int(dt.timestamp())
    except ValueError:
        pass
    return fallback

