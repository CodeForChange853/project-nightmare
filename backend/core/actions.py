"""Allowlisted actions: open apps, open folders, run predefined tasks.

Nothing here accepts a free-form shell string from the model. Every action is
built from an entry in apps.json (or, if you enable it, a raw command that always
needs a click-to-confirm). Processes are started with shell=False.
"""
from __future__ import annotations

import json
import os
import secrets
import shlex
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path

from ..tools.fs_reader import normalize, project_dir_by_name

DEVNULL = subprocess.DEVNULL
NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)
DETACHED = getattr(subprocess, "DETACHED_PROCESS", 0) | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
CMD_UNSAFE = '&|<>^%"\r\n'


class ActionError(Exception):
    pass


@dataclass
class ActionPlan:
    kind: str  # open_app | open_folder | open_project_in | run_task | run_command
    label: str  # shown to the user, also on the confirmation prompt
    argv: list | None = None
    cwd: Path | None = None
    path: Path | None = None  # open_folder only
    wait: bool = False
    timeout: int = 30
    needs_confirm: bool = False


@dataclass
class ActionResult:
    ok: bool
    message: str


class Registry:
    """apps.json: {"apps": {...}, "tasks": {...}}"""

    def __init__(self, data: dict | None = None):
        self.replace(data)

    def replace(self, data: dict | None) -> None:
        """Swap in a new allowlist in place, so everything holding this registry sees it at once."""
        data = data or {}
        self.apps: dict = data.get("apps", {})
        self.tasks: dict = data.get("tasks", {})

    def as_dict(self) -> dict:
        return {"apps": self.apps, "tasks": self.tasks}

    @classmethod
    def load(cls, path: Path) -> "Registry":
        path = Path(path)
        if not path.is_file():
            return cls({})
        try:
            return cls(json.loads(path.read_text(encoding="utf-8")))
        except (OSError, ValueError) as exc:
            raise ActionError(f"Could not read {path}: {exc}") from exc

    @staticmethod
    def _match(table: dict, text_norm: str):
        padded, best, best_len = f" {text_norm} ", None, 0
        for key, spec in table.items():
            for name in [key, *spec.get("aliases", [])]:
                alias = normalize(name)
                if alias and f" {alias} " in padded and len(alias) > best_len:
                    best, best_len = key, len(alias)
        return best

    def find_app(self, text_norm: str):
        return self._match(self.apps, text_norm)

    def find_task(self, text_norm: str):
        return self._match(self.tasks, text_norm)


def _argv(spec: dict, name: str) -> list[str]:
    argv = spec.get("argv")
    if not isinstance(argv, list) or not argv or not all(isinstance(a, str) for a in argv):
        raise ActionError(f"'{name}' has no valid argv in apps.json")
    return list(argv)


def plan_open_app(reg: Registry, app_id: str) -> ActionPlan:
    spec = reg.apps[app_id]
    return ActionPlan(
        "open_app",
        f"open {spec.get('label', app_id)}",
        argv=_argv(spec, app_id),
        needs_confirm=bool(spec.get("confirm", False)),
    )


def plan_open_folder(project_dir: Path) -> ActionPlan:
    return ActionPlan("open_folder", f"open the {project_dir.name} folder", path=project_dir)


def plan_open_project_in(reg: Registry, app_id: str, project_dir: Path) -> ActionPlan:
    spec = reg.apps[app_id]
    label = spec.get("label", app_id)
    if not spec.get("project_arg"):
        raise ActionError(f"{label} isn't set up to open projects (add \"project_arg\": true).")
    argv = _argv(spec, app_id)
    if spec.get("project_flag"):
        argv.append(str(spec["project_flag"]))
    argv.append(str(project_dir))
    return ActionPlan(
        "open_project_in",
        f"open {project_dir.name} in {label}",
        argv=argv,
        cwd=project_dir,
        needs_confirm=bool(spec.get("confirm", False)),
    )


def plan_run_task(reg: Registry, task_id: str, desktop_root: Path) -> ActionPlan:
    spec = reg.tasks[task_id]
    argv = _argv(spec, task_id)
    cwd = desktop_root
    if spec.get("project"):
        project = project_dir_by_name(desktop_root, spec["project"])
        if project is None:
            raise ActionError(f"Project folder '{spec['project']}' was not found on the Desktop.")
        cwd = project
    return ActionPlan(
        "run_task",
        f"{spec.get('label', task_id)} ({subprocess.list2cmdline(argv)} in {cwd.name})",
        argv=argv,
        cwd=cwd,
        wait=bool(spec.get("wait", False)),
        timeout=int(spec.get("timeout", 60)),
        needs_confirm=bool(spec.get("confirm", True)),
    )


