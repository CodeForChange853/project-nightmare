"""Level 3 Smart File Navigator: plain Python indexing, fuzzy matching, and safe file opening.

Zero LLM is involved. Scans and caches safe files across Desktop, Documents, Downloads,
and safe top-level user directories in Path.home(), strictly skipping hidden directories,
virtualenvs, build dirs, AppData, and secret files (.env, password, credential, pem, key).
"""
from __future__ import annotations

from dataclasses import dataclass
from difflib import SequenceMatcher
import logging
import os
from pathlib import Path
import re
import subprocess
import time
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .audit import Audit

logger = logging.getLogger("nightmare.file_navigator")

SAFE_EXTENSIONS = {".pptx", ".ppt", ".docx", ".doc", ".xlsx", ".pdf", ".txt", ".md"}

FORBIDDEN_DIR_NAMES = {
    ".git", "node_modules", ".venv", "venv", "env", "appdata", "application data",
    "local settings", "cookies", "nethood", "printhood", "recent", "sendto",
    "start menu", "templates", "__pycache__", "dist", "build", "$recycle.bin", "data",
}

BLOCKED_FILE_RE = re.compile(
    r"(^\.env|secret|password|passwd|credential|token|apikey|api_key|id_rsa|id_ed25519|\.pem$|\.key$)",
    re.I,
)

APP_EXT_MAP = {
    "word": {".docx", ".doc"},
    "doc": {".docx", ".doc"},
    "docx": {".docx", ".doc"},
    "powerpoint": {".pptx", ".ppt"},
    "ppt": {".pptx", ".ppt"},
    "pptx": {".pptx", ".ppt"},
    "presentation": {".pptx", ".ppt"},
    "slides": {".pptx", ".ppt"},
    "excel": {".xlsx", ".xls"},
    "spreadsheet": {".xlsx", ".xls"},
    "sheets": {".xlsx", ".xls"},
    "xls": {".xlsx", ".xls"},
    "xlsx": {".xlsx", ".xls"},
    "pdf": {".pdf"},
    "acrobat": {".pdf"},
    "text": {".txt"},
    "txt": {".txt"},
    "notepad": {".txt"},
    "markdown": {".md"},
    "md": {".md"},
}


class SecurityBlockError(Exception):
    """Raised when an action violates file navigation security boundaries."""


@dataclass
class FileMatch:
    path: Path
    filename: str
    ext: str
    score: float
    mtime_ns: int
    matched_tokens: int = 0
    total_query_tokens: int = 0
    exact_match: bool = False


class PendingFileChoices(list):
    """List of candidate file Paths awaiting user disambiguation, with 2-minute expiry TTL."""

    def __init__(self, paths: list[Path] | tuple[Path, ...], ttl_sec: float = 120.0):
        super().__init__(paths)
        self.created_at = time.monotonic()
        self.ttl_sec = ttl_sec
        self.expires_at = self.created_at + ttl_sec

    @property
    def is_expired(self) -> bool:
        return time.monotonic() > self.expires_at


