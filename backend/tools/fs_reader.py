"""Find projects on the Desktop and read their handoff file.

Safety model: the language model never supplies a path. Python lists the folders
under one root, matches the spoken name to a real folder, and only ever opens a
file literally named like the handoff filename, after resolving symlinks and
checking the result is still inside the root.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from difflib import SequenceMatcher
import os
from pathlib import Path
import re
import subprocess

SKIP_DIRS = {
    "node_modules", ".git", ".venv", "venv", "env", "__pycache__", "dist", "build", "$recycle.bin", "data",
}
MAX_FILE_BYTES = 1_000_000
MIN_SCORE = 0.75
APPROX_BELOW = 0.9
ALLOWED_DOC_EXTS = {".md", ".txt"}
BLOCKED_DOC_RE = re.compile(
    r"(^\.env|secret|password|passwd|credential|token|apikey|api_key|id_rsa|id_ed25519|\.pem$|\.key$)",
    re.I,
)

STOPWORDS = set(
    """a about am an and are at can catch check checking could current desktop directory do doing
    far file find folder for from go going hand handoff hey how i in is it its latest leave left
    let lets list look looking me my name named now of off on open please progress project projects
    read reading run s show so start status summarize summary tell that the then this to up update
    what whats where which with work working you your""".split()
)

WAKE_PREFIX = re.compile(r"^\s*(?:(?:hey|ok|okay|hi|yo)\s+)?nightmare\b[\s,:;-]*", re.I)


class PathError(Exception):
    """A path was unreadable or outside the allowed root."""


def normalize(text: str) -> str:
    return " ".join(re.sub(r"[^a-z0-9]+", " ", text.lower()).split())


def compact(text: str) -> str:
    return re.sub(r"[^a-z0-9]", "", text.lower())


@dataclass
class Resolution:
    status: str  # found | ambiguous | none | error
    matches: list = field(default_factory=list)  # [(Path, score)], best first
    error: str = ""


def _scan(directory: Path):
    try:
        with os.scandir(directory) as it:
            return sorted(it, key=lambda e: e.name.lower())
    except OSError as exc:
        raise PathError(f"Cannot read {directory}: {exc}") from exc


def list_projects(root: Path) -> list[Path]:
    projects = []
    for entry in _scan(root):
        if entry.name.startswith(".") or entry.name.lower() in SKIP_DIRS:
            continue
        try:
            if entry.is_dir():
                projects.append(Path(entry.path))
        except OSError:
            continue
    return projects


def project_dir_by_name(root: Path, name: str) -> Path | None:
    wanted = compact(name)
    for project in list_projects(root):
        if compact(project.name) == wanted:
            return project
    return None


def _phrases(text: str) -> set[str]:
    stripped = WAKE_PREFIX.sub("", text, count=1)
    words = [w for w in normalize(stripped).split() if w not in STOPWORDS and len(w) >= 2]
    if not words:
        words = [w for w in normalize(text).split() if w not in STOPWORDS and len(w) >= 2]
    phrases = set()
    for i in range(len(words)):
        for n in (1, 2, 3):
            if i + n <= len(words):
                phrases.add("".join(words[i : i + n]))
    return phrases


def _score_one(phrases: set[str], name: str) -> float:
    best = 0.0
    for phrase in phrases:
        if phrase == name:
            return 1.0
        if len(phrase) >= 4 and name.startswith(phrase):
            best = max(best, 0.9)
            continue
        if len(name) >= 4 and abs(len(phrase) - len(name)) <= 3:
            ratio = SequenceMatcher(None, phrase, name).ratio()
            if ratio >= MIN_SCORE:
                best = max(best, min(ratio, 0.89))
    return best


def _score(phrases: set[str], name: str) -> float:
    best = _score_one(phrases, name)
    if name.startswith("project") and len(name) > len("project") + 1:
        best = max(best, _score_one(phrases, name[len("project") :]))
    return best


def resolve_project(text: str, root: Path) -> Resolution:
    """Match free text ("citizen graph progress") to a real folder under root."""
    try:
        projects = list_projects(root)
    except PathError as exc:
        return Resolution("error", error=str(exc))

    phrases = _phrases(text)
    scored = []
    for project in projects:
        name = compact(project.name)
        if len(name) < 2:
            continue
        score = _score(phrases, name)
        if score >= MIN_SCORE:
            scored.append((project, score))

    if not scored:
        return Resolution("none")
    scored.sort(key=lambda m: (-m[1], m[0].name.lower()))
    top = scored[0][1]
    close = [m for m in scored if top - m[1] < 0.05]
    if len(close) > 1:
        return Resolution("ambiguous", close)
    return Resolution("found", [scored[0]])


def find_handoff(project_dir: Path, filename: str = "handoff.md", max_depth: int = 2) -> Path | None:
    """Shallowest file named `filename` (case-insensitive) within max_depth levels."""
    target = filename.lower()
    level = [project_dir]
    for _ in range(max_depth + 1):
        found, next_level = [], []
        for directory in level:
            try:
                entries = _scan(directory)
            except PathError:
                continue
            for entry in entries:
                try:
                    if entry.is_file() and entry.name.lower() == target:
                        found.append(Path(entry.path))
                    elif (
                        entry.is_dir()
                        and not entry.name.startswith(".")
                        and entry.name.lower() not in SKIP_DIRS
                        and not entry.name.lower().endswith(".db")
                    ):
                        next_level.append(Path(entry.path))
                except OSError:
                    continue
        if found:
            return found[0]
        level = next_level
    return None


README_NAMES = ("readme.md", "readme.txt")


def find_readme(project_dir: Path) -> Path | None:
    """The project's own README, at its top level only: one deeper down (frontend/README.md)
    is usually a framework's boilerplate, which would describe the wrong thing."""
    for name in README_NAMES:
        found = find_handoff(project_dir, name, max_depth=0)
        if found is not None:
            return found
    return None