def plan_run_command(command: str, desktop_root: Path, allowed: bool) -> ActionPlan:
    if not allowed:
        raise ActionError(
            "Raw commands are off. Add it to apps.json as a task, or set ALLOW_RAW_COMMANDS=1 in .env."
        )
    argv = shlex.split(command, posix=(os.name != "nt"))
    if os.name == "nt":
        argv = [a[1:-1] if len(a) >= 2 and a[0] == a[-1] == '"' else a for a in argv]
    if not argv:
        raise ActionError("No command was given.")
    return ActionPlan(
        "run_command",
        f"run command: {command} (in {desktop_root.name})",
        argv=argv,
        cwd=desktop_root,
        wait=True,
        timeout=30,
        needs_confirm=True,
    )


def _resolve_exe(argv: list[str]):
    exe = shutil.which(argv[0])
    if exe is None:
        return None
    if exe.lower().endswith((".cmd", ".bat")):
        for arg in argv[1:]:
            if any(ch in arg for ch in CMD_UNSAFE):
                raise ActionError("Refusing to pass special characters to a .cmd/.bat launcher.")
    return [exe, *argv[1:]]


def _launch_detached(argv: list[str], cwd: Path | None) -> None:
    full = _resolve_exe(argv)
    if full is None:
        if sys.platform == "win32":
            # ShellExecute also finds apps registered under App Paths, e.g. chrome.exe
            args = subprocess.list2cmdline(argv[1:])
            if args:
                os.startfile(argv[0], arguments=args)  # type: ignore[attr-defined]
            else:
                os.startfile(argv[0])  # type: ignore[attr-defined]
            return
        raise ActionError(f"'{argv[0]}' was not found on PATH.")
    kwargs = {"cwd": str(cwd) if cwd else None, "stdin": DEVNULL, "stdout": DEVNULL, "stderr": DEVNULL}
    if sys.platform == "win32":
        kwargs["creationflags"] = DETACHED
    else:
        kwargs["start_new_session"] = True
    subprocess.Popen(full, **kwargs)


def _run_captured(argv: list[str], cwd: Path | None, timeout: int) -> ActionResult:
    full = _resolve_exe(argv)
    if full is None:
        raise ActionError(f"'{argv[0]}' was not found on PATH.")
    try:
        proc = subprocess.run(
            full,
            cwd=str(cwd) if cwd else None,
            capture_output=True,
            stdin=DEVNULL,
            timeout=timeout,
            creationflags=NO_WINDOW,
        )
    except subprocess.TimeoutExpired as exc:
        raise ActionError(f"Timed out after {timeout} seconds.") from exc
    text = (proc.stdout + proc.stderr).decode("utf-8", errors="replace").strip()
    tail = "\n".join(text.splitlines()[-30:])[-1500:]
    head = "Finished." if proc.returncode == 0 else f"Failed with exit code {proc.returncode}."
    return ActionResult(proc.returncode == 0, head + (f"\n{tail}" if tail else ""))


def _open_path(path: Path) -> None:
    if sys.platform == "win32":
        os.startfile(str(path))  # type: ignore[attr-defined]
    elif sys.platform == "darwin":
        subprocess.Popen(["open", str(path)])
    else:
        subprocess.Popen(["xdg-open", str(path)])


def execute(plan: ActionPlan) -> ActionResult:
    try:
        if plan.kind == "open_folder":
            if plan.path is None or not plan.path.is_dir():
                raise ActionError("That folder no longer exists.")
            _open_path(plan.path)
            return ActionResult(True, f"Opened {plan.path.name}.")
        if plan.cwd is not None and not plan.cwd.is_dir():
            raise ActionError("The working folder no longer exists.")
        if not plan.argv:
            raise ActionError("Nothing to run.")
        if plan.wait:
            return _run_captured(plan.argv, plan.cwd, plan.timeout)
        _launch_detached(plan.argv, plan.cwd)
        return ActionResult(True, f"Done: {plan.label}.")
    except ActionError as exc:
        return ActionResult(False, str(exc))
    except OSError as exc:
        return ActionResult(False, f"Could not run that: {exc}")


class PendingStore:
    """Plans waiting for a click. Held server-side so the id cannot be swapped for another action."""

    def __init__(self, ttl: int = 60, clock=time.monotonic):
        self.ttl = ttl
        self._clock = clock
        self._items: dict[str, tuple[float, ActionPlan]] = {}

    def _purge(self) -> None:
        now = self._clock()
        for key in [k for k, (expires, _) in self._items.items() if expires <= now]:
            del self._items[key]

    def add(self, plan: ActionPlan) -> str:
        self._purge()
        pid = secrets.token_urlsafe(9)
        self._items[pid] = (self._clock() + self.ttl, plan)
        return pid

    def clear(self) -> None:
        """Drop every waiting plan (the allowlist changed, so they may no longer match it)."""
        self._items.clear()

    def pop(self, pid: str) -> ActionPlan | None:
        self._purge()
        item = self._items.pop(pid, None)
        return item[1] if item else None