def resolve_file_choice(text: str, choices: list[Path] | PendingFileChoices) -> Path | None:
    """Resolves follow-up turn selection ('the first one', '1', 'the second one', '2', or filename)."""
    if not choices:
        return None
    t = text.strip().lower()
    t = re.sub(r"^\s*(?:(?:hey|ok|hi)\s+)?(?:nightmare[, ]+)?(?:please\s+)?", "", t, flags=re.I).strip(" .,?!")
    t = re.sub(r"^\s*(?:open|select|pick|choose|launch)\s+", "", t, flags=re.I).strip(" .,?!")

    # Ordinals map
    ORDINAL_MAP = {
        "first": 0, "1st": 0, "the first": 0, "the first one": 0, "first one": 0,
        "second": 1, "2nd": 1, "the second": 1, "the second one": 1, "second one": 1,
        "third": 2, "3rd": 2, "the third": 2, "the third one": 2, "third one": 2,
        "fourth": 3, "4th": 3, "the fourth": 3, "the fourth one": 3, "fourth one": 3,
        "fifth": 4, "5th": 4, "the fifth": 4, "the fifth one": 4, "fifth one": 4,
    }
    if t in ORDINAL_MAP:
        idx = ORDINAL_MAP[t]
        if idx < len(choices):
            return choices[idx]

    m_ord = re.search(r"\b(first|1st|second|2nd|third|3rd|fourth|4th|fifth|5th)\s*(?:one|choice|option|file)?\b", t)
    if m_ord:
        raw_ord = m_ord.group(1).lower()
        idx_map = {
            "first": 0, "1st": 0,
            "second": 1, "2nd": 1,
            "third": 2, "3rd": 2,
            "fourth": 3, "4th": 3,
            "fifth": 4, "5th": 4,
        }
        if raw_ord in idx_map:
            idx = idx_map[raw_ord]
            if idx < len(choices):
                return choices[idx]

    # Explicit numbers: "1", "2", "number 1", "choice 1", "option 2", "#1", "num 1", "one", "two"
    NUMBER_MAP = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5}
    m_num = re.search(r"\b(?:number|num|no|choice|option|#)?\s*(\d{1,2})\b", t)
    if m_num:
        try:
            num = int(m_num.group(1))
            if 1 <= num <= len(choices):
                return choices[num - 1]
        except ValueError:
            pass

    for word, num in NUMBER_MAP.items():
        if re.search(rf"\b(?:number|choice|option)?\s*{word}\s*(?:one|file)?\b", t):
            if 1 <= num <= len(choices):
                return choices[num - 1]

    # Direct filename or stem match
    clean_target = t.strip(" .,?!\"'")
    for path in choices:
        fname = path.name.lower()
        fstem = path.stem.lower()
        if clean_target in (fname, fstem):
            return path
        target_no_ext = re.sub(r"\.(?:pptx?|docx?|xlsx?|pdf|txt|md)$", "", clean_target, flags=re.I).strip()
        if target_no_ext and target_no_ext == fstem:
            return path
        if fname in clean_target or fstem in clean_target:
            return path

    return None


def get_allowed_roots(base_home: Path | None = None) -> list[Path]:
    """Returns safe user directories allowed for file indexing and opening."""
    if base_home is None:
        base_home = Path.home()

    roots: list[Path] = []
    # Primary user directories
    for name in ("Desktop", "Documents", "Downloads"):
        p = base_home / name
        if p.is_dir():
            roots.append(p)

    # Safe top-level non-system directories in user home
    try:
        for entry in os.scandir(base_home):
            if entry.name.startswith("."):
                continue
            if entry.name.lower() in FORBIDDEN_DIR_NAMES:
                continue
            try:
                if entry.is_dir() and not entry.is_symlink():
                    d = Path(entry.path)
                    if d not in roots:
                        roots.append(d)
            except OSError:
                continue
    except OSError:
        pass

    return roots


def scan_safe_files(roots: list[Path]) -> list[tuple[str, str, str, str, int]]:
    """Recursively walks allowed roots and gathers safe file records."""
    records: list[tuple[str, str, str, str, int]] = []
    seen_paths: set[str] = set()

    for root in roots:
        if not root.is_dir():
            continue
        for dirpath, dirnames, filenames in os.walk(root, topdown=True, followlinks=False):
            # In-place filtering of subdirectories
            dirnames[:] = [
                d for d in dirnames
                if not d.startswith(".")
                and d.lower() not in FORBIDDEN_DIR_NAMES
                and not d.lower().endswith(".db")
            ]

            for fname in filenames:
                if fname.startswith(".") or fname.startswith("~$") or fname.lower().endswith(".db") or BLOCKED_FILE_RE.search(fname):
                    continue
                ext = Path(fname).suffix.lower()
                if ext not in SAFE_EXTENSIONS:
                    continue

                full_p = os.path.join(dirpath, fname)
                if full_p in seen_paths:
                    continue
                seen_paths.add(full_p)

                try:
                    mtime_ns = os.stat(full_p).st_mtime_ns
                except OSError:
                    continue

                stem_lower = Path(fname).stem.lower()
                records.append((fname, stem_lower, ext, full_p, mtime_ns))

    return records


