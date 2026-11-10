import asyncio
import json
from pathlib import Path
import time
import pytest

from backend.core.actions import ActionPlan
from backend.core.llm import LLMProvider
from backend.core.orchestrator import Orchestrator
from backend.core.router import route
from backend.tools.audit import Audit
from backend.tools.workspace import (
    DevTask,
    detect_dev_tasks,
    pick_dev_task,
    priority,
    scan_project,
    workspace_briefing_from_snaps,
    workspace_changes,
    work_priorities,
)


class Fake(LLMProvider):
    name = "fake"

    async def complete(self, prompt, **kw):
        return "Fake completion."


@pytest.fixture
def orch(settings, registry):
    provider = Fake()
    o = Orchestrator(settings, provider, registry, Audit(settings.db_path))
    return o, provider


def say(orch, text, readonly=False):
    return asyncio.run(orch.handle(text, readonly=readonly))


@pytest.mark.parametrize("text,kind", [
    ("workspace briefing", "workspace_briefing"),
    ("give me a briefing", "workspace_briefing"),
    ("daily briefing", "workspace_briefing"),
    ("workspace status", "workspace_briefing"),
    ("what changed since yesterday", "workspace_changes"),
    ("changes since yesterday", "workspace_changes"),
    ("what did i change today", "workspace_changes"),
    ("what should i work on", "work_priorities"),
    ("which project should i work on", "work_priorities"),
    ("where should i start", "work_priorities"),
    ("run bims tests", "run_dev_task"),
    ("run tests in bims", "run_dev_task"),
    ("run build in bims", "run_dev_task"),
    ("run bims typecheck", "run_dev_task"),
    ("run bims lint", "run_dev_task"),
    ("run bims pytest", "run_dev_task"),
    ("run it again", "rerun_task"),
    ("run that again", "rerun_task"),
    ("rerun", "rerun_task"),
    ("retry last task", "rerun_task"),
])
def test_workspace_routing(text, kind, settings, registry):
    assert route(text, settings, registry).kind == kind


def test_detect_dev_tasks(tmp_path):
    proj = tmp_path / "myproj"
    proj.mkdir()
    (proj / "package.json").write_text(json.dumps({
        "scripts": {
            "test": "vitest run",
            "build": "vite build",
            "dev": "vite",
            "lint": "eslint .",
            "typecheck": "tsc --noEmit",
        }
    }), encoding="utf-8")

    tasks = detect_dev_tasks(proj)
    kinds = [t.kind for t in tasks]
    assert "test" in kinds
    assert "build" in kinds
    assert "dev" in kinds
    assert "lint" in kinds
    assert "typecheck" in kinds

    task_test, err = pick_dev_task(tasks, "test")
    assert err == ""
    assert task_test is not None
    assert task_test.kind == "test"
    assert task_test.wait is True

    task_dev, err = pick_dev_task(tasks, "dev")
    assert err == ""
    assert task_dev is not None
    assert task_dev.wait is False  # long running server is not waited for


def test_detect_subfolder_tasks_and_pytest(tmp_path):
    proj = tmp_path / "fullstack"
    frontend = proj / "frontend"
    backend = proj / "backend"
    frontend.mkdir(parents=True)
    backend.mkdir(parents=True)

    (frontend / "package.json").write_text(json.dumps({
        "scripts": {"test": "npm test"}
    }), encoding="utf-8")
    (backend / "conftest.py").write_text("# pytest marker", encoding="utf-8")

    tasks = detect_dev_tasks(proj)
    kinds = [t.kind for t in tasks]
    assert "test" in kinds
    assert "pytest" in kinds

    # Disambiguation when both exist and user asks for generic "test"
    picked, err = pick_dev_task(tasks, "test")
    assert picked is None
    assert "has both npm test and pytest" in err

    # Specific asks work
    picked_npm, err = pick_dev_task(tasks, "npmtest")
    assert err == ""
    assert picked_npm.kind == "test"

    picked_py, err = pick_dev_task(tasks, "pytest")
    assert err == ""
    assert picked_py.kind == "pytest"


