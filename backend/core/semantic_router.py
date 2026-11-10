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
        "wake up", "wakeup", "wake up nightmare", "nightmare wake up", "wake up please",
        "you are getting smart nightmare", "you are getting smart",
    ],
    "quick_reply:model_identity": [
        "what model powers you", "what model are you", "who powers you", "what model is powering you",
        "who trained you", "what model is running you", "are you chatgpt", "are you gemini",
        "i am trained by my developer", "i am not powered by any model",
        "i am trained by my developer to be fully aware with its everyday setup",
        "you don't need to include this Google AI Pro quota",
    ],
    "developer_info": [
        "who is your developer", "who is the developer", "who developed you",
        "tell me about your developer", "who is adrian", "who is adrian garcia",
        "who created you", "who made you", "who programmed you", "who built you",
        "who is adrian girlfriend", "who is adrian ex girlfriend",
    ],
    "developer_why": [
        "why did adrian develop you", "why you are develop", "why were you developed",
        "why did adrian build you", "why did adrian make you", "why did adrian create you",
        "why are you developed", "why were you created", "why do you exist", "what is your purpose",
    ],
    "open_portfolio": [
        "open that link", "open the link", "open your developers portfolio web",
        "open your developer's portfolio", "open adrian portfolio", "open developer portfolio",
        "open the portfolio", "visit your developers portfolio", "open that website",
        "how many have visited my portfolio today", "how many have visited my portfolio",
    ],
    "developer_skills": [
        "what are adrian's skills", "what are your developer's skills", "what is adrian's tech stack",
        "what tech stack does adrian use", "what does adrian specialize in",
    ],
    "developer_projects": [
        "what other projects did adrian build", "what did adrian create", "what projects did your developer make",
        "what projects did adrian build",
    ],
    "system_telemetry": [
        "how is my laptop running", "laptop hardware status", "pc hardware health",
        "check hardware telemetry", "hardware telemetry", "check my hardware", "how is my pc running",
        "how much ram is used", "how much memory is used", "cpu load",
    ],
    "system_battery": [
        "check battery", "battery status", "how is my battery", "is ac plugged in",
        "check battery and thermals", "battery percentage", "battery level",
    ],
    "system_processes": [
        "what is using my memory", "which app is eating ram", "top processes",
        "heavy processes", "list heavy processes", "what is eating my ram",
        "what processes are running", "which processes are running",
    ],
    "defense_start": [
        "start defense rehearsal", "activate defense mode", "start mock defense",
        "start thesis rehearsal", "begin defense practice", "thesis defense mode",
    ],
    "defense_stop": [
        "stop defense rehearsal", "stop defense mode", "end defense rehearsal",
        "finish rehearsal", "exit defense mode",
    ],
    "defense_question": [
        "ask defense question", "panelist question", "ask panelist question",
        "panelist interrogation", "challenge me on this slide", "ask a question about this slide",
        "mock panelist question",
    ],
    "defense_status": [
        "defense timing", "how is my defense pace", "rehearsal pace", "defense pace",
        "check defense timing", "how is my rehearsal time",
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
        "give me some quote of the day", "give me some qoute of the day", "what are we going to do today", "quote of the day",
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
    "open_team_excel": [
        "open citizengraph timeline in excel", "open citizengraph thesis timeline in excel",
        "open timeline in excel", "launch citizengraph timeline in excel",
        "open team timeline in excel", "open thesis timeline in excel",
    ],
    "approve_email": [
        "approve email", "send the reminder email", "approve team reminder",
        "approve the email draft", "confirm and send email",
    ],
    "email_report": [
        "check my priority emails", "read my inbox", "do i have any new emails",
        "check priority emails", "read inbox", "check the inbox",
        "do i have any emails", "email report", "check priority inbox",
    ],
    "calendar_query": [
        "what are in my calendar", "what is in my calendar", "what is on my calendar", "check my calendar",
        "do i have any meetings this week", "any meetings this week", "show my calendar events",
    ],
    "measurable_task": [
        "have any task", "do i have any tasks", "what are my tasks", "list my tasks", "check my tasks",
        "open task", "list measurable tasks",
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

            # Load persistent custom exemplars from SQLite if table exists
            try:
                import sqlite3
                from pathlib import Path
                db_p = Path(__file__).resolve().parent.parent / "nightmare.db"
                if db_p.is_file():
                    with sqlite3.connect(db_p) as conn:
                        tbl = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='custom_exemplars'").fetchone()
                        if tbl:
                            for i_row, p_row in conn.execute("SELECT intent, phrase FROM custom_exemplars").fetchall():
                                if p_row and i_row:
                                    self._exemplar_texts.append(p_row)
                                    self._exemplar_intents.append(i_row)
            except Exception as exc:
                logger.debug("Failed loading custom exemplars: %s", exc)

            embs = np.array(list(self._model.embed(self._exemplar_texts)))
            norms = np.linalg.norm(embs, axis=1, keepdims=True)
            self._embs_norm = embs / np.maximum(norms, 1e-9)
            return True
        except Exception as exc:
            logger.warning("Could not initialize semantic router: %s", exc)
            self._model = None
            return False

    def add_custom_exemplar(self, intent: str, phrase: str) -> bool:
        """Dynamically adds an approved exemplar and updates normalized embeddings in-memory."""
        if not self._ensure_initialized() or self._model is None:
            return False
        try:
            import numpy as np
            clean = phrase.strip()
            new_emb = np.array(list(self._model.embed([clean])))[0]
            norm = np.linalg.norm(new_emb)
            if norm > 0:
                new_emb_norm = new_emb / norm
                self._exemplar_texts.append(clean)
                self._exemplar_intents.append(intent)
                if self._embs_norm is not None:
                    self._embs_norm = np.vstack([self._embs_norm, new_emb_norm])
                else:
                    self._embs_norm = np.array([new_emb_norm])
                return True
        except Exception as exc:
            logger.warning("Failed adding custom exemplar: %s", exc)
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
                matched_intent = self._exemplar_intents[best_idx]
                # Guard: Never allow wake up queries to map to sleep mode
                if "sleep" in matched_intent and any(w in clean.lower() for w in ("wake up", "wakeup", "wake")):
                    return "quick_reply:greet", 0.95, "wake up nightmare"
                return matched_intent, best_score, self._exemplar_texts[best_idx]
            return None
        except Exception as exc:
            logger.debug("Semantic matching failed: %s", exc)
            return None

    def find_top_candidates(self, text: str, top_k: int = 2) -> list[tuple[str, float]]:
        """Returns top_k (intent_name, similarity_score) sorted descending by score."""
        clean = " ".join(text.strip().split())
        if not clean:
            return []
        if not self._ensure_initialized() or self._model is None or self._embs_norm is None:
            return []
        try:
            import numpy as np
            q_emb = np.array(list(self._model.embed([clean])))[0]
            norm = np.linalg.norm(q_emb)
            if norm == 0:
                return []
            q_emb_norm = q_emb / norm
            sims = np.dot(self._embs_norm, q_emb_norm)
            intent_scores: dict[str, float] = {}
            for intent, score in zip(self._exemplar_intents, sims):
                score_val = float(score)
                if intent not in intent_scores or score_val > intent_scores[intent]:
                    intent_scores[intent] = score_val
            sorted_intents = sorted(intent_scores.items(), key=lambda kv: -kv[1])
            return sorted_intents[:top_k]
        except Exception as exc:
            logger.debug("Finding top candidates failed: %s", exc)
            return []


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


def find_top_candidates(text: str, top_k: int = 2) -> list[tuple[str, float]]:
    """Returns top_k (intent_name, score) candidates using semantic similarity."""
    return get_semantic_router().find_top_candidates(text, top_k=top_k)


def embed_text(text: str):
    """Computes a normalized 1D float32 embedding vector for text using the loaded FastEmbed model."""
    router = get_semantic_router()
    if not router._ensure_initialized() or router._model is None:
        return None
    try:
        import numpy as np
        emb = np.array(list(router._model.embed([text.strip()])))[0].astype(np.float32)
        norm = float(np.linalg.norm(emb))
        if norm > 0:
            return (emb / norm).astype(np.float32)
        return emb
    except Exception as exc:
        logger.debug("Failed computing embedding: %s", exc)
        return None


def embed_texts(texts: list[str]):
    """Computes normalized 1D float32 embedding vectors for multiple texts in a batch."""
    router = get_semantic_router()
    if not router._ensure_initialized() or router._model is None:
        return None
    try:
        import numpy as np
        clean_texts = [t.strip() for t in texts]
        embs = np.array(list(router._model.embed(clean_texts))).astype(np.float32)
        norms = np.linalg.norm(embs, axis=1, keepdims=True)
        return [e.astype(np.float32) for e in (embs / np.maximum(norms, 1e-9))]
    except Exception as exc:
        logger.debug("Failed computing batch embeddings: %s", exc)
        return None


INTENT_FRIENDLY_NAMES: dict[str, str] = {
    "quick_reply:name": "asking my name",
    "quick_reply:greet": "greeting Nightmare",
    "quick_reply:model_identity": "asking what model powers me",
    "quick_reply:help": "asking for help and capabilities",
    "quick_reply:helper": "opening developer helper function",
    "quick_reply:time": "asking for the time or date",
    "quick_reply:thanks": "saying thank you",
    "quick_reply:sleep": "putting Nightmare to sleep",
    "developer_info": "asking about developer Adrian Garcia",
    "developer_why": "asking why Adrian developed Nightmare",
    "developer_skills": "asking about Adrian's technical skills",
    "developer_projects": "asking about Adrian's projects",
    "open_portfolio": "opening Adrian's developer portfolio",
    "system_telemetry": "checking system hardware telemetry",
    "system_battery": "checking battery and power status",
    "system_processes": "checking running system processes",
    "defense_start": "starting thesis defense rehearsal",
    "defense_stop": "stopping defense rehearsal",
    "defense_question": "asking a thesis defense mock question",
    "defense_status": "checking thesis defense pacing",
    "weather": "checking the weather forecast",
    "list_facts": "checking memories",
    "list_notes": "checking your notes and reminders",
    "list_projects": "listing your Desktop projects",
    "conversation_history": "recapping earlier conversation",
    "cross_project": "summarizing all Desktop projects",
    "workspace_briefing": "getting your workspace daily briefing",
    "workspace_changes": "checking recent workspace changes",
    "work_priorities": "checking your project work priorities",
    "rerun_task": "rerunning the last dev task",
    "db_open": "opening database records",
    "db_close": "closing database access",
    "settings_open": "opening Nightmare settings",
    "settings_close": "closing settings",
    "reset_session": "starting a fresh session",
    "usage": "checking AI quota usage",
    "clearance_lockdown": "locking down clearance to Level 1",
    "clearance_status": "checking current clearance level",
    "clear_cache": "clearing cached summaries",
    "open_file": "finding or opening a file",
    "github_check": "checking GitHub repositories",
    "progress": "checking project progress",
    "team_progress": "checking CitizenGraph team timeline",
    "timeline_diff": "checking timeline updates from GDrive",
    "open_team_excel": "opening CitizenGraph timeline in Excel",
    "approve_email": "approving the team reminder email",
    "email_report": "checking your priority emails",
    "calendar_query": "checking your calendar schedule",
    "measurable_task": "checking measurable tasks",
}


def friendly_intent_name(key: str) -> str:
    if key.startswith("clearance_elevate:"):
        lvl = key.split(":", 1)[1]
        return f"elevating clearance to Level {lvl}"
    if key.startswith("voice_settings:"):
        gender = key.split(":", 1)[1]
        return f"switching voice to {gender}"
    if key.startswith("system_authority:"):
        act = key.split(":", 1)[1]
        return f"performing system {act}"
    return INTENT_FRIENDLY_NAMES.get(key, key.replace("_", " "))


def match_semantic_intent(text: str, threshold: float = 0.82) -> "Intent | None":
    """Maps freeform text to an Intent if semantic similarity >= threshold or returns clarification if ambiguous."""
    import re
    if re.search(r"\b(joke|jokes|pun|puns|funny|humor|story|poem)\b", text, re.I):
        return None

    from .router import Intent

    router = get_semantic_router()
    candidates = router.find_top_candidates(text, top_k=2)
    if not candidates:
        return None

    top1_intent, s1 = candidates[0]
    top2_intent, s2 = candidates[1] if len(candidates) > 1 else ("", 0.0)
    delta = s1 - s2

    # Ambiguous band clarification: s1 in [0.785, threshold) and delta < 0.06
    if 0.785 <= s1 < threshold and delta < 0.06 and top2_intent:
        name1 = friendly_intent_name(top1_intent)
        name2 = friendly_intent_name(top2_intent)
        res_intent = Intent("clarification", text, options=[top1_intent, top2_intent], query=f"Did you mean {name1} or {name2}?")
        res_intent.router_path = "semantic_clarification"
        res_intent.confidence_margin = round(float(delta), 4)
        return res_intent

    matched = router.match(text, threshold=threshold)
    if matched is None:
        return None
    intent_key, score, exemplar = matched
    logger.info("Semantic match: '%s' -> %s (score %.3f via '%s')", text, intent_key, score, exemplar)

    res_intent: Intent
    if intent_key.startswith("quick_reply:"):
        sub = intent_key.split(":", 1)[1]
        res_intent = Intent("quick_reply", text, note_text=sub)
    elif intent_key.startswith("voice_settings:"):
        gender = intent_key.split(":", 1)[1]
        res_intent = Intent("voice_settings", text, voice_gender=gender)
    elif intent_key.startswith("clearance_elevate:"):
        lvl = intent_key.split(":", 1)[1]
        res_intent = Intent("clearance_prompt", text, query=lvl)
    elif intent_key == "clearance_lockdown":
        res_intent = Intent("clearance_lockdown", text)
    elif intent_key == "clearance_status":
        res_intent = Intent("clearance_status", text)
    elif intent_key == "clear_cache":
        res_intent = Intent("clear_cache", text)
    elif intent_key == "team_progress":
        from .router import _match_team_progress
        p = _match_team_progress(text)
        if p is not None:
            res_intent = p
        elif any(w in text.lower() for w in ("timeline", "progress", "tracker", "quota", "wbs")):
            res_intent = Intent("team_progress", text)
        else:
            return None
    elif intent_key == "timeline_diff":
        res_intent = Intent("timeline_diff", text)
    elif intent_key == "open_team_excel":
        res_intent = Intent("open_team_excel", text)
    elif intent_key == "approve_email":
        res_intent = Intent("approve_email", text)
    elif intent_key == "email_report":
        res_intent = Intent("email_report", text)
    elif intent_key == "calendar_query":
        tf = "today" if "today" in text.lower() else "this week"
        res_intent = Intent("calendar_query", text, query=tf)
    elif intent_key == "measurable_task":
        res_intent = Intent("measurable_task", text, action="list")
    elif intent_key.startswith("system_authority:"):
        act = intent_key.split(":", 1)[1]
        res_intent = Intent("system_authority", text, action=act)
    elif intent_key == "ppt_control:next":
        res_intent = Intent("ppt_control", text, action="next")
    elif intent_key == "ppt_control:prev":
        res_intent = Intent("ppt_control", text, action="previous")
    elif intent_key == "open_file":
        from ..tools.file_navigator import parse_file_query
        q, exts = parse_file_query(text)
        ext_hint = next(iter(exts)) if exts else None
        res_intent = Intent("open_file", text, query=q or text, note_text=ext_hint)
    elif intent_key == "progress":
        from .router import _resolve_with_followup, normalize
        from ..config import Settings
        s = Settings.from_env()
        res = _resolve_with_followup(text, normalize(text), s.desktop_root, None)
        res_intent = Intent("progress", text, resolution=res)
    else:
        res_intent = Intent(intent_key, text)

    res_intent.router_path = "semantic"
    res_intent.confidence_margin = round(float(score), 4)
    return res_intent
