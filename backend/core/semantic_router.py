"""Semantic intent router using a lightweight embedding model (fastembed ONNX).

Runs in ~5-10ms on CPU. Matches queries that miss exact regexes (e.g. "who are you again",
"what is your capability", "open access database") against canonical intent exemplars.
"""
from __future__ import annotations

import logging
import os
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .router import Intent

# Ensure HuggingFace mirror / settings are friendly on Windows
os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")

logger = logging.getLogger("nightmare.semantic_router")

# Canonical intents and reference exemplars
CANONICAL_INTENTS: dict[str, list[str]] = {
    "quick_reply:name": [
        "what is your name", "who are you", "who are you again", "what's your name again",
        "what are you", "what should i call you", "tell me who you are", "identify yourself",
    ],
    "quick_reply:greet": [
        "hello nightmare", "hey nightmare", "are you there", "nightmare", "mic check", "testing mic",
    ],
    "quick_reply:help": [
        "what can you do", "help", "what is your capability", "what are your capabilities",
        "what is nightmare can do", "what can nightmare do", "list your commands", "show commands",
        "how can you help me",
    ],
    "quick_reply:helper": [
        "open helper function", "nightmare open helper function", "open developer helper function",
        "developer helper function", "open helper", "open helper ui", "show helper function",
        "show developer helper function", "display helper function", "launch helper function",
    ],
    "quick_reply:sleep": [
        "go to sleep", "you're not doing anything go to sleep", "going to sleep", "sleep now",
        "good night nightmare", "put nightmare to sleep", "sleep mode please",
    ],
    "quick_reply:time": [
        "what time is it", "current time", "what is the date today", "tell me the time",
        "date today", "what date is it", "tell me what time it is",
    ],
    "quick_reply:thanks": [
        "thank you nightmare", "thanks a lot", "thanks nightmare", "thank you so much",
    ],
    "weather": [
        "what is the weather", "weather forecast", "how hot is it", "is it raining outside",
        "how cold is it", "what is the temperature", "check the weather",
    ],
    "list_facts": [
        "what do you remember", "do you remember", "what have i told you", "what do you know about me",
        "list my memories", "show your memories", "what do you remember about me",
    ],
    "list_notes": [
        "what are my reminders", "reminder for today", "do i have a reminder for today", "notes right now",
        "show my reminders", "list my notes", "any reminders today", "tell me my notes",
        "minors for today do i have a reminder for today",
    ],
    "list_projects": [
        "list my projects", "what projects are on my desktop", "show my projects", "projects on desktop",
        "what are the projects", "how many active projects i have", "how many projects do i have",
        "how many projects i have", "count my projects", "how many projects are there", "total projects on desktop",
    ],
    "conversation_history": [
        "earlier what we have discussed earlier", "what did we discuss earlier", "what was our previous conversation",
        "what was our previous conversation was", "what were we talking about", "what did we talk about earlier",
        "what did i ask earlier", "recap our conversation", "recap recent conversation",
    ],
    "voice_settings:female": [
        "switch voice to female", "change female voice", "change voice to female", "use female voice",
        "switch to female voice", "female voice", "set voice to female",
    ],
    "voice_settings:male": [
        "switch voice to male", "change male voice", "change voice to male", "use male voice",
        "switch to male voice", "male voice", "set voice to male",
    ],
    "cross_project": [
        "which project needs attention", "compare all my projects", "overview of all projects",
        "catch me up on all projects", "status of all projects", "summarize all projects",
    ],
    "workspace_briefing": [
        "workspace briefing", "daily briefing", "give me a briefing", "workspace status",
        "workspace health", "how are my projects doing", "give me an overview of my workspace",
    ],
    "workspace_changes": [
        "what changed since yesterday", "changes since yesterday", "recent changes across projects",
        "what did i change today", "changes today", "what changed recently",
    ],
    "work_priorities": [
        "what should i work on", "which project should i work on", "where should i start",
        "project priorities", "what should i do next", "what project needs work",
    ],
    "rerun_task": [
        "run it again", "run that again", "rerun last task", "retry that", "run again",
    ],
    "db_open": [
        "open database", "database access open", "open access database", "access database", "show database",
    ],
    "db_close": [
        "close database", "database access close", "hide database", "lock database",
    ],
    "settings_open": [
        "open settings", "manage allowlist", "edit settings", "change allowlist", "settings open",
        "can you open the settings menu",
    ],
    "settings_close": [
        "close settings", "settings close", "lock settings",
    ],
    "reset_session": [
        "start a new session", "clear conversation", "reset conversation", "clear history", "start fresh",
    ],
    "usage": [
        "how many calls today", "usage stats", "how many calls did you make today", "model call usage",
        "how many calls we have today",
    ],
    "clearance_elevate:3": [
        "nightmare open level 3", "open level 3", "elevate to level 3", "level 3 access", "unlock level 3",
        "open nightmare level 3", "elevate clearance to level 3",
    ],
    "clearance_elevate:5": [
        "nightmare open level 5", "open level 5", "elevate to level 5", "level 5 access", "unlock level 5",
        "open nightmare level 5", "elevate clearance to level 5",
    ],
    "clearance_lockdown": [
        "lock down", "nightmare lock down", "drop to level 1", "lockdown now", "emergency lockdown",
        "reset clearance to level 1", "reset clearance",
    ],
    "clearance_status": [
        "what is my clearance level", "what is my clearance", "check clearance level", "current clearance level",
        "what level am i", "check my clearance", "what's my clearance level",
    ],
    "clear_cache": [
        "clear cache", "clear summary cache", "reset summary cache", "flush cache",
        "wipe summary cache", "refresh cache", "clear all cached summaries", "reset cache",
    ],
    "open_file": [
        "find file related to timeline and open it in word or powerpoint",
        "open citizengraph ppt",
        "find file related to roadmap and open it",
        "open budget in excel",
        "open report in word",
        "find document and open it",
        "open presentation file",
        "find spreadsheet and open it",
        "find citizen graph chapter 1 docs and open it on word",
        "comments and find citizen graph chapter 1 docs and open it on word",
        "ilcro interview checklist and open it in word",
        "open thesis checklist in word",
        "open chapter 1 docs",
        "open document in word",
    ],
    "github_check": [
        "check my github repositories for commits pull requests merge conflicts",
        "check github repositories",
        "check github repos",
        "check my github repositories",
        "check github pull requests",
        "check for merge conflicts",
        "github repository status",
        "check github status",
        "any merge conflicts on github",
        "check my pull requests on github",
    ],
    "progress": [
        "progress of project nightmare",
        "what's the latest progress of project nightmare",
        "give me the new progress",
        "tell me the new handoff",
        "what is the latest progress of citizengraph",
        "fresh progress on project",
        "latest update on project",
    ],
    "system_authority:restart_nightmare": [
        "rerun yourself", "restart nightmare", "reboot nightmare", "restart nightmare assistant",
    ],
    "system_authority:restart_pc": [
        "restart my pc", "reboot my pc", "restart the computer", "restart my computer", "reboot the system",
    ],
    "system_authority:shutdown_pc": [
        "shut down my pc", "shutdown my pc", "power off my pc", "turn off the pc", "shut down the computer",
    ],
    "system_authority:cancel_shutdown": [
        "cancel shutdown", "abort shutdown", "cancel pc shutdown", "stop shutdown",
    ],
    "ppt_control:next": [
        "next slide", "advance slide", "go to next slide",
    ],
    "ppt_control:prev": [
        "previous slide", "prev slide", "go back one slide",
    ],
    "team_progress": [
        "show team progress", "open timeline tracker", "check team progress",
        "check team 1 progress", "team progress", "timeline tracker",
        "show the development timeline", "how is the team doing on quotas",
        "citizengraph timeline", "show citizengraph thesis timeline",
    ],
    "timeline_diff": [
        "nightmare what change in the citizengraph timeline from the gdrive",
        "what changed in the citizengraph timeline",
        "compare citizengraph timeline with gdrive",
        "check gdrive timeline updates",
        "what did my team update in the timeline",
        "check timeline diff",
        "timeline changes from gdrive",
        "diff citizengraph timeline",
    ],
    "approve_email": [
        "approve email", "send the reminder email", "approve team reminder",
        "approve the email draft", "confirm and send email",
    ],
}