def index_files(roots: list[Path] | None = None, audit: Audit | None = None) -> int:
    """Scans allowed roots and stores file metadata in SQLite audit indexed_files table."""
    if audit is None:
        return 0
    if roots is None:
        roots = get_allowed_roots()

    records = scan_safe_files(roots)
    audit.upsert_indexed_files(records)
    valid_paths = {r[3] for r in records}
    audit.prune_indexed_files(valid_paths)
    return len(records)


def _char_trigrams(s: str) -> set[str]:
    """Extracts character 3-grams for trigram similarity matching."""
    clean = re.sub(r"[^a-z0-9]", "", s.lower())
    if len(clean) < 3:
        return {clean} if clean else set()
    return {clean[i:i+3] for i in range(len(clean) - 2)}


def _trigram_similarity(s1: str, s2: str) -> float:
    """Computes character trigram similarity coefficient (Dice coefficient)."""
    t1 = _char_trigrams(s1)
    t2 = _char_trigrams(s2)
    if not t1 or not t2:
        return 0.0
    inter = len(t1 & t2)
    return 2.0 * inter / (len(t1) + len(t2))


def _normalize_phonetic_stt(text: str) -> str:
    """Normalizes common Web Speech transcriptions to canonical spelling."""
    s = text.lower()
    s = re.sub(r"\bl\s+filibuster\s+esmo\b", "el filibusterismo", s)
    s = re.sub(r"\bfilibuster\s+esmo\b", "filibusterismo", s)
    s = re.sub(r"\belfilibusterismo\b", "el filibusterismo", s)
    return s


def parse_file_query(query: str) -> tuple[str, set[str]]:
    """Extracts target search keywords and extension filter hints from spoken user input."""
    q = query.lower()
    inferred_exts: set[str] = set()

    # Detect app / format mentions
    for keyword, exts in APP_EXT_MAP.items():
        if re.search(rf"\b{re.escape(keyword)}\b", q):
            inferred_exts.update(exts)

    # Phonetic STT normalization
    clean = _normalize_phonetic_stt(query)
    # Strip parenthesized app hints, e.g. "LCRO Interview checklist.docx (word)"
    clean = re.sub(r"\s*\(\s*(?:word|powerpoint|excel|notepad|sheets|slides|acrobat|wordpad|doc|docx|ppt|pptx|xls|xlsx|pdf)\s*\)\s*$", "", clean, flags=re.I)
    clean = re.sub(r"^\s*(?:(?:hey|ok|hi)\s+)?(?:nightmare[, ]+)?(?:please\s+)?", "", clean, flags=re.I)
    clean = re.sub(r"^\s*(?:i\s+said|said)\s+", "", clean, flags=re.I)
    clean = re.sub(r"^\s*(?:comments?\s+(?:and\s+)?|so\s+|well\s+|can\s+you\s+|could\s+you\s+)", "", clean, flags=re.I)
    clean = re.sub(r"^\s*(?:list\s+(?:all\s+)?(?:the\s+)?|do\s+i\s+have\s+any\s+|what\s+about\s+(?:the\s+)?)(?:files?|documents?|docs?)(?:\s+related\s+to|\s+about)?\s*", "", clean, flags=re.I)
    clean = re.sub(r"^\s*(?:find|search\s+for|look\s+up|locate)\s+(?:the\s+|a\s+|an\s+)?(?:file|document|presentation|spreadsheet|docs?|doc)?(?:\s+related\s+to|\s+about)?\s*", "", clean, flags=re.I)
    clean = re.sub(r"^\s*(?:open\s*file|open|launch)\s+(?:the\s+|a\s+|an\s+)?(?:file|document|docs?|doc)?(?:\s+related\s+to|\s+about)?\s*", "", clean, flags=re.I)
    clean = re.sub(r"^\s*(?:create\s+(?:a\s+|an\s+)?)(?P<cr_file>.+?)\s+(?:in|on|with|using)\s+(?:word|powerpoint|excel)\s*$", r"\g<cr_file>", clean, flags=re.I)
    clean = re.sub(r"\s*(?:\b(?:and|then)\s+)?(?:open\s*file|open|launch)\s+(?:it\s+)?(?:(?:in|on|with|using)\s+[a-z\s]+)?\s*$", "", clean, flags=re.I)
    clean = re.sub(r"\s*(?:\b(?:in|on|using|with)\s+)?(?:word|powerpoint|excel|notepad|sheets|slides|acrobat|wordpad|doc|docx|ppt|pptx|xls|xlsx|pdf)\s*$", "", clean, flags=re.I)
    clean = re.sub(r"\s+\b(?:and|then|or|also)\s*$", "", clean, flags=re.I)
    clean = re.sub(r"\b(?:docs?|files?|documents?)\b\s*$", "", clean, flags=re.I)
    clean = " ".join(clean.split()).strip(" .,?!")

    if not clean:
        tokens = [w for w in re.split(r"[^a-zA-Z0-9]+", query) if w.lower() not in {"find", "file", "open", "it", "in", "on", "with", "or", "and", "the", "related", "to", "docs", "doc", "document"}]
        clean = " ".join(tokens)

    return clean, inferred_exts