def test_priority_calculation():
    now = 1000000.0
    clean_snap = {
        "project": "clean", "git": True, "branch": "main", "dirty": 0, "ahead": 0, "behind": 0,
        "commit_ts": int(now - 3600), "commit_subject": "recent", "handoff_mtime": 0, "todos": 0,
    }
    score_clean, why_clean = priority(clean_snap, dirty_days=0.0, now=now)
    assert score_clean == 0.0
    assert why_clean == []

    busy_snap = {
        "project": "busy", "git": True, "branch": "feature", "dirty": 3, "ahead": 2, "behind": 0,
        "commit_ts": int(now - (5 * 86400)), "commit_subject": "older", "handoff_mtime": int(now - 1000), "todos": 4,
    }
    score_busy, why_busy = priority(busy_snap, dirty_days=2.5, now=now)
    assert score_busy > 0.0
    assert any("uncommitted file" in w for w in why_busy)
    assert any("not pushed" in w for w in why_busy)
    assert any("last commit" in w for w in why_busy)
    assert any("TODO" in w for w in why_busy)
    assert any("handoff updated" in w for w in why_busy)


def test_workspace_briefing_from_snaps():
    snaps = [
        {"project": "p1", "git": True, "branch": "main", "dirty": 2, "ahead": 1, "behind": 0,
         "commit_ts": 0, "commit_subject": "", "handoff_mtime": 0, "todos": 3},
        {"project": "p2", "git": True, "branch": "main", "dirty": 0, "ahead": 0, "behind": 0,
         "commit_ts": 0, "commit_subject": "", "handoff_mtime": 0, "todos": 0},
    ]
    briefing = workspace_briefing_from_snaps(snaps)
    assert "2 projects on your Desktop" in briefing
    assert "2 uncommitted files across 1 project" in briefing
    assert "Unpushed commits: p1 has 1" in briefing
    assert "3 TODO or FIXME" in briefing


def test_audit_workspace_dirty_tracking(tmp_path):
    audit = Audit(tmp_path / "test.db")
    t0 = 1700000000

    # Project becomes dirty
    d_days = audit.update_workspace_dirty("proj1", dirty=2, now_ts=t0)
    assert d_days == 0.0

    # 2 days later, still dirty
    t1 = t0 + (2 * 86400)
    d_days = audit.update_workspace_dirty("proj1", dirty=3, now_ts=t1)
    assert abs(d_days - 2.0) < 0.01

    m = audit.get_dirty_days_map()
    assert "proj1" in m

    # Project is committed / clean
    d_days_clean = audit.update_workspace_dirty("proj1", dirty=0, now_ts=t1 + 100)
    assert d_days_clean == 0.0
    assert "proj1" not in audit.get_dirty_days_map()


def test_orchestrator_briefings_and_priorities(orch):
    o, _ = orch
    rep_briefing = say(o, "workspace briefing")
    assert rep_briefing.ok
    assert rep_briefing.intent == "workspace_briefing"
    assert "project" in rep_briefing.text.lower()

    rep_changes = say(o, "what changed since yesterday")
    assert rep_changes.ok
    assert rep_changes.intent == "workspace_changes"

    rep_priorities = say(o, "what should i work on")
    assert rep_priorities.ok
    assert rep_priorities.intent == "work_priorities"


def test_orchestrator_dev_tasks_flow(orch, settings, tmp_path):
    o, _ = orch
    # Create mock bims project on Desktop with a package.json
    bims = settings.desktop_root / "bims"
    bims.mkdir(parents=True, exist_ok=True)
    (bims / "package.json").write_text(json.dumps({
        "scripts": {"build": "node -v"}
    }), encoding="utf-8")

    # Asking to run build in bims asks for confirmation
    rep = say(o, "run build in bims")
    assert rep.ok
    assert rep.intent == "run_dev_task"
    assert rep.pending_id is not None
    assert "Confirm:" in rep.text

    # Approving executes it
    rep_conf = asyncio.run(o.confirm(rep.pending_id, True))
    assert rep_conf.ok

    # "run it again" reruns the same build task with confirmation
    rep_again = say(o, "run it again")
    assert rep_again.ok
    assert rep_again.intent == "rerun_task"
    assert rep_again.pending_id is not None
    assert "rerun" in rep_again.text.lower()


def test_readonly_blocks_dev_tasks_but_allows_briefings(orch, settings):
    o, _ = orch
    # Briefing is allowed on readonly
    rep_brief = say(o, "workspace briefing", readonly=True)
    assert rep_brief.ok
    assert rep_brief.intent == "workspace_briefing"

    # Dev tasks are blocked on readonly
    rep_task = say(o, "run build in bims", readonly=True)
    assert not rep_task.ok
    assert "read-only" in rep_task.text.lower()

    # Rerun is blocked on readonly
    rep_rerun = say(o, "run it again", readonly=True)
    assert not rep_rerun.ok
    assert "read-only" in rep_rerun.text.lower()