def safe_path(root: Path, path: Path) -> Path:
    """Resolve symlinks and require the result to stay inside root."""
    try:
        resolved = Path(path).resolve()
        resolved.relative_to(Path(root).resolve())
    except (ValueError, OSError) as exc:
        raise PathError(f"{path} is outside the allowed folder") from exc
    return resolved


def _clip(text: str, max_chars: int) -> tuple[str, bool]:
    if len(text) <= max_chars:
        return text, False
    head = int(max_chars * 0.7)
    tail = max_chars - head
    return text[:head] + "\n[... truncated ...]\n" + text[-tail:], True


def read_handoff(path: Path, root: Path, filename: str = "handoff.md", max_chars: int = 12000):
    """Return (text, truncated). Refuses anything that is not the handoff file under root."""
    resolved = safe_path(root, path)
    if resolved.name.lower() != filename.lower():
        raise PathError(f"Refusing to read {resolved.name}: only {filename} is allowed")
    if not resolved.is_file():
        raise PathError(f"{resolved.name} is not a regular file")
    if resolved.stat().st_size > MAX_FILE_BYTES:
        raise PathError(f"{resolved.name} is larger than {MAX_FILE_BYTES} bytes")
    text = resolved.read_bytes().decode("utf-8", errors="replace")
    return _clip(text, max_chars)


DOC_STOPWORDS = STOPWORDS | {
    "content", "contents", "doc", "docs", "document", "documentation", "inside",
    "markdown", "md", "note", "notes", "page", "say", "says", "text", "txt",
    "write", "written",
}
EXPLICIT_DOC_RE = re.compile(r"(?:(?P<subpath>[a-z0-9_.-]+)[/\\])?(?P<fname>[a-z0-9_.-]+\.(?:md|txt))\b", re.I)


def is_safe_doc_name(filename: str) -> bool:
    p = Path(filename)
    if p.suffix.lower() not in ALLOWED_DOC_EXTS:
        return False
    if p.name.lower().endswith(".db") or p.suffix.lower() == ".db":
        return False
    if BLOCKED_DOC_RE.search(p.name):
        return False
    return True


def _iter_safe_docs(project_dir: Path, root: Path, max_depth: int = 3) -> list[Path]:
    docs: list[Path] = []
    level = [project_dir]
    for _ in range(max_depth + 1):
        next_level = []
        for directory in level:
            try:
                entries = _scan(directory)
            except PathError:
                continue
            for entry in entries:
                try:
                    if entry.name.startswith(".") or entry.name.lower().endswith(".db"):
                        continue
                    p = Path(entry.path)
                    if entry.is_file() and is_safe_doc_name(entry.name):
                        try:
                            safe_path(root, p)
                            docs.append(p)
                        except PathError:
                            continue
                    elif entry.is_dir() and entry.name.lower() not in SKIP_DIRS and not entry.name.lower().endswith(".db"):
                        next_level.append(p)
                except OSError:
                    continue
        level = next_level
    return docs