def _token_match(q_tok: str, stem_tok: str) -> bool:
    if q_tok == stem_tok:
        return True
    if len(q_tok) >= 3 and len(stem_tok) >= 3:
        if q_tok in stem_tok or stem_tok in q_tok:
            return True
        if SequenceMatcher(None, q_tok, stem_tok).ratio() >= 0.8:
            return True
    return False


# Track when index was last refreshed
_last_index_time: float = 0.0


def find_files(
    query: str,
    ext_filter: str | list[str] | set[str] | None = None,
    audit: Audit | None = None,
    db_path: Path | None = None,
    allowed_roots: list[Path] | None = None,
    limit: int | None = None,
) -> list[FileMatch]:
    """Finds matching indexed files using deterministic token + fuzzy score matching."""
    global _last_index_time
    clean_q, query_exts = parse_file_query(query)

    effective_exts: set[str] = set()
    if ext_filter:
        if isinstance(ext_filter, str):
            low = ext_filter.lower()
            if low in APP_EXT_MAP:
                effective_exts.update(APP_EXT_MAP[low])
            else:
                effective_exts.add(low if low.startswith(".") else f".{low}")
        else:
            for item in ext_filter:
                low = item.lower()
                if low in APP_EXT_MAP:
                    effective_exts.update(APP_EXT_MAP[low])
                else:
                    effective_exts.add(low if low.startswith(".") else f".{low}")
    elif query_exts:
        effective_exts.update(query_exts)

    if audit is None and db_path is not None:
        from .audit import Audit
        audit = Audit(db_path)

    if audit is None:
        return []

    indexed = audit.get_indexed_files(effective_exts if effective_exts else None)
    now = time.monotonic()
    if (not indexed or (now - _last_index_time > 180)) and allowed_roots is not None:
        index_files(roots=allowed_roots, audit=audit)
        _last_index_time = now
        indexed = audit.get_indexed_files(effective_exts if effective_exts else None)

    clean_q_lower = clean_q.lower()
    clean_stem_lower = re.sub(r"\.(?:pptx?|docx?|xlsx?|pdf|txt|md)$", "", clean_q_lower, flags=re.I).strip()
    q_tokens = [w for w in re.split(r"[^a-z0-9]+", clean_stem_lower) if len(w) >= 2]
    total_q_tokens = len(q_tokens)

    def _score_items(items):
        res: list[FileMatch] = []
        for item in items:
            stem = item["stem_lower"]
            filename = item["filename"]
            ext = item["ext"]
            score = 0.0
            exact_match = False
            matched_tokens = 0

            # Exact match check against filename or stem
            if (
                clean_q_lower == filename.lower()
                or clean_q_lower == stem
                or clean_stem_lower == stem
                or re.sub(r"[^a-z0-9]", "", clean_q_lower) == re.sub(r"[^a-z0-9]", "", filename.lower())
                or re.sub(r"[^a-z0-9]", "", clean_stem_lower) == re.sub(r"[^a-z0-9]", "", stem)
            ):
                score = 1.0
                exact_match = True
                matched_tokens = total_q_tokens
            else:
                stem_tokens = [w for w in re.split(r"[^a-z0-9]+", stem) if len(w) >= 2]
                matched_count = sum(1 for q_tok in q_tokens if any(_token_match(q_tok, s_tok) for s_tok in stem_tokens))
                matched_tokens = matched_count

                tri_sim = _trigram_similarity(clean_stem_lower, stem)
                diff_sim = SequenceMatcher(
                    None,
                    re.sub(r"[^a-z0-9]", "", clean_stem_lower),
                    re.sub(r"[^a-z0-9]", "", stem),
                ).ratio()

                if total_q_tokens > 1:
                    ratio = matched_count / total_q_tokens
                    coverage = total_q_tokens / max(len(stem_tokens), total_q_tokens)
                    if ratio == 1.0:
                        score = 0.85 + (coverage * 0.10) + (tri_sim * 0.05)
                    elif ratio >= 0.5:
                        score = 0.45 + (ratio * 0.20) + (max(tri_sim, diff_sim) * 0.25) + (coverage * 0.10)
                    elif any(tok in stem for tok in q_tokens):
                        score = 0.35 + (max(tri_sim, diff_sim) * 0.30)
                    else:
                        score = max(tri_sim, diff_sim) * 0.85
                elif total_q_tokens == 1:
                    if matched_count == 1:
                        coverage = 1.0 / max(len(stem_tokens), 1)
                        score = 0.75 + (coverage * 0.15) + (tri_sim * 0.10)
                    elif any(tok in stem for tok in q_tokens):
                        score = 0.60 + (max(tri_sim, diff_sim) * 0.20)
                    else:
                        score = max(tri_sim, diff_sim) * 0.85
                else:
                    score = max(tri_sim, diff_sim) * 0.85

                if max(tri_sim, diff_sim) >= 0.70 and score < 0.80:
                    score = max(score, max(tri_sim, diff_sim) * 0.90)

            if score >= 0.5:
                res.append(
                    FileMatch(
                        path=Path(item["full_path"]),
                        filename=filename,
                        ext=ext,
                        score=round(score, 3),
                        mtime_ns=item["mtime_ns"],
                        matched_tokens=matched_tokens,
                        total_query_tokens=total_q_tokens,
                        exact_match=exact_match,
                    )
                )
        res.sort(
            key=lambda m: (m.exact_match, m.score, m.matched_tokens, m.mtime_ns),
            reverse=True,
        )
        return res

    matches = _score_items(indexed)

    # Dynamic rescan fallback: if query didn't find all tokens and allowed_roots provided, refresh once
    if (not matches or (matches and matches[0].matched_tokens < total_q_tokens)) and allowed_roots is not None:
        now_call = time.monotonic()
        if now_call - _last_index_time > 10:
            index_files(roots=allowed_roots, audit=audit)
            _last_index_time = now_call
            refreshed = audit.get_indexed_files(effective_exts if effective_exts else None)
            matches = _score_items(refreshed)

    return matches[:limit] if limit is not None else matches


