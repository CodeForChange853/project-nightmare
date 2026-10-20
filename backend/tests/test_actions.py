import sys

import pytest

from backend.core import actions
from backend.core.actions import ActionError, PendingStore


def test_open_project_requires_project_arg(registry, desktop):
    with pytest.raises(ActionError):
        actions.plan_open_project_in(registry, "chrome", desktop / "bims")


def test_open_project_in_builds_argv(registry, desktop):
    plan = actions.plan_open_project_in(registry, "vscode", desktop / "bims")
    assert plan.argv == ["code", str(desktop / "bims")]
    assert not plan.needs_confirm


def test_task_defaults_to_confirm_and_shows_exact_command(registry, desktop):
    plan = actions.plan_run_task(registry, "bims-dev", desktop)
    assert plan.needs_confirm
    assert "npm run dev" in plan.label and plan.cwd == desktop / "bims"


def test_task_with_missing_project_fails(registry, tmp_path):
    empty = tmp_path / "empty"
    empty.mkdir()
    with pytest.raises(ActionError):
        actions.plan_run_task(registry, "bims-dev", empty)


def test_raw_commands_disabled_by_default(desktop):
    with pytest.raises(ActionError):
        actions.plan_run_command("dir", desktop, allowed=False)


def test_raw_commands_always_confirm(desktop):
    plan = actions.plan_run_command("git status", desktop, allowed=True)
    assert plan.needs_confirm and plan.argv[0] == "git"


def test_pending_is_one_shot_and_expires(desktop):
    now = [0.0]
    store = PendingStore(ttl=60, clock=lambda: now[0])
    plan = actions.plan_open_folder(desktop / "bims")
    pid = store.add(plan)
    assert store.pop(pid) is plan
    assert store.pop(pid) is None  # one-shot
    pid2 = store.add(plan)
    now[0] = 61
    assert store.pop(pid2) is None  # expired
    assert store.pop("not-a-real-id") is None


def test_execute_captured_runs_real_process(tmp_path):
    plan = actions.ActionPlan("run_task", "echo", argv=[sys.executable, "-c", "print('hi from task')"],
                              cwd=tmp_path, wait=True, timeout=20)
    result = actions.execute(plan)
    assert result.ok and "hi from task" in result.message


def test_execute_reports_failure_and_timeout(tmp_path):
    bad = actions.ActionPlan("run_task", "bad", argv=[sys.executable, "-c", "raise SystemExit(3)"],
                             cwd=tmp_path, wait=True, timeout=20)
    r = actions.execute(bad)
    assert not r.ok and "exit code 3" in r.message
    slow = actions.ActionPlan("run_task", "slow", argv=[sys.executable, "-c", "import time; time.sleep(5)"],
                              cwd=tmp_path, wait=True, timeout=1)
    assert "Timed out" in actions.execute(slow).message


def test_execute_missing_program(tmp_path):
    plan = actions.ActionPlan("run_task", "x", argv=["definitely-not-a-program-xyz"], cwd=tmp_path, wait=True)
    r = actions.execute(plan)
    assert not r.ok and "not found" in r.message


@pytest.mark.skipif(sys.platform == "win32", reason="posix launcher path")
def test_execute_detached_launch(tmp_path):
    plan = actions.ActionPlan("open_app", "launch", argv=[sys.executable, "-c", "pass"], cwd=tmp_path)
    assert actions.execute(plan).ok
