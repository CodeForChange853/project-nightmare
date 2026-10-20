"""Editing apps.json from the Settings screen: validate, compare, write with backups.

The browser sends the whole allowlist back. Nothing is trusted: every field is checked against a
fixed shape, unknown keys are dropped, and two rules keep a saved entry from becoming a way to run
something without a click:
  - a task that is new or changed always asks before running (confirm: true);
  - an app whose program is a shell or script host (cmd, powershell, python, ...) always asks too.
Entries that are byte-for-byte what is already on disk keep whatever they had (hand-edited files).
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import tempfile
import time
from pathlib import Path

from ..tools.fs_reader import normalize, project_dir_by_name

ID_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,39}$")
FLAG_RE = re.compile(r"^-{1,2}[A-Za-z][A-Za-z0-9-]{0,30}$")
CONTROL_RE = re.compile(r"[\x00-\x1f\x7f]")
MAX_ENTRIES = 50
MAX_ARGV = 20
MAX_ALIASES = 10
KEEP_BACKUPS = 5
# programs that can run arbitrary code from their arguments: never one-step from the Settings screen
SHELLS = frozenset({
    "cmd", "powershell", "pwsh", "wsl", "bash", "sh", "wscript", "cscript", "mshta", "rundll32",
    "regsvr32", "python", "pythonw", "py", "node", "deno", "bun", "ruby", "perl", "php", "java",
    "javaw", "conhost", "schtasks", "reg", "msiexec", "certutil", "bitsadmin", "curl", "wget",
})


class ConfigError(ValueError):
    def __init__(self, errors: list[str]):
        super().__init__("; ".join(errors))
        self.errors = errors


def file_version(path: Path) -> str:
    """Hash of the file on disk, so a save can tell the file was edited by hand in the meantime."""
    try:
        return hashlib.sha256(Path(path).read_bytes()).hexdigest()[:16]
    except FileNotFoundError:
        return "missing"


def is_shell(program: str) -> bool:
    name = re.split(r"[\\/]", program.strip())[-1].lower()
    for ext in (".exe", ".cmd", ".bat", ".com"):
        if name.endswith(ext):
            name = name[: -len(ext)]
    return name in SHELLS


def _text(value, field: str, errors: list[str], *, limit: int, required: bool = True) -> str:
    if value is None or value == "":
        if required:
            errors.append(f"{field} is required.")
        return ""
    if not isinstance(value, str):
        errors.append(f"{field} must be text.")
        return ""
    value = value.strip()
    if required and not value:
        errors.append(f"{field} is required.")
    elif len(value) > limit:
        errors.append(f"{field} is longer than {limit} characters.")
    elif CONTROL_RE.search(value):
        errors.append(f"{field} contains a line break or control character.")
    return value


def _flag(value, field: str, errors: list[str], default: bool = False) -> bool:
    if value is None:
        return default
    if not isinstance(value, bool):
        errors.append(f"{field} must be true or false.")
        return default
    return value


def _argv(value, field: str, errors: list[str]) -> list[str]:
    if not isinstance(value, list) or not value:
        errors.append(f"{field}: the command needs at least the program name.")
        return []
    if len(value) > MAX_ARGV:
        errors.append(f"{field}: at most {MAX_ARGV} parts.")
        return []
    out = []
    for i, part in enumerate(value):
        part = _text(part, f"{field} part {i + 1}", errors, limit=300)
        if part:
            out.append(part)
    return out


def _aliases(value, field: str, errors: list[str]) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, list) or len(value) > MAX_ALIASES:
        errors.append(f"{field}: up to {MAX_ALIASES} spoken names.")
        return []
    out = []
    for alias in value:
        alias = _text(alias, f"{field} name", errors, limit=60)
        if alias and not normalize(alias):
            errors.append(f"{field}: “{alias}” has no letters or digits to match speech against.")
        elif alias and alias not in out:
            out.append(alias)
    return out


def _clean_app(app_id: str, spec, errors: list[str]) -> dict:
    where = f"App “{app_id}”"
    if not isinstance(spec, dict):
        errors.append(f"{where} is not an object.")
        return {}
    clean = {
        "label": _text(spec.get("label"), f"{where} label", errors, limit=60),
        "argv": _argv(spec.get("argv"), f"{where} command", errors),
        "aliases": _aliases(spec.get("aliases"), f"{where} spoken names", errors),
    }
    if _flag(spec.get("project_arg"), f"{where} project_arg", errors):
        clean["project_arg"] = True
        flag = _text(spec.get("project_flag"), f"{where} project flag", errors, limit=32, required=False)
        if flag:
            if FLAG_RE.match(flag):
                clean["project_flag"] = flag
            else:
                errors.append(f"{where} project flag must look like -d or --folder.")
    if _flag(spec.get("confirm"), f"{where} confirm", errors):
        clean["confirm"] = True
    return clean


def _clean_task(task_id: str, spec, errors: list[str], desktop_root: Path) -> dict:
    where = f"Task “{task_id}”"
    if not isinstance(spec, dict):
        errors.append(f"{where} is not an object.")
        return {}
    clean = {
        "label": _text(spec.get("label"), f"{where} label", errors, limit=60),
        "argv": _argv(spec.get("argv"), f"{where} command", errors),
        "aliases": _aliases(spec.get("aliases"), f"{where} spoken names", errors),
    }
    project = _text(spec.get("project"), f"{where} project", errors, limit=100, required=False)
    if project:
        if project_dir_by_name(desktop_root, project) is None:
            errors.append(f"{where}: there is no project folder called “{project}” on the Desktop.")
        clean["project"] = project
    clean["wait"] = _flag(spec.get("wait"), f"{where} wait", errors)
    timeout = spec.get("timeout", 60)
    if isinstance(timeout, bool) or not isinstance(timeout, int) or not 1 <= timeout <= 600:
        errors.append(f"{where} timeout must be a whole number of seconds from 1 to 600.")
        timeout = 60
    clean["timeout"] = timeout
    clean["confirm"] = _flag(spec.get("confirm"), f"{where} confirm", errors, default=True)
    return clean


def _table(data: dict, key: str, errors: list[str]) -> dict:
    table = data.get(key, {})
    if not isinstance(table, dict):
        errors.append(f"“{key}” must be an object.")
        return {}
    if len(table) > MAX_ENTRIES:
        errors.append(f"At most {MAX_ENTRIES} {key}.")
        return {}
    for entry_id in table:
        if not isinstance(entry_id, str) or not ID_RE.match(entry_id):
            errors.append(f"“{entry_id}” is not a valid id: use lowercase letters, digits and dashes (max 40).")
    return {k: v for k, v in table.items() if isinstance(k, str) and ID_RE.match(k)}


def validate(data, desktop_root: Path, current: dict) -> tuple[dict, list[str]]:
    """Return (clean config, notes about entries that were made to ask first). Raises ConfigError."""
    errors: list[str] = []
    if not isinstance(data, dict):
        raise ConfigError(["The settings must be an object with apps and tasks."])
    apps_in, tasks_in = _table(data, "apps", errors), _table(data, "tasks", errors)
    old_apps, old_tasks = current.get("apps", {}), current.get("tasks", {})
    notes: list[str] = []

    # an entry that is exactly what the file already has is kept byte for byte: Settings neither
    # reformats nor re-judges hand-written entries, it only checks what was added or changed here
    apps = {}
    for app_id, spec in apps_in.items():
        if app_id in old_apps and old_apps[app_id] == spec:
            apps[app_id] = spec
            continue
        clean = _clean_app(app_id, spec, errors)
        if clean.get("argv") and is_shell(clean["argv"][0]) and not clean.get("confirm"):
            clean["confirm"] = True
            notes.append(f"App “{app_id}” runs {clean['argv'][0]}, so it will ask before opening.")
        apps[app_id] = clean

    tasks = {}
    for task_id, spec in tasks_in.items():
        if task_id in old_tasks and old_tasks[task_id] == spec:
            tasks[task_id] = spec
            continue
        clean = _clean_task(task_id, spec, errors, desktop_root)
        if not clean.get("confirm"):
            clean["confirm"] = True
            notes.append(f"Task “{task_id}” was added or changed here, so it will ask before running.")
        tasks[task_id] = clean

    if errors:
        raise ConfigError(errors)
    return {"apps": apps, "tasks": tasks}, notes


def describe_changes(old: dict, new: dict) -> list[str]:
    out = []
    for key, noun in (("apps", "app"), ("tasks", "task")):
        before, after = old.get(key, {}), new.get(key, {})
        out += [f"added {noun} {i}" for i in after if i not in before]
        out += [f"changed {noun} {i}" for i in after if i in before and before[i] != after[i]]
        out += [f"removed {noun} {i}" for i in before if i not in after]
    return out


def save(path: Path, config: dict, backup_dir: Path) -> str:
    """Back up the current file, then replace it atomically. Returns the new version."""
    path = Path(path)
    if path.is_file():
        backup_dir.mkdir(parents=True, exist_ok=True)
        stamp = time.strftime("%Y%m%d-%H%M%S")
        n = 0
        while (backup_dir / f"apps-{stamp}-{n:03d}.json").exists():  # several saves in one second
            n += 1
        shutil.copy2(path, backup_dir / f"apps-{stamp}-{n:03d}.json")
        for old in sorted(backup_dir.glob("apps-*.json"))[:-KEEP_BACKUPS]:
            old.unlink(missing_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".apps-", suffix=".json", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as fh:
            json.dump(config, fh, indent=2, ensure_ascii=False)
            fh.write("\n")
        os.replace(tmp, path)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise
    return file_version(path)


def check_entry(kind: str, spec: dict, desktop_root: Path) -> dict:
    """Dry run for the Check button: what would start, and from where. Never runs anything."""
    argv = spec.get("argv") or []
    program = argv[0] if argv and isinstance(argv[0], str) else ""
    found = shutil.which(program) if program else None
    result = {
        "program": program,
        "found": found,
        "command_line": subprocess.list2cmdline([str(a) for a in argv]) if argv else "",
        "asks_first": bool(spec.get("confirm", kind == "task")) or (kind == "app" and is_shell(program)),
        "shell": bool(program) and is_shell(program),
    }
    if not found and program:
        result["note"] = (
            "Not on PATH. Windows will still try its registered app list (this is how chrome.exe opens)."
            if not spec.get("wait")
            else "Not on PATH, so this will fail. Use the full path to the program."
        )
    if kind == "task":
        project = spec.get("project")
        folder = project_dir_by_name(desktop_root, project) if project else desktop_root
        result["folder"] = str(folder) if folder else None
        if project and folder is None:
            result["note"] = f"There is no project folder called “{project}” on the Desktop."
    return result
