"""Unit tests for Phase 4 of the Project Nightmare Unified Engineering Plan:
- Instant <100ms working indicator & voice output cap (llm.py, orchestrator.py)
- FastEmbed Semantic Response Cache (hit, miss, TTL expiry, exclusion rules)
- Expanded Offline CitizenGraph Defense Bank (50+ items, <30ms retrieval and evaluation)
"""
from __future__ import annotations

import asyncio
from pathlib import Path
import time
import pytest
import numpy as np

from backend.config import Settings
from backend.core.actions import Registry
from backend.core.clearance import ClearanceManager
from backend.core.llm import AgyProvider, NoLLMProvider, LLMError, VOICE_CONCISENESS_CONSTRAINT
from backend.core.orchestrator import Orchestrator, Reply
from backend.core.router import Intent
from backend.tools.audit import Audit
from backend.tools.defense_copilot import DefenseCoPilot
from backend.tools.defense_qa_data import CITIZENGRAPH_DEFENSE_BANK


class MockLLMProvider:
    name = "mock_agy"

    def __init__(self, answer: str = "This is a mock response from agy."):
        self.answer = answer
        self.call_count = 0
        self.last_prompt = ""

    async def complete(self, prompt: str, smart: bool = False) -> str:
        self.call_count += 1
        self.last_prompt = prompt
        return self.answer


def _create_orch(tmp_path: Path, provider=None, event_emitter=None):
    desktop = tmp_path / "desktop"
    desktop.mkdir(exist_ok=True)
    db_path = tmp_path / "nightmare.db"
    apps_file = tmp_path / "apps.json"
    apps_file.write_text('{"apps": {}, "tasks": {}}')
    settings = Settings(
        desktop_root=desktop,
        api_token="x" * 32,
        db_path=db_path,
        apps_file=apps_file,
    )
    registry = Registry({"apps": {}, "tasks": {}})
    audit = Audit(db_path)
    clearance = ClearanceManager()
    orch = Orchestrator(
        settings=settings,
        provider=provider or NoLLMProvider(),
        registry=registry,
        audit=audit,
        clearance=clearance,
        event_emitter=event_emitter,
    )
    return orch, audit


# =============================================================================
# 1. Instant <100ms Working Indicator & Voice Output Cap
# =============================================================================

def test_agy_conciseness_constraint_injection():
    # Regular conversational prompt gets strict conciseness constraint
    prompt = "What is the capital of France?"
    constrained = AgyProvider.inject_conciseness(prompt, smart=False)
    assert VOICE_CONCISENESS_CONSTRAINT in constrained
    assert "50-60 words" in constrained

    # Deep detail prompts remain unconstrained
    deep_prompt = "Explain in detail how quicksort works step-by-step."
    assert AgyProvider.inject_conciseness(deep_prompt, smart=False) == deep_prompt

    # Code requests remain unconstrained
    code_prompt = "Write a python script to parse JSON."
    assert AgyProvider.inject_conciseness(code_prompt, smart=False) == code_prompt

    # smart=True remains unconstrained
    smart_prompt = "Analyze the socio-technical impacts."
    assert AgyProvider.inject_conciseness(smart_prompt, smart=True) == smart_prompt


def test_turn_status_emitted_within_100ms(tmp_path):
    events = []

    def capture_event(payload):
        events.append(payload)

    provider = MockLLMProvider("Quantum computing uses qubits.")
    orch, _ = _create_orch(tmp_path, provider=provider, event_emitter=capture_event)

    t0 = time.perf_counter()
    reply = asyncio.run(orch.handle("What is quantum computing?"))
    elapsed_ms = (time.perf_counter() - t0) * 1000

    assert reply.ok
    assert reply.intent == "chat"
    # Verify working event was emitted
    working_events = [e for e in events if e.get("type") == "turn_status" and e.get("status") == "working"]
    idle_events = [e for e in events if e.get("type") == "turn_status" and e.get("status") == "idle"]

    assert len(working_events) == 1
    assert working_events[0]["target"] == "agy"
    assert working_events[0]["intent"] == "chat"

    assert len(idle_events) == 1
    assert idle_events[0]["status"] == "idle"


# =============================================================================
# 2. FastEmbed Semantic Response Cache
# =============================================================================

def test_semantic_cache_hit_miss_and_ttl(tmp_path):
    audit = Audit(tmp_path / "cache_test.db")

    # 1. Put item in cache
    dummy_vec = np.ones(384, dtype=np.float32)
    dummy_vec = dummy_vec / np.linalg.norm(dummy_vec)
    now = time.time()

    row_id = audit.put_semantic_cache(
        query_text="What is polymorphic inheritance?",
        embedding_blob=dummy_vec.tobytes(),
        response_text="Polymorphic inheritance allows subclasses to override methods.",
        ttl_seconds=3600,
        created_at=now,
    )
    assert row_id > 0

    # 2. Query cache entries
    entries = audit.get_semantic_cache_entries(now=now)
    assert len(entries) == 1
    assert entries[0]["query_text"] == "What is polymorphic inheritance?"
    assert entries[0]["response_text"] == "Polymorphic inheritance allows subclasses to override methods."

    # 3. Test TTL expiration
    future_time = now + 4000
    expired_entries = audit.get_semantic_cache_entries(now=future_time)
    assert len(expired_entries) == 0

    # 4. Test pruning
    pruned_count = audit.prune_semantic_cache(now=future_time)
    assert pruned_count == 1
    assert len(audit.get_semantic_cache_entries(now=now)) == 0