def find_documents(project_dir: Path, text: str, root: Path, max_depth: int = 3) -> list[Path]:
    """Find safe .md/.txt files in project_dir matching the user's spoken/typed query."""
    candidates = _iter_safe_docs(project_dir, root, max_depth=max_depth)
    if not candidates:
        return []

    proj_compact = compact(project_dir.name)
    proj_short = proj_compact[len("project") :] if proj_compact.startswith("project") else proj_compact

    # 1. Check for an explicit filename like `file.md` or `docs/file.md`
    m = EXPLICIT_DOC_RE.search(text)
    if m:
        wanted_name = m.group("fname").lower()
        wanted_stem = compact(Path(wanted_name).stem)
        sub_hint = (m.group("subpath") or "").lower()
        exact = [p for p in candidates if p.name.lower() == wanted_name]
        if not exact:
            exact = [p for p in candidates if compact(p.stem) == wanted_stem]
        if len(exact) > 1 and sub_hint and sub_hint != project_dir.name.lower():
            narrowed = [p for p in exact if sub_hint in [part.lower() for part in p.relative_to(project_dir).parts[:-1]]]
            if narrowed:
                return narrowed
        return exact

    # 2. Match spoken stem words (e.g. "read the architecture file in bims")
    words = [
        w
        for w in normalize(WAKE_PREFIX.sub("", text, count=1)).split()
        if w not in DOC_STOPWORDS and w not in {proj_compact, proj_short} and len(w) >= 2
    ]
    if not words:
        return []
    phrases = set()
    for i in range(len(words)):
        for n in (1, 2, 3):
            if i + n <= len(words):
                phrases.add("".join(words[i : i + n]))

    scored: list[tuple[Path, float]] = []
    for doc in candidates:
        stem = compact(doc.stem)
        if not stem:
            continue
        score = _score_one(phrases, stem)
        if score >= MIN_SCORE:
            scored.append((doc, score))

    if not scored:
        return []
    scored.sort(key=lambda item: (-item[1], len(item[0].relative_to(project_dir).parts), item[0].name.lower()))
    top = scored[0][1]
    close = [doc for doc, s in scored if top - s < 0.05]
    # If same score but one is in a subfolder mentioned in the text (e.g., "docs"), prefer it
    if len(close) > 1:
        norm_words = set(normalize(text).split())
        sub_matches = [
            d for d in close if any(part.lower() in norm_words for part in d.relative_to(project_dir).parts[:-1])
        ]
        if len(sub_matches) == 1:
            return sub_matches
    return close


def read_document(path: Path, root: Path, max_chars: int = 12000) -> tuple[str, bool]:
    """Read an allowlisted .md or .txt document inside root, blocking secrets and symlinks."""
    resolved = safe_path(root, path)
    if not is_safe_doc_name(resolved.name):
        raise PathError(f"Refusing to read {resolved.name}: only safe .md and .txt files are allowed")
    if not resolved.is_file():
        raise PathError(f"{resolved.name} is not a regular file")
    if resolved.stat().st_size > MAX_FILE_BYTES:
        raise PathError(f"{resolved.name} is larger than {MAX_FILE_BYTES} bytes")
    text = resolved.read_bytes().decode("utf-8", errors="replace")
    return _clip(text, max_chars)


NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


def git_info(project_dir: Path) -> dict | None:
    """Fast read-only git branch and dirty-file count for a project folder."""
    if not (project_dir / ".git").exists():
        return None
    try:
        proc = subprocess.run(
            ["git", "status", "--porcelain", "--branch"],
            cwd=str(project_dir),
            capture_output=True,
            stdin=subprocess.DEVNULL,
            timeout=2,
            creationflags=NO_WINDOW,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if proc.returncode != 0:
        return None
    lines = [ln for ln in proc.stdout.decode("utf-8", errors="replace").splitlines() if ln.strip()]
    if not lines:
        return {"branch": "HEAD", "dirty": 0}
    head = lines[0]
    branch = "HEAD"
    if head.startswith("## "):
        raw = head[3:].split("...")[0].strip()
        if raw.startswith("No commits yet on "):
            branch = raw.replace("No commits yet on ", "").strip()
        else:
            branch = raw.split()[0] if raw else "HEAD"
    dirty = sum(1 for ln in lines[1:] if not ln.startswith("##"))
    return {"branch": branch, "dirty": dirty}


def last_commit(project_dir: Path) -> dict | None:
    """Subject and relative date of the latest commit, read-only."""
    if not (project_dir / ".git").exists():
        return None
    try:
        proc = subprocess.run(
            ["git", "log", "-1", "--format=%s%x1f%cr"],
            cwd=str(project_dir),
            capture_output=True,
            stdin=subprocess.DEVNULL,
            timeout=2,
            creationflags=NO_WINDOW,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    out = proc.stdout.decode("utf-8", errors="replace").strip()
    if proc.returncode != 0 or "\x1f" not in out:
        return None
    subject, when = out.split("\x1f", 1)
    return {"subject": subject.strip()[:120], "when": when.strip()}


def project_cards(
    root: Path,
    handoff_filename: str = "handoff.md",
    summary_cache: dict[tuple[str, int], str] | None = None,
) -> list[dict]:
    """Metadata for UI project cards: handoff status, last updated time, cached summary, git status."""
    cards: list[dict] = []
    for proj in list_projects(root):
        handoff = find_handoff(proj, handoff_filename)
        updated_at = None
        cached = None
        try:
            target = handoff if handoff is not None else proj
            st = target.stat()
            updated_at = datetime.fromtimestamp(st.st_mtime).astimezone().isoformat(timespec="minutes")
            if handoff is not None and summary_cache:
                cached = summary_cache.get((str(handoff), st.st_mtime_ns))
        except OSError:
            pass
        cards.append(
            {
                "name": proj.name,
                "has_handoff": handoff is not None,
                "has_readme": find_readme(proj) is not None,
                "updated_at": updated_at,
                "cached_summary": cached,
                "git": git_info(proj),
            }
        )
    return cards
