"""Offline Router Replay Harness.

Replays historical user utterances from backend/nightmare.db (or activity_log.md fallback),
benchmarks router.route() precision/latency, and analyzes remaining fallbacks.
"""
from __future__ import annotations

import argparse
from collections import defaultdict
import os
from pathlib import Path
import re
import sqlite3
import sys
import time

# Ensure project root is in sys.path
REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from backend.config import Settings
from backend.core.actions import Registry
from backend.core.context_buffer import ConversationContext
from backend.core.router import route
from backend.core.semantic_router import find_top_candidates, warmup_semantic_router


def extract_utterances_from_db(db_path: Path) -> list[str]:
    """Extract unique historical utterances from SQLite tables preserving chronological order."""
    if not db_path.is_file():
        return []

    utterances: list[str] = []
    seen: set[str] = set()

    def add(item: str) -> None:
        clean = " ".join(item.strip().split())
        if clean and clean.lower() not in seen:
            seen.add(clean.lower())
            utterances.append(clean)

    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        # Check existing tables
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = {row[0] for row in cursor.fetchall()}

        # 1. From turns table if populated
        if "turns" in tables:
            for (utt,) in cursor.execute("SELECT utterance FROM turns ORDER BY turn_id ASC").fetchall():
                add(utt)

        # 2. From conversations table
        if "conversations" in tables:
            for (user_text,) in cursor.execute("SELECT user_text FROM conversations ORDER BY id ASC").fetchall():
                add(user_text)

        # 3. From actions table (specifically fallback unrecognized_chat)
        if "actions" in tables:
            for (detail,) in cursor.execute(
                "SELECT detail FROM actions WHERE kind = 'unrecognized_chat' ORDER BY id ASC"
            ).fetchall():
                add(detail)

        conn.close()
    except Exception as exc:
        print(f"[Warning] Failed extracting from {db_path}: {exc}", file=sys.stderr)

    return utterances


def extract_utterances_from_activity_log(log_path: Path) -> list[str]:
    """Extract historical fallback queries and utterances from activity_log.md."""
    if not log_path.is_file():
        return []

    utterances: list[str] = []
    seen: set[str] = set()

    def add(item: str) -> None:
        clean = " ".join(item.strip().split())
        if clean and clean.lower() not in seen:
            seen.add(clean.lower())
            utterances.append(clean)

    try:
        content = log_path.read_text(encoding="utf-8", errors="replace")
        # Match table rows: | id | timestamp | group | unrecognized_chat | fallback | query |
        table_pattern = re.compile(
            r"\|\s*\d+\s*\|\s*[^|]+\|\s*[^|]+\|\s*(?:`?unrecognized_chat`?|`?[a-z_]+`?)\s*\|\s*[^|]+\|\s*([^|\r\n]+)\|"
        )
        for match in table_pattern.finditer(content):
            val = match.group(1).strip().strip("`")
            if val and not val.startswith("---") and not val.startswith("router") and "|" not in val:
                add(val)
    except Exception as exc:
        print(f"[Warning] Failed extracting from {log_path}: {exc}", file=sys.stderr)

    return utterances