def safe_open_file(
    file_path: Path | str,
    allowed_roots: list[Path] | None = None,
    app_binary: str | None = None,
) -> tuple[bool, str]:
    """Opens a file after verifying existence and path traversal boundaries."""
    if allowed_roots is None:
        allowed_roots = get_allowed_roots()

    p = Path(file_path).resolve()

    # Path traversal validation: resolved path must reside strictly within an allowed root
    allowed_resolved = [r.resolve() for r in allowed_roots if r.exists()]
    is_safe = any(ar == p or ar in p.parents for ar in allowed_resolved)
    if not is_safe:
        raise SecurityBlockError(f"Security block: '{p}' is outside allowed directories.")

    # Sensitive / secret file validation
    if BLOCKED_FILE_RE.search(p.name):
        raise SecurityBlockError(f"Security block: access to sensitive file '{p.name}' is forbidden.")

    if not p.exists() or not p.is_file():
        return False, f"File not found: {p.name}"

    try:
        if app_binary:
            subprocess.Popen([app_binary, str(p)], shell=False)
        else:
            if os.name == "nt" and hasattr(os, "startfile"):
                os.startfile(str(p))
            else:
                subprocess.Popen(["start", str(p)], shell=False)
        return True, f"Opened {p.name}."
    except Exception as exc:
        return False, f"Failed to open {p.name}: {exc}"