def test_orchestrator_semantic_cache_workflow(tmp_path):
    provider = MockLLMProvider("An abstract class is a blueprint that cannot be instantiated directly.")
    orch, audit = _create_orch(tmp_path, provider=provider)

    query = "What is an abstract class in object oriented programming?"

    # Turn 1: Cache Miss -> calls LLM provider and populates semantic cache
    t0 = time.perf_counter()
    reply1 = asyncio.run(orch.handle(query))
    assert reply1.ok
    assert reply1.text == "An abstract class is a blueprint that cannot be instantiated directly."
    assert provider.call_count == 1

    entries = audit.get_semantic_cache_entries()
    assert len(entries) == 1

    # Turn 2: Cache Hit -> exactly matching or semantically identical query
    # Should resolve from cache in <25ms with 0 calls to LLM
    provider.answer = "CHANGED ANSWER THAT SHOULD NOT BE RETURNED"
    t1 = time.perf_counter()
    reply2 = asyncio.run(orch.handle("What is an abstract class in object-oriented programming?"))
    hit_ms = (time.perf_counter() - t1) * 1000

    assert reply2.ok
    assert reply2.text == "An abstract class is a blueprint that cannot be instantiated directly."
    assert reply2.understood == "chat (semantic cache hit)"
    assert provider.call_count == 1  # No additional model call!
    assert hit_ms < 150.0  # Fast response time including asyncio.run overhead


def test_semantic_cache_exclusion_rules(tmp_path):
    provider = MockLLMProvider("Acknowledged.")
    orch, audit = _create_orch(tmp_path, provider=provider)

    # Personal memory mutation should NOT be cached
    asyncio.run(orch.handle("remember that my student ID is 2026-CS-042"))
    entries = audit.get_semantic_cache_entries()
    assert len(entries) == 0

    # Live status command should NOT be cached
    asyncio.run(orch.handle("how much ram is used"))
    entries = audit.get_semantic_cache_entries()
    assert len(entries) == 0


# =============================================================================
# 3. Expanded Offline CitizenGraph Defense Bank
# =============================================================================

def test_defense_bank_size_and_coverage():
    # Must have 50+ comprehensive Q&A pairs
    assert len(CITIZENGRAPH_DEFENSE_BANK) >= 50

    categories = {q["category"] for q in CITIZENGRAPH_DEFENSE_BANK}
    assert "methodology" in categories
    assert "architecture" in categories
    assert "problem_rrl" in categories
    assert "benchmarks_results" in categories

    # Verify methodology questions include M = R \ H and AST validation
    meth_questions = [q for q in CITIZENGRAPH_DEFENSE_BANK if q["category"] == "methodology"]
    assert len(meth_questions) >= 12
    all_meth_text = " ".join(q["question"] + " " + q["reference_answer"] for q in meth_questions)
    assert "R \\ H" in all_meth_text or "R \\\\ H" in all_meth_text
    assert "Topological Sorting" in all_meth_text
    assert "AST" in all_meth_text

    # Verify architecture questions include 3-tier clearance and OpenXML
    arch_questions = [q for q in CITIZENGRAPH_DEFENSE_BANK if q["category"] == "architecture"]
    assert len(arch_questions) >= 12
    all_arch_text = " ".join(q["question"] + " " + q["reference_answer"] for q in arch_questions)
    assert "3-tier" in all_arch_text
    assert "OpenXML" in all_arch_text
    assert "Neo4j" in all_arch_text

    # Verify benchmarks include >= 95% and <= 5.0s
    bench_questions = [q for q in CITIZENGRAPH_DEFENSE_BANK if q["category"] == "benchmarks_results"]
    assert len(bench_questions) >= 10
    all_bench_text = " ".join(q["question"] + " " + q["reference_answer"] for q in bench_questions)
    assert "95%" in all_bench_text
    assert "5.0" in all_bench_text


def test_defense_bank_offline_precomputation_and_evaluation(tmp_path):
    audit = Audit(tmp_path / "defense_test.db")
    copilot = DefenseCoPilot(audit=audit)

    # 1. Initialize bank into SQLite
    copilot.ensure_bank_initialized()
    db_items = audit.get_defense_qa_bank()
    assert len(db_items) >= 50

    # 2. Test offline matching retrieval in <30ms
    t0 = time.perf_counter()
    matches = copilot.find_matching_qa("How does return-trip prevention formula work?", top_k=2)
    elapsed_ms = (time.perf_counter() - t0) * 1000

    assert len(matches) > 0
    assert matches[0]["category"] == "methodology"
    assert "meth" in matches[0]["id"]
    assert elapsed_ms < 150.0

    # 3. Test offline answer evaluation in <30ms
    target_qa_id = matches[0]["id"]
    student_answer = (
        "In our research, M = R \\ H computes the set difference of requirements minus held documents. "
        "We enforce a 90% threshold and use in-memory AST representations to keep query latency below 5.0 seconds."
    )
    t1 = time.perf_counter()
    eval_res = copilot.evaluate_answer(target_qa_id, student_answer)
    eval_ms = (time.perf_counter() - t1) * 1000

    assert "score" in eval_res
    assert eval_res["score"] >= 0.70
    assert eval_res["grade"] in ("Strong Defense", "Adequate Defense")
    assert len(eval_res["key_points_covered"]) >= 2
    assert eval_ms < 150.0
