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
"""


# activity-log filter groups; anything not listed counts as a question (summaries, weather, chat...)
ACTION_GROUPS = {
    "access": ["login", "db_open", "db_close", "settings_open", "settings_save", "confirm"],
    "actions": ["open_app", "open_folder", "open_project_in", "run_task", "run_command", "open_url"],
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
            }
