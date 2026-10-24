"""SQLite audit log, LLM call counter, and local notes/reminders store.

Counts calls made through Nightmare. It cannot see your Google AI Pro quota,
because agy does not report that in print mode.
"""
from __future__ import annotations

from contextlib import closing
from datetime import datetime, timedelta
from pathlib import Path
import sqlite3

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
"""


# activity-log filter groups; anything not listed counts as a question (summaries, weather, chat...)
ACTION_GROUPS = {
    "access": ["login", "db_open", "db_close", "settings_open", "settings_save", "confirm"],
    "actions": ["open_app", "open_folder", "open_project_in", "run_task", "run_command", "open_url", "run_dev_task", "rerun_task", "open_file", "send_team_nudge", "team_progress", "timeline_diff"],
    "reminders": ["add_note", "complete_note", "delete_note"],
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
                        1,
                    )
                    for item in items
                ]
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

