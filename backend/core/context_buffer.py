"""Deterministic Stateful Conversation Context Buffer (Layer 2).

Maintains short-term conversational memory with a 120-second TTL:
- `last_candidates: list[str]`: candidate paths/filenames from previous disambiguation or searches
- `last_opened_file: str | None`: most recent file opened or presented
- `last_intent: str | None`: most recent intent
- `pending_slots: dict`: incomplete slot values awaiting follow-up turn

Resolves ordinal follow-ups ("the first one", "#1", "the Readme.md") in <5 ms.
Resolves coreference pronouns ("present it", "open it", "read it") against last_opened_file.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import logging
from pathlib import Path
import re
import time

logger = logging.getLogger("nightmare.context_buffer")

ORDINAL_MAP: dict[str, int] = {
    "first": 0, "1st": 0, "the first": 0, "the first one": 0, "first one": 0, "1": 0, "#1": 0, "number 1": 0, "option 1": 0, "choice 1": 0,
    "second": 1, "2nd": 1, "the second": 1, "the second one": 1, "second one": 1, "2": 1, "#2": 1, "number 2": 1, "option 2": 1, "choice 2": 1,
    "third": 2, "3rd": 2, "the third": 2, "the third one": 2, "third one": 2, "3": 2, "#3": 2, "number 3": 2, "option 3": 2, "choice 3": 2,
    "fourth": 3, "4th": 3, "the fourth": 3, "the fourth one": 3, "fourth one": 3, "4": 3, "#4": 3,
    "fifth": 4, "5th": 4, "the fifth": 4, "the fifth one": 4, "fifth one": 4, "5": 4, "#5": 4,
}

WORD_NUMBERS: dict[str, int] = {
    "one": 0, "two": 1, "three": 2, "four": 3, "five": 4,
}

PRESENT_PRONOUNS_RE = re.compile(
    r"^\s*(?:(?:hey|ok|hi)\s+)?(?:nightmare[, ]+)?(?:please\s+)?(?:"
    r"present\s+(?:it|this|that)|"
    r"start\s+(?:the\s+)?presentation|"
    r"show\s+(?:it|this|that)\s+(?:in|on)\s+powerpoint|"
    r"present\s+(?:the\s+)?slides|"
    r"run\s+(?:the\s+)?slideshow"
    r")\s*[.!?]*$",
    re.I,
)

OPEN_PRONOUNS_RE = re.compile(
    r"^\s*(?:(?:hey|ok|hi)\s+)?(?:nightmare[, ]+)?(?:please\s+)?(?:"
    r"open\s+(?:it|this|that)|"
    r"read\s+(?:it|this|that)|"
    r"launch\s+(?:it|this|that)|"
    r"view\s+(?:it|this|that)"
    r")\s*[.!?]*$",
    re.I,
)


@dataclass
class ConversationContext:
    last_candidates: list[str] = field(default_factory=list)
    last_opened_file: str | None = None
    last_intent: str | None = None
    pending_slots: dict = field(default_factory=dict)
    updated_at: float = field(default_factory=time.monotonic)
    ttl_sec: float = 120.0

    def is_expired(self) -> bool:
        return (time.monotonic() - self.updated_at) > self.ttl_sec

    def update(
        self,
        *,
        last_candidates: list[str] | list[Path] | None = None,
        last_opened_file: str | Path | None = None,
        last_intent: str | None = None,
        pending_slots: dict | None = None,
    ) -> None:
        """Updates buffer state and refreshes TTL."""
        if self.is_expired():
            self.last_candidates = []
            self.last_opened_file = None
            self.last_intent = None
            self.pending_slots = {}

        self.updated_at = time.monotonic()
        if last_candidates is not None:
            self.last_candidates = [str(c) for c in last_candidates]
        if last_opened_file is not None:
            self.last_opened_file = str(last_opened_file)
        if last_intent is not None:
            self.last_intent = last_intent
        if pending_slots is not None:
            self.pending_slots = dict(pending_slots)

    def clear(self) -> None:
        self.last_candidates.clear()
        self.last_opened_file = None
        self.last_intent = None
        self.pending_slots.clear()
        self.updated_at = 0.0

    def resolve_ordinal(self, text: str) -> str | None:
        """Resolves ordinal follow-ups ('the first one', '#1', 'the second one', 'the Readme.md')
        against last_candidates in <5 ms. Returns candidate string or None.
        """
        if self.is_expired() or not self.last_candidates:
            return None

        clean = text.strip().lower()
        clean = re.sub(r"^\s*(?:(?:hey|ok|hi)\s+)?(?:nightmare[, ]+)?(?:please\s+)?", "", clean, flags=re.I).strip(" .,?!")
        c = re.sub(r"^\s*(?:open|select|pick|choose|launch|view|get)\s+(?:the\s+)?", "", clean, flags=re.I).strip(" .,?!")

        # 1. Exact ordinal match in ORDINAL_MAP
        if c in ORDINAL_MAP:
            idx = ORDINAL_MAP[c]
            if 0 <= idx < len(self.last_candidates):
                return self.last_candidates[idx]

        # 2. Ordinal phrase match: "the first one", "first option", "the 2nd choice", "#1"
        m_ord = re.match(
            r"^(?:(?:the\s+)?(first|1st|second|2nd|third|3rd|fourth|4th|fifth|5th)(?:\s+(?:one|choice|option|file))?|(?:option|choice|number|num|#)\s*(\d+)|#(\d+))$",
            c,
            re.I,
        )
        if m_ord:
            ord_word = m_ord.group(1)
            num_str = m_ord.group(2) or m_ord.group(3)
            if ord_word and ord_word.lower() in ORDINAL_MAP:
                idx = ORDINAL_MAP[ord_word.lower()]
                if 0 <= idx < len(self.last_candidates):
                    return self.last_candidates[idx]
            elif num_str:
                idx = int(num_str) - 1
                if 0 <= idx < len(self.last_candidates):
                    return self.last_candidates[idx]

        # 3. Exact candidate filename or stem mention: e.g. "the Readme.md", "LCRO Interview checklist.docx"
        target_name = re.sub(r"^(?:the\s+)", "", c, flags=re.I).strip(" .,?!\"'")
        target_no_ext = re.sub(r"\.(?:pptx?|docx?|xlsx?|pdf|txt|md)$", "", target_name, flags=re.I).strip()
        for cand in self.last_candidates:
            c_name = Path(cand).name.lower()
            c_stem = Path(cand).stem.lower()
            if target_name in (c_name, c_stem) or clean in (c_name, c_stem):
                return cand
            if target_no_ext and target_no_ext == c_stem:
                return cand

        return None

    def resolve_pronoun(self, text: str) -> tuple[str, str] | None:
        """Resolves coreference pronouns ('present it', 'open it', 'read it') against last_opened_file.

        Returns (action_type, file_path) where action_type is 'present' or 'open', or None.
        """
        if self.is_expired() or not self.last_opened_file:
            return None

        if PRESENT_PRONOUNS_RE.match(text):
            return "present", self.last_opened_file

        if OPEN_PRONOUNS_RE.match(text):
            return "open", self.last_opened_file

        return None


# Global context buffers mapped per session
_context_buffers: dict[str, ConversationContext] = {}


def get_context_buffer(session: str = "default") -> ConversationContext:
    """Retrieves or creates the ConversationContext buffer for a session."""
    buf = _context_buffers.get(session)
    if buf is None:
        buf = ConversationContext()
        _context_buffers[session] = buf
    return buf


def reset_context_buffer(session: str = "default") -> None:
    """Clears and resets the context buffer for a session."""
    if session in _context_buffers:
        _context_buffers[session].clear()
