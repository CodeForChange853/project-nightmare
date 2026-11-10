"""Phase 8F Thesis Defense Co-Pilot & Mock Panelist Interrogation Mode.

Integrates with PowerPoint COM automation and CitizenGraph research objectives to provide
slide-aware presentation rehearsal pacing, speech timer nudges, realistic academic panelist
technical questions, and rehearsal telemetry persistence in SQLite.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import logging
from pathlib import Path
import random
import re
import time
from typing import TYPE_CHECKING

from .defense_qa_data import CITIZENGRAPH_DEFENSE_BANK

if TYPE_CHECKING:
    from .audit import Audit

logger = logging.getLogger("nightmare.defense_copilot")

# Target pacing per slide in seconds for a standard 12-minute (720s) CS defense
DEFAULT_SLIDE_PACING_BUDGET = {
    1: 45,   # Title & Introduction
    2: 75,   # Background & Problem Statement
    3: 60,   # Research Objectives (SO-1 to SO-7)
    4: 90,   # Conceptual Framework & Architecture
    5: 120,  # Methodology & Algorithms (AST Validation & Return-Trip Formula)
    6: 90,   # Implementation & Zero-Dependency OpenXML Engine
    7: 90,   # Quantitative Results & Benchmark Verification (>= 90%, >= 95%)
    8: 60,   # System Demo & Security Clearance Model
    9: 50,   # Limitations & Future Work
    10: 40,  # Summary & Conclusion
}

# Targeted academic panelist questions aligned with Adrian's CitizenGraph research
PANELIST_QUESTIONS_BY_TOPIC = {
    "methodology": [q["question"] for q in CITIZENGRAPH_DEFENSE_BANK if q["category"] == "methodology"],
    "architecture": [q["question"] for q in CITIZENGRAPH_DEFENSE_BANK if q["category"] == "architecture"],
    "problem": [q["question"] for q in CITIZENGRAPH_DEFENSE_BANK if q["category"] == "problem_rrl"],
    "results": [q["question"] for q in CITIZENGRAPH_DEFENSE_BANK if q["category"] == "benchmarks_results"],
    "general": [q["question"] for q in CITIZENGRAPH_DEFENSE_BANK],
}


@dataclass
class DefenseSession:
    presentation_path: Path
    start_time: float = field(default_factory=time.time)
    end_time: float | None = None
    active_slide: int = 1
    total_slides: int = 10
    slide_timestamps: dict[int, float] = field(default_factory=dict)
    questions_asked: list[str] = field(default_factory=list)
    target_duration_s: int = 720  # 12 minutes standard

    def __post_init__(self):
        if not self.slide_timestamps:
            self.slide_timestamps[self.active_slide] = self.start_time

    @property
    def elapsed_seconds(self) -> int:
        end = self.end_time or time.time()
        return max(0, int(end - self.start_time))

    @property
    def active_slide_elapsed_seconds(self) -> int:
        slide_start = self.slide_timestamps.get(self.active_slide, self.start_time)
        end = self.end_time or time.time()
        return max(0, int(end - slide_start))


class DefenseCoPilot:
    """Manages active thesis rehearsal sessions, pacing evaluation, and panelist questions."""

    def __init__(self, audit: Audit | None = None):
        self.audit = audit
        self.current_session: DefenseSession | None = None
        self._bank_items: list[dict] = list(CITIZENGRAPH_DEFENSE_BANK)
        self._bank_by_id: dict[str, dict] = {item["id"]: item for item in CITIZENGRAPH_DEFENSE_BANK}
        self._bank_vectors: dict[str, any] = {}
        self._initialized_bank: bool = False

    def ensure_bank_initialized(self) -> None:
        """Pre-computes and stores FastEmbed vectors in SQLite for sub-30ms offline retrieval."""
        if self._initialized_bank:
            return
        self._initialized_bank = True

        db_entries = []
        if self.audit is not None:
            try:
                self.audit.init_defense_qa_bank(self._bank_items)
                db_entries = self.audit.get_defense_qa_bank()
            except Exception as exc:
                logger.debug("Failed initializing defense_qa_bank in audit: %s", exc)

        try:
            import numpy as np
            from ..core.semantic_router import embed_text

            for entry in db_entries:
                qa_id = entry["id"]
                blob = entry.get("embedding_blob")
                if blob:
                    self._bank_vectors[qa_id] = np.frombuffer(blob, dtype=np.float32)

            for item in self._bank_items:
                qa_id = item["id"]
                if qa_id not in self._bank_vectors:
                    text_to_embed = f"{item['question']} {item['reference_answer']}"
                    vec = embed_text(text_to_embed)
                    if vec is not None:
                        self._bank_vectors[qa_id] = vec
                        if self.audit is not None:
                            try:
                                self.audit.update_defense_qa_embedding(qa_id, vec.tobytes())
                            except Exception as exc:
                                logger.debug("Failed saving embedding for %s: %s", qa_id, exc)
        except Exception as exc:
            logger.debug("FastEmbed initialization skipped in defense copilot: %s", exc)

    def get_defense_bank(self, category: str | None = None) -> list[dict]:
        """Returns defense Q&A pairs, optionally filtered by category."""
        if not category:
            return list(self._bank_items)
        cat_lower = category.lower()
        return [q for q in self._bank_items if q["category"] == cat_lower]

    def find_matching_qa(self, query_text: str, top_k: int = 1) -> list[dict]:
        """Finds closest defense Q&A pairs in <30ms using FastEmbed cosine similarity."""
        t0 = time.perf_counter()
        self.ensure_bank_initialized()
        if not self._bank_vectors:
            return [self._bank_items[0]] if self._bank_items else []

        try:
            import numpy as np
            from ..core.semantic_router import embed_text

            q_vec = embed_text(query_text)
            if q_vec is None:
                return [self._bank_items[0]]

            scores = []
            for qa_id, v in self._bank_vectors.items():
                sim = float(np.dot(q_vec, v))
                scores.append((sim, qa_id))

            scores.sort(key=lambda x: x[0], reverse=True)
            results = []
            elapsed_ms = int((time.perf_counter() - t0) * 1000)
            for sim, qa_id in scores[:top_k]:
                item = dict(self._bank_by_id[qa_id])
                item["similarity_score"] = round(sim, 3)
                item["latency_ms"] = elapsed_ms
                results.append(item)
            return results
        except Exception as exc:
            logger.debug("Vector matching failed: %s", exc)
            return [self._bank_items[0]] if self._bank_items else []

    def evaluate_answer(self, qa_id: str, candidate_answer: str) -> dict:
        """Evaluates student defense answer offline against pre-computed reference in <30ms."""
        t0 = time.perf_counter()
        self.ensure_bank_initialized()
        target = self._bank_by_id.get(qa_id)
        if not target:
            return {"error": f"Question {qa_id} not found in defense bank."}

        ans_clean = candidate_answer.lower()
        key_points = target.get("key_points", [])
        covered_points = []
        missing_points = []
        for pt in key_points:
            pt_words = [w for w in re.findall(r"\b\w+\b", pt.lower()) if len(w) > 2]
            if pt_words and any(w in ans_clean for w in pt_words):
                covered_points.append(pt)
            else:
                missing_points.append(pt)

        coverage_ratio = len(covered_points) / max(1, len(key_points))

        sim_score = coverage_ratio
        try:
            import numpy as np
            from ..core.semantic_router import embed_text

            ref_vec = self._bank_vectors.get(qa_id)
            cand_vec = embed_text(candidate_answer)
            if ref_vec is not None and cand_vec is not None:
                sim_score = max(0.0, float(np.dot(cand_vec, ref_vec)))
        except Exception as exc:
            logger.debug("Embedding similarity failed in evaluate_answer: %s", exc)

        composite = round(0.60 * sim_score + 0.40 * coverage_ratio, 3)
        grade = "Strong Defense" if composite >= 0.80 else "Adequate Defense" if composite >= 0.60 else "Needs Revision"
        elapsed_ms = int((time.perf_counter() - t0) * 1000)

        return {
            "qa_id": qa_id,
            "question": target["question"],
            "score": composite,
            "similarity": round(sim_score, 3),
            "grade": grade,
            "key_points_covered": covered_points,
            "key_points_missing": missing_points,
            "reference_answer": target["reference_answer"],
            "latency_ms": elapsed_ms,
        }

    def start_session(
        self,
        presentation_path: Path,
        total_slides: int = 10,
        target_duration_s: int = 720,
    ) -> DefenseSession:
        """Initializes a new defense rehearsal session."""
        session = DefenseSession(
            presentation_path=presentation_path,
            start_time=time.time(),
            active_slide=1,
            total_slides=total_slides,
            target_duration_s=target_duration_s,
        )
        self.current_session = session
        return session

    def advance_slide(self, new_slide_num: int) -> None:
        """Records slide transition timestamp."""
        if self.current_session:
            self.current_session.active_slide = new_slide_num
            self.current_session.slide_timestamps[new_slide_num] = time.time()

    def get_pacing_status(self, session: DefenseSession | None = None) -> dict:
        """Evaluates whether the rehearsal is on pace, nearing limit, or over budget."""
        sess = session or self.current_session
        if not sess:
            return {"status": "inactive", "elapsed_seconds": 0, "slide": 1, "advice": "No active rehearsal."}

        elapsed = sess.elapsed_seconds
        slide_elapsed = sess.active_slide_elapsed_seconds
        current_slide = sess.active_slide
        budget_for_slide = DEFAULT_SLIDE_PACING_BUDGET.get(current_slide, 75)

        remaining_total = max(0, sess.target_duration_s - elapsed)

        if slide_elapsed > (budget_for_slide + 30):
            status = "over_budget"
            advice = f"You have spent {slide_elapsed // 60}m {slide_elapsed % 60}s on Slide {current_slide}. Recommend advancing to stay on schedule."
        elif slide_elapsed > budget_for_slide:
            status = "nearing_limit"
            advice = f"Slide {current_slide} time target reached ({budget_for_slide}s). Wrap up this slide's core points."
        else:
            status = "on_pace"
            advice = f"On pace. {budget_for_slide - slide_elapsed}s remaining on this slide."

        return {
            "status": status,
            "elapsed_seconds": elapsed,
            "remaining_seconds": remaining_total,
            "slide_elapsed_seconds": slide_elapsed,
            "slide": current_slide,
            "total_slides": sess.total_slides,
            "advice": advice,
        }

    def generate_panelist_question(
        self,
        session: DefenseSession | None = None,
        slide_topic: str = "",
        slide_text: str = "",
    ) -> str:
        """Selects or dynamically synthesizes a realistic academic defense interrogation question."""
        sess = session or self.current_session
        topic_lower = f"{slide_topic} {slide_text}".lower()

        # Categorize by topic keywords
        category = "general"
        if re.search(r"\bast\b", topic_lower) or any(w in topic_lower for w in ["method", "algorithm", "return-trip", "so-4", "so-5", "sequence", "formula"]):
            category = "methodology"
        elif any(w in topic_lower for w in ["architecture", "clearance", "security", "fastapi", "tier", "schema", "database", "sqlite"]):
            category = "architecture"
        elif any(w in topic_lower for w in ["problem", "statement", "objective", "scope", "background", "grievance"]):
            category = "problem"
        elif any(w in topic_lower for w in ["result", "benchmark", "evaluation", "latency", "90%", "95%", "experiment"]):
            category = "results"

        candidates = PANELIST_QUESTIONS_BY_TOPIC.get(category, PANELIST_QUESTIONS_BY_TOPIC["general"])
        
        # Avoid immediate repetition if possible
        asked = set(sess.questions_asked) if sess else set()
        unasked = [q for q in candidates if q not in asked]
        chosen = random.choice(unasked if unasked else candidates)

        if sess:
            sess.questions_asked.append(chosen)

        return chosen

    def stop_session(self, audit: Audit | None = None) -> dict:
        """Stops active rehearsal, compiles metrics, and persists to SQLite."""
        if not self.current_session:
            return {"active": False, "duration": 0, "slides_covered": 0}

        sess = self.current_session
        sess.end_time = time.time()
        duration = sess.elapsed_seconds
        slides_count = len(sess.slide_timestamps)
        questions_count = len(sess.questions_asked)

        pacing_summary = "On Pace" if duration <= sess.target_duration_s else f"Over Budget by {(duration - sess.target_duration_s) // 60}m"

        if audit:
            try:
                audit.add_defense_session(
                    presentation_name=sess.presentation_path.name,
                    duration_seconds=duration,
                    slides_count=slides_count,
                    questions_count=questions_count,
                    pacing_summary=pacing_summary,
                )
            except Exception as exc:
                logger.debug("Failed saving defense session to audit: %s", exc)

        summary = {
            "presentation_name": sess.presentation_path.name,
            "duration_seconds": duration,
            "duration_formatted": f"{duration // 60}m {duration % 60}s",
            "slides_count": slides_count,
            "questions_count": questions_count,
            "pacing_summary": pacing_summary,
        }

        self.current_session = None
        return summary