class SemanticRouter:
    """Computes embeddings using FastEmbed ONNX and finds cosine similarity with canonical intents."""

    def __init__(self, model_name: str = "BAAI/bge-small-en-v1.5"):
        self.model_name = model_name
        self._model = None
        self._embs_norm = None
        self._exemplar_texts: list[str] = []
        self._exemplar_intents: list[str] = []
        self._initialized = False

    def _ensure_initialized(self) -> bool:
        if self._initialized:
            return self._model is not None

        self._initialized = True
        try:
            from fastembed import TextEmbedding
            import numpy as np
        except ImportError:
            logger.warning("fastembed is not installed; semantic routing disabled.")
            return False

        try:
            self._model = TextEmbedding(model_name=self.model_name)
            for intent_key, phrases in CANONICAL_INTENTS.items():
                for p in phrases:
                    self._exemplar_texts.append(p)
                    self._exemplar_intents.append(intent_key)

            embs = np.array(list(self._model.embed(self._exemplar_texts)))
            norms = np.linalg.norm(embs, axis=1, keepdims=True)
            self._embs_norm = embs / np.maximum(norms, 1e-9)
            return True
        except Exception as exc:
            logger.warning("Could not initialize semantic router: %s", exc)
            self._model = None
            return False

    def warmup(self) -> bool:
        """Pre-loads the ONNX model and computes exemplar embeddings."""
        return self._ensure_initialized()

    def match(self, text: str, threshold: float = 0.82) -> tuple[str, float, str] | None:
        """Returns (intent_key, similarity_score, matched_exemplar) or None."""
        clean = " ".join(text.strip().split())
        if not clean or len(clean) > 200:
            return None

        if not self._ensure_initialized() or self._model is None or self._embs_norm is None:
            return None

        try:
            import numpy as np
            q_emb = np.array(list(self._model.embed([clean])))[0]
            norm = np.linalg.norm(q_emb)
            if norm == 0:
                return None
            q_emb_norm = q_emb / norm

            sims = np.dot(self._embs_norm, q_emb_norm)
            best_idx = int(np.argmax(sims))
            best_score = float(sims[best_idx])

            if best_score >= threshold:
                return self._exemplar_intents[best_idx], best_score, self._exemplar_texts[best_idx]
            return None
        except Exception as exc:
            logger.debug("Semantic matching failed: %s", exc)
            return None