def run_replay(
    db_path: Path | None = None,
    from_activity_log: bool = False,
    limit: int | None = None,
) -> dict:
    target_db = db_path or (REPO_ROOT / "backend" / "nightmare.db")
    activity_log = REPO_ROOT / "activity_log.md"

    if from_activity_log:
        utterances = extract_utterances_from_activity_log(activity_log)
        source_name = f"activity_log.md ({activity_log.name})"
    else:
        utterances = extract_utterances_from_db(target_db)
        source_name = f"SQLite ({target_db.name})"
        if not utterances:
            utterances = extract_utterances_from_activity_log(activity_log)
            source_name = f"activity_log.md ({activity_log.name})"

    if not utterances:
        # Fallback to representative sample
        utterances = [
            "what is the weather",
            "check my github repositories for commits/pull requests/merge conflicts",
            "what is my clearance level",
            "who is your developer",
            "why did adrian develop you",
            "system telemetry",
            "how is my ram usage",
            "start defense rehearsal",
            "ask defense question",
            "search projects for authentication",
            "what changed today",
            "what should i work on",
            "open that link",
            "what time is it",
            "good morning nightmare",
            "help",
        ]
        source_name = "Builtin Representative Suite"

    if limit is not None and limit > 0:
        utterances = utterances[:limit]

    # Initialize settings and registry
    try:
        settings = Settings.from_env()
    except Exception:
        settings = Settings(
            desktop_root=Path.home() / "Desktop",
            api_token="test_token_for_replay_mode_32chars_min",
        )
    registry = Registry()

    print(f"\n[Offline Router Replay Harness]")
    print(f"Data source: {source_name}")
    print(f"Total utterances extracted: {len(utterances)}")
    print("Warming up FastEmbed semantic router...")
    warmup_semantic_router()

    total_count = len(utterances)
    fast_path_count = 0
    fallback_count = 0
    latencies: list[float] = []

    matched_by_intent: dict[str, int] = defaultdict(int)
    fallbacks: list[dict] = []

    context = ConversationContext()

    for text in utterances:
        t0 = time.perf_counter()
        intent = route(text, settings, registry, context=context)
        lat_ms = (time.perf_counter() - t0) * 1000.0
        latencies.append(lat_ms)

        if intent.kind != "chat":
            fast_path_count += 1
            matched_by_intent[intent.kind] += 1
            if intent.kind == "open_file":
                q = intent.query or intent.text
                if q:
                    # Like orchestrator disambiguation, populate candidate list for ordinal followups
                    candidates = [f"{q}_option1.docx", f"{q}_option2.pptx", f"{q}_option3.pdf"]
                    context.update(last_candidates=candidates, last_opened_file=q, last_intent=intent.kind)
                else:
                    context.update(last_intent=intent.kind)
            elif intent.kind == "ppt_control":
                p = getattr(intent, "ppt_path", None)
                if p:
                    context.update(last_opened_file=Path(p).name, last_intent=intent.kind)
                else:
                    context.update(last_intent=intent.kind)
            else:
                context.update(last_intent=intent.kind)
        else:
            fallback_count += 1
            # Retrieve top 2 semantic candidate matches for diagnostic categorization
            candidates = find_top_candidates(text, top_k=2)
            fallbacks.append({
                "utterance": text,
                "latency_ms": lat_ms,
                "candidates": candidates,
            })

    avg_lat = sum(latencies) / len(latencies) if latencies else 0.0
    fallback_pct = (fallback_count / total_count * 100.0) if total_count > 0 else 0.0
    fast_path_pct = (fast_path_count / total_count * 100.0) if total_count > 0 else 0.0

    # Print Precision / Recall Summary Table
    print("\n" + "=" * 68)
    print("                  ROUTER REPLAY SUMMARY TABLE")
    print("=" * 68)
    print(f" {'Metric':<36} | {'Value':<27} ")
    print("-" * 68)
    print(f" {'Total Turns Tested':<36} | {total_count:<27} ")
    print(f" {'Fast-Path Matches (Deterministic/ONNX)':<36} | {fast_path_count:<10} ({fast_path_pct:.1f}%) ")
    print(f" {'Fallbacks (unrecognized_chat -> LLM)':<36} | {fallback_count:<10} ({fallback_pct:.1f}%) ")
    print(f" {'Fallback Percentage':<36} | {fallback_pct:.2f}% ")
    print(f" {'Average Routing Latency':<36} | {avg_lat:.2f} ms ")
    print(f" {'Median Routing Latency':<36} | {sorted(latencies)[len(latencies)//2]:.2f} ms ")
    print(f" {'95th Percentile Routing Latency':<36} | {sorted(latencies)[int(len(latencies)*0.95)]:.2f} ms ")
    print("=" * 68)

    # Top matched fast-path intents
    top_matched = sorted(matched_by_intent.items(), key=lambda kv: -kv[1])[:10]
    print("\n[Top Matched Fast-Path Intents]")
    for intent_name, cnt in top_matched:
        print(f"  - {intent_name:<25}: {cnt} turns")

    # Categorized Fallbacks with Top-2 Semantic Candidates
    if fallbacks:
        print(f"\n[Remaining Fallbacks ({len(fallbacks)}) & Top-2 Semantic Candidates]")
        # Categorize by top semantic candidate intent
        categorized: dict[str, list[dict]] = defaultdict(list)
        for fb in fallbacks:
            top_intent = fb["candidates"][0][0] if fb["candidates"] else "unmapped_chat"
            categorized[top_intent].append(fb)

        sorted_cats = sorted(categorized.items(), key=lambda kv: -len(kv[1]))
        for cat_name, items in sorted_cats:
            print(f"\n  Category: {cat_name} ({len(items)} queries)")
            for item in items[:5]:  # print up to 5 per category
                cand_str = ", ".join(f"{c[0]} ({c[1]:.2f})" for c in item["candidates"])
                print(f"    * \"{item['utterance']}\"")
                print(f"      Candidates: {cand_str}")
            if len(items) > 5:
                print(f"      ... and {len(items) - 5} more")

    print("\n" + "=" * 68 + "\n")
    return {
        "total_count": total_count,
        "fast_path_count": fast_path_count,
        "fallback_count": fallback_count,
        "fallback_pct": fallback_pct,
        "avg_lat_ms": avg_lat,
        "matched_by_intent": dict(matched_by_intent),
        "fallbacks": fallbacks,
    }


def main():
    parser = argparse.ArgumentParser(description="Offline Router Replay Harness")
    parser.add_argument("--db", type=Path, default=None, help="Path to nightmare.db")
    parser.add_argument("--activity-log", action="store_true", help="Force replay from activity_log.md")
    parser.add_argument("--limit", type=int, default=None, help="Limit number of utterances to test")
    args = parser.parse_args()

    run_replay(db_path=args.db, from_activity_log=args.activity_log, limit=args.limit)


if __name__ == "__main__":
    main()
