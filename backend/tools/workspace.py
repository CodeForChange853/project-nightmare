"""Workspace awareness: read-only project scans and dev-task detection. Plain code, never the model.

Everything here only *reads* (git status/log/grep, package.json, pyproject.toml). Nothing is run
from this module; detected dev tasks become ActionPlans that always wait for a click.
"""
from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import re
import shutil
import subprocess
import time

NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)
TODO_RE = r"\b(TODO|FIXME)\b"


def _git(project: Path, args: list[str], timeout: int = 5) -> str | None:
    if not (project / ".git").exists() or shutil.which("git") is None:
        return None
    try:
        proc = subprocess.run(
            ["git", *args], cwd=str(project), capture_output=True, stdin=subprocess.DEVNULL,
            timeout=timeout, creationflags=NO_WINDOW,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if proc.returncode not in (0, 1):  # `git grep` exits 1 when nothing matches
        return None
    return proc.stdout.decode("utf-8", errors="replace")


def scan_project(project: Path, handoff: Path | None) -> dict:
    """One project's state: branch, dirty files, ahead/behind, last commit, handoff mtime, TODO count."""
    name = project.name or project.resolve().name
    snap = {
        "project": name, "git": False, "branch": "", "dirty": 0, "ahead": 0, "behind": 0,
        "commit_ts": 0, "commit_subject": "", "handoff_mtime": 0, "todos": 0,
    }
    if handoff is not None:
        try:
            snap["handoff_mtime"] = int(handoff.stat().st_mtime)
        except OSError:
            pass
    status = _git(project, ["status", "--porcelain", "--branch"])
    if status is None:
        return snap
    snap["git"] = True
    lines = [ln for ln in status.splitlines() if ln.strip()]
    if lines and lines[0].startswith("## "):
        head = lines[0][3:]
        branch = head.split("...")[0].strip()
        snap["branch"] = branch.replace("No commits yet on ", "").split()[0] if branch else "HEAD"
        m_ahead, m_behind = re.search(r"ahead (\d+)", head), re.search(r"behind (\d+)", head)
        snap["ahead"] = int(m_ahead.group(1)) if m_ahead else 0
        snap["behind"] = int(m_behind.group(1)) if m_behind else 0
        lines = lines[1:]
    snap["dirty"] = len(lines)
    log = _git(project, ["log", "-1", "--format=%ct%x1f%s"])
    if log and "\x1f" in log:
        ts, subject = log.strip().split("\x1f", 1)
        snap["commit_ts"] = int(ts) if ts.isdigit() else 0
        snap["commit_subject"] = subject.strip()[:120]
    grep = _git(project, ["grep", "-I", "-c", "-E", TODO_RE], timeout=8)  # tracked files only
    if grep:
        snap["todos"] = sum(int(ln.rsplit(":", 1)[1]) for ln in grep.splitlines() if ":" in ln and ln.rsplit(":", 1)[1].isdigit())
    return snap


def commits_since(project: Path, since_epoch: int, limit: int = 3) -> tuple[int, list[str]]:
    """(count, newest subjects) of commits made after `since_epoch`."""
    out = _git(project, ["log", f"--since={int(since_epoch)}", "--format=%s"])
    if not out:
        return 0, []
    subjects = [ln.strip()[:100] for ln in out.splitlines() if ln.strip()]
    return len(subjects), subjects[:limit]


def priority(snap: dict, dirty_days: float, now: float | None = None) -> tuple[float, list[str]]:
    """Score for "what should I work on", with the reasons behind it."""
    now = now or time.time()
    score, why = 0.0, []
    if snap["dirty"]:
        score += min(snap["dirty"], 20)
        span = f" for {dirty_days:.0f} day{'s' if round(dirty_days) != 1 else ''}" if dirty_days >= 1 else ""
        why.append(f"{snap['dirty']} uncommitted file{'' if snap['dirty'] == 1 else 's'}{span}")
        score += min(dirty_days, 14) * 2
    if snap["ahead"]:
        score += 2
        why.append(f"{snap['ahead']} commit{'' if snap['ahead'] == 1 else 's'} not pushed")
    if snap["commit_ts"]:
        idle = (now - snap["commit_ts"]) / 86400
        if idle >= 3:
            score += min(idle, 30) * 0.5
            why.append(f"last commit {idle:.0f} days ago")
    if snap["todos"]:
        score += min(snap["todos"], 15) * 0.2
        why.append(f"{snap['todos']} TODO/FIXME")
    if snap["handoff_mtime"] and snap["commit_ts"] and snap["handoff_mtime"] > snap["commit_ts"] + 3600:
        score += 3
        why.append("handoff updated since the last commit")
    return score, why


# ---- dev tasks found in a project (always confirmed with a click) -----------------------------

JS_SCRIPTS = {  # kind -> package.json script names to look for, in order
    "test": ("test",), "build": ("build",), "dev": ("dev", "start", "serve"),
    "lint": ("lint",), "preview": ("preview",), "typecheck": ("typecheck", "type-check", "tsc"),
}
LONG_RUNNING = {"dev", "preview"}  # servers: launched detached, not waited for
TIMEOUTS = {"test": 300, "build": 300, "lint": 120, "typecheck": 180}
SCRIPT_NAME_RE = re.compile(r"^[a-z][a-z0-9:_-]{0,30}$")


@dataclass
class DevTask:
    kind: str  # test | build | dev | lint | preview | typecheck | pytest
    label: str
    argv: list
    wait: bool
    timeout: int
    detail: str = ""  # what the script actually runs, shown on the confirmation
    cwd: Path | None = None


def _package_manager(project: Path) -> list[str]:
    if (project / "pnpm-lock.yaml").exists() and shutil.which("pnpm"):
        return ["pnpm", "run"]
    if (project / "yarn.lock").exists() and shutil.which("yarn"):
        return ["yarn", "run"]
    return ["npm", "run"]


def _has_pytest(project: Path) -> bool:
    if (project / "pytest.ini").exists() or (project / "conftest.py").exists():
        return True
    for name in ("pyproject.toml", "setup.cfg", "tox.ini"):
        f = project / name
        try:
            if f.is_file() and ("pytest" in f.read_text(encoding="utf-8", errors="ignore")):
                return True
        except OSError:
            pass
    tests = project / "tests"
    try:
        return tests.is_dir() and any(tests.glob("test_*.py"))
    except OSError:
        return False


def _project_python(project: Path) -> str:
    for rel in (".venv/Scripts/python.exe", ".venv/bin/python", "venv/Scripts/python.exe"):
        if (project / rel).is_file():
            return str(project / rel)
    return "python"


def detect_dev_tasks(project: Path) -> list[DevTask]:
    """Routine tasks from package.json scripts and pytest.

    Checks the root project as well as common subfolders (frontend, backend, client, web).
    """
    tasks: list[DevTask] = []
    dirs_to_check = [project]
    for sub_name in ("frontend", "client", "web", "backend", "server", "api"):
        sub = project / sub_name
        if sub.is_dir():
            dirs_to_check.append(sub)

    seen_keys: set[tuple[str, str]] = set()

    for d in dirs_to_check:
        pkg = d / "package.json"
        scripts: dict = {}
        try:
            if pkg.is_file() and pkg.stat().st_size < 500_000:
                data = json.loads(pkg.read_text(encoding="utf-8", errors="replace"))
                scripts = data.get("scripts") if isinstance(data.get("scripts"), dict) else {}
        except (OSError, ValueError):
            scripts = {}

        runner = _package_manager(d)
        loc_suffix = f" in {d.name}" if d != project else ""
        for kind, names in JS_SCRIPTS.items():
            for name in names:
                body = scripts.get(name)
                if isinstance(body, str) and SCRIPT_NAME_RE.match(name):
                    key = (kind, d.name if d != project else "")
                    if key not in seen_keys:
                        seen_keys.add(key)
                        tasks.append(DevTask(
                            kind=kind,
                            label=f"{kind} ({' '.join(runner)} {name}{loc_suffix})",
                            argv=[*runner, name],
                            wait=kind not in LONG_RUNNING,
                            timeout=TIMEOUTS.get(kind, 60),
                            detail=body.strip()[:100],
                            cwd=d,
                        ))
                    break

        if _has_pytest(d):
            key = ("pytest", d.name if d != project else "")
            if key not in seen_keys:
                seen_keys.add(key)
                py = _project_python(d) if (d / ".venv").exists() else _project_python(project)
                tasks.append(DevTask(
                    kind="pytest",
                    label=f"tests (pytest{loc_suffix})",
                    argv=[py, "-m", "pytest", "-q"],
                    wait=True,
                    timeout=TIMEOUTS["test"],
                    detail=f"{Path(py).name} -m pytest -q",
                    cwd=d,
                ))

    return tasks


def pick_dev_task(tasks: list[DevTask], kind: str) -> tuple[DevTask | None, str]:
    """Choose the task for a spoken kind. Returns (task, "") or (None, reason to tell the user)."""
    if kind == "test":
        options = [t for t in tasks if t.kind in {"test", "pytest"}]
        if len(options) > 1:
            return None, "has both npm test and pytest. Say which: run npm tests, or run pytest."
    elif kind in {"npmtest", "npm_test", "npm-test"}:
        options = [t for t in tasks if t.kind == "test"]
    else:
        options = [t for t in tasks if t.kind == kind]
    if not options:
        return None, ""
    return options[0], ""


# ---- workspace-wide scans and briefings (plain Python, no LLM) -------------------------------

def scan_all_projects(desktop_root: Path, handoff_filename: str = "handoff.md") -> list[dict]:
    """Scans all projects on Desktop. Fast, plain code, returns list of project snapshots."""
    from .fs_reader import find_handoff, list_projects
    projects = list_projects(desktop_root)
    snaps = []
    for p in projects:
        handoff = find_handoff(p, handoff_filename)
        snaps.append(scan_project(p, handoff))
    return snaps


def workspace_briefing_from_snaps(snaps: list[dict]) -> str:
    """Concise spoken briefing summarizing health across all projects."""
    if not snaps:
        return "No projects found on your Desktop."

    total = len(snaps)
    git_repos = [s for s in snaps if s["git"]]
    dirty_snaps = [s for s in git_repos if s["dirty"] > 0]
    total_dirty = sum(s["dirty"] for s in dirty_snaps)
    ahead_snaps = [s for s in git_repos if s["ahead"] > 0]
    total_todos = sum(s["todos"] for s in snaps)

    parts = [f"You have {total} project{'s' if total != 1 else ''} on your Desktop, {len(git_repos)} with git."]

    if dirty_snaps:
        breakdown = ", ".join(f"{s['project']} has {s['dirty']}" for s in dirty_snaps[:3])
        if len(dirty_snaps) > 3:
            breakdown += f", plus {len(dirty_snaps) - 3} more"
        parts.append(f"{total_dirty} uncommitted file{'s' if total_dirty != 1 else ''} across {len(dirty_snaps)} project{'s' if len(dirty_snaps) != 1 else ''} ({breakdown}).")
    else:
        parts.append("All git repositories are clean.")

    if ahead_snaps:
        ahead_desc = ", ".join(f"{s['project']} has {s['ahead']}" for s in ahead_snaps[:2])
        parts.append(f"Unpushed commits: {ahead_desc}.")

    if total_todos:
        parts.append(f"Found {total_todos} TODO or FIXME comment{'s' if total_todos != 1 else ''} across tracked files.")

    return " ".join(parts)


def workspace_changes(desktop_root: Path, handoff_filename: str = "handoff.md", since_epoch: int | None = None) -> str:
    """Summarizes commits and handoff updates across projects in the given timeframe."""
    from .fs_reader import find_handoff, list_projects
    since_epoch = int(since_epoch if since_epoch is not None else (time.time() - 86400))
    projects = list_projects(desktop_root)
    commit_parts = []
    handoff_parts = []

    for p in projects:
        count, subjects = commits_since(p, since_epoch, limit=2)
        if count:
            sample = f" (including: {subjects[0]})" if subjects else ""
            commit_parts.append(f"{p.name} has {count} new commit{'s' if count != 1 else ''}{sample}")

        handoff = find_handoff(p, handoff_filename)
        if handoff:
            try:
                mtime = int(handoff.stat().st_mtime)
                if mtime >= since_epoch:
                    handoff_parts.append(p.name)
            except OSError:
                pass

    if not commit_parts and not handoff_parts:
        return "No commits or handoff changes since yesterday across your projects."

    sentences = []
    if commit_parts:
        sentences.append("Since yesterday: " + "; ".join(commit_parts) + ".")
    if handoff_parts:
        sentences.append("Handoffs updated: " + ", ".join(handoff_parts) + ".")
    return " ".join(sentences)


def work_priorities(desktop_root: Path, dirty_days_map: dict[str, float] | None = None, handoff_filename: str = "handoff.md") -> str:
    """Determines top projects needing developer attention based on deterministic scoring."""
    snaps = scan_all_projects(desktop_root, handoff_filename)
    if not snaps:
        return "No projects found on your Desktop."

    dirty_days_map = dirty_days_map or {}
    scored = []
    for s in snaps:
        dirty_days = dirty_days_map.get(s["project"], 0.0)
        score, why = priority(s, dirty_days)
        scored.append((score, s, why))

    scored.sort(key=lambda item: item[0], reverse=True)
    active = [item for item in scored if item[0] > 0]
    if not active:
        return "All your projects look clean and up to date."

    top_score, top_snap, top_why = active[0]
    top_why_str = ", ".join(top_why)
    reply = f"I recommend working on {top_snap['project']}: {top_why_str}."

    if len(active) > 1:
        _, next_snap, next_why = active[1]
        next_why_str = ", ".join(next_why)
        reply += f" Next is {next_snap['project']}: {next_why_str}."

    return reply


# ---- GitHub Repository Checks (Phase 8B - Level 3+) -------------------------------------------

def check_repo_remote(project: Path, timeout: int = 8) -> dict:
    """Checks remote updates: fetch dry-run and ahead/behind counts."""
    res = {"ahead": 0, "behind": 0, "has_remote": False, "fetch_output": ""}
    if not (project / ".git").exists() or shutil.which("git") is None:
        return res

    try:
        proc_rem = subprocess.run(
            ["git", "remote"], cwd=str(project), capture_output=True,
            stdin=subprocess.DEVNULL, timeout=timeout, shell=False, creationflags=NO_WINDOW,
        )
        remotes = [r.strip() for r in proc_rem.stdout.decode("utf-8", errors="replace").splitlines() if r.strip()]
        if not remotes:
            return res
        res["has_remote"] = True
    except (OSError, subprocess.SubprocessError):
        return res

    try:
        proc_fetch = subprocess.run(
            ["git", "fetch", "--dry-run"], cwd=str(project), capture_output=True,
            stdin=subprocess.DEVNULL, timeout=timeout, shell=False, creationflags=NO_WINDOW,
        )
        fetch_out = (proc_fetch.stdout + proc_fetch.stderr).decode("utf-8", errors="replace").strip()
        res["fetch_output"] = fetch_out
    except (OSError, subprocess.SubprocessError):
        pass

    try:
        proc_count = subprocess.run(
            ["git", "rev-list", "--left-right", "--count", "HEAD...@{u}"],
            cwd=str(project), capture_output=True, stdin=subprocess.DEVNULL,
            timeout=timeout, shell=False, creationflags=NO_WINDOW,
        )
        if proc_count.returncode == 0:
            parts = proc_count.stdout.decode("utf-8", errors="replace").strip().split()
            if len(parts) >= 2 and parts[0].isdigit() and parts[1].isdigit():
                res["ahead"] = int(parts[0])
                res["behind"] = int(parts[1])
    except (OSError, subprocess.SubprocessError):
        pass

    return res


def check_repo_pull_requests(project: Path, timeout: int = 8) -> list[dict]:
    """Queries open pull requests via gh CLI with graceful fallback if offline/unauthenticated."""
    if shutil.which("gh") is None:
        return []
    try:
        proc = subprocess.run(
            ["gh", "pr", "list", "--json", "number,title,author,state"],
            cwd=str(project), capture_output=True, stdin=subprocess.DEVNULL,
            timeout=timeout, shell=False, creationflags=NO_WINDOW,
        )
        if proc.returncode != 0:
            return []
        data = json.loads(proc.stdout.decode("utf-8", errors="replace"))
        if isinstance(data, list):
            prs = []
            for item in data:
                if isinstance(item, dict):
                    author = item.get("author")
                    author_login = author.get("login") if isinstance(author, dict) else str(author or "")
                    prs.append({
                        "number": item.get("number"),
                        "title": item.get("title", ""),
                        "author": author_login,
                        "state": item.get("state", "OPEN"),
                    })
            return prs
    except (OSError, subprocess.SubprocessError, ValueError):
        pass
    return []


def check_repo_conflicts(project: Path, timeout: int = 8) -> list[str]:
    """Detects unmerged conflict paths in git status or potential merge conflicts with origin/main."""
    conflicts: list[str] = []
    if not (project / ".git").exists() or shutil.which("git") is None:
        return conflicts

    # 1. Unmerged paths in working tree
    try:
        proc_st = subprocess.run(
            ["git", "status", "--porcelain"], cwd=str(project), capture_output=True,
            stdin=subprocess.DEVNULL, timeout=timeout, shell=False, creationflags=NO_WINDOW,
        )
        if proc_st.returncode == 0:
            for line in proc_st.stdout.decode("utf-8", errors="replace").splitlines():
                if len(line) >= 3:
                    code = line[:2]
                    if code in {"UU", "AA", "UD", "DU", "DD", "AU", "UA"}:
                        conflicts.append(line[3:].strip())
    except (OSError, subprocess.SubprocessError):
        pass

    # 2. Potential conflict check against origin/main if available
    if not conflicts:
        try:
            proc_rev = subprocess.run(
                ["git", "rev-parse", "--verify", "origin/main"], cwd=str(project),
                capture_output=True, stdin=subprocess.DEVNULL, timeout=timeout,
                shell=False, creationflags=NO_WINDOW,
            )
            if proc_rev.returncode == 0:
                proc_base = subprocess.run(
                    ["git", "merge-base", "HEAD", "origin/main"], cwd=str(project),
                    capture_output=True, stdin=subprocess.DEVNULL, timeout=timeout,
                    shell=False, creationflags=NO_WINDOW,
                )
                base = proc_base.stdout.decode("utf-8", errors="replace").strip()
                if base:
                    proc_mt = subprocess.run(
                        ["git", "merge-tree", base, "HEAD", "origin/main"], cwd=str(project),
                        capture_output=True, stdin=subprocess.DEVNULL, timeout=timeout,
                        shell=False, creationflags=NO_WINDOW,
                    )
                    out = proc_mt.stdout.decode("utf-8", errors="replace")
                    for ln in out.splitlines():
                        if "CONFLICT" in ln or "+<<<<<<<" in ln:
                            conflicts.append("origin/main merge conflict")
                            break
        except (OSError, subprocess.SubprocessError):
            pass

    return conflicts


def check_github_repos(desktop_root: Path) -> list[dict]:
    """Runs GitHub status, remote, PR, and conflict checks across tracked Desktop repos."""
    from .fs_reader import list_projects
    projects = list_projects(desktop_root)
    results = []
    for p in projects:
        if not (p / ".git").exists():
            continue
        results.append({
            "project": p.name,
            "path": p,
            "remote": check_repo_remote(p),
            "pull_requests": check_repo_pull_requests(p),
            "conflicts": check_repo_conflicts(p),
        })
    return results


def github_workspace_summary(desktop_root: Path) -> str:
    """Concise spoken briefing of remote updates, open PRs, and merge conflicts across repos."""
    repos = check_github_repos(desktop_root)
    if not repos:
        return "No git repositories found on your Desktop."

    repo_summaries: list[str] = []
    total_prs = 0
    total_conflicts = 0

    for r in repos:
        p_name = r["project"]
        parts = []
        rem = r["remote"]
        if rem.get("behind", 0) > 0:
            parts.append(f"{rem['behind']} incoming commit{'s' if rem['behind'] != 1 else ''}")
        if rem.get("ahead", 0) > 0:
            parts.append(f"{rem['ahead']} unpushed commit{'s' if rem['ahead'] != 1 else ''}")
        prs = r["pull_requests"]
        total_prs += len(prs)
        if prs:
            pr_desc = ", ".join(f"#{pr['number']} ({pr['title']})" for pr in prs[:2])
            parts.append(f"{len(prs)} open PR{'s' if len(prs) != 1 else ''}: {pr_desc}")
        confs = r["conflicts"]
        total_conflicts += len(confs)
        if confs:
            parts.append(f"{len(confs)} conflict{'s' if len(confs) != 1 else ''} ({', '.join(confs[:2])})")

        if parts:
            repo_summaries.append(f"{p_name}: {'; '.join(parts)}")

    if not repo_summaries:
        return f"All {len(repos)} GitHub repositories are clean and up to date with no merge conflicts or open pull requests."

    summary_text = f"Checked {len(repos)} repositor{'y' if len(repos) == 1 else 'ies'}. " + ". ".join(repo_summaries) + "."
    return summary_text