# Global singleton instance
_router_instance: SemanticRouter | None = None


def get_semantic_router() -> SemanticRouter:
    global _router_instance
    if _router_instance is None:
        _router_instance = SemanticRouter()
    return _router_instance


def warmup_semantic_router() -> bool:
    """Pre-loads FastEmbed model and precomputes exemplar embeddings into RAM."""
    return get_semantic_router().warmup()


def match_semantic_intent(text: str, threshold: float = 0.82) -> "Intent | None":
    """Maps freeform text to an Intent if semantic similarity >= threshold, else None."""
    from .router import Intent

    router = get_semantic_router()
    matched = router.match(text, threshold=threshold)
    if matched is None:
        return None

    intent_key, score, exemplar = matched
    logger.info("Semantic match: '%s' -> %s (score %.3f via '%s')", text, intent_key, score, exemplar)

    if intent_key.startswith("quick_reply:"):
        sub = intent_key.split(":", 1)[1]
        return Intent("quick_reply", text, note_text=sub)

    if intent_key.startswith("voice_settings:"):
        gender = intent_key.split(":", 1)[1]
        return Intent("voice_settings", text, voice_gender=gender)

    if intent_key.startswith("clearance_elevate:"):
        lvl = intent_key.split(":", 1)[1]
        return Intent("clearance_prompt", text, query=lvl)

    if intent_key == "clearance_lockdown":
        return Intent("clearance_lockdown", text)

    if intent_key == "clearance_status":
        return Intent("clearance_status", text)

    if intent_key == "clear_cache":
        return Intent("clear_cache", text)

    if intent_key == "team_progress":
        from .router import _match_team_progress
        p = _match_team_progress(text)
        return p if p is not None else Intent("team_progress", text)

    if intent_key == "timeline_diff":
        return Intent("timeline_diff", text)

    if intent_key == "approve_email":
        return Intent("approve_email", text)

    if intent_key.startswith("system_authority:"):
        act = intent_key.split(":", 1)[1]
        return Intent("system_authority", text, action=act)

    if intent_key == "ppt_control:next":
        return Intent("ppt_control", text, action="next")

    if intent_key == "ppt_control:prev":
        return Intent("ppt_control", text, action="previous")

    if intent_key == "open_file":
        from ..tools.file_navigator import parse_file_query
        q, exts = parse_file_query(text)
        ext_hint = next(iter(exts)) if exts else None
        return Intent("open_file", text, query=q or text, note_text=ext_hint)

    if intent_key == "progress":
        from .router import _resolve_with_followup, normalize
        from ..config import get_settings
        s = get_settings()
        res = _resolve_with_followup(text, normalize(text), s.desktop_root, None)
        return Intent("progress", text, resolution=res)

    return Intent(intent_key, text)
