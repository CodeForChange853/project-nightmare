import pytest
from datetime import datetime, timedelta
from backend.core.router import route
from backend.config import Settings
from backend.core.actions import Registry
from backend.core.orchestrator import Orchestrator
from backend.core.llm import NoLLMProvider
from backend.tools.audit import Audit
import dataclasses


def test_calendar_and_task_schemas_and_methods(tmp_path):
    db_file = tmp_path / "test_audit.db"
    audit = Audit(db_file)

    # Calendar Events
    ev1 = audit.add_calendar_event("Sprint Planning", "meeting", "2026-10-26T09:00:00")
    assert ev1["id"] is not None
    assert ev1["title"] == "Sprint Planning"

    events = audit.list_calendar_events()
    assert len(events) == 1
    assert events[0]["title"] == "Sprint Planning"

    range_events = audit.get_calendar_events_in_range("2026-10-26T00:00:00", "2026-10-26T23:59:59")
    assert len(range_events) == 1

    out_range = audit.get_calendar_events_in_range("2026-11-01T00:00:00", "2026-11-02T00:00:00")
    assert len(out_range) == 0

    assert audit.delete_calendar_event(ev1["id"]) is True
    assert len(audit.list_calendar_events()) == 0

    # Measurable Tasks
    t1 = audit.add_measurable_task("Client Outreach", current_progress=0, target_progress=5, unit="clients")
    assert t1["id"] is not None
    assert t1["current_progress"] == 0
    assert t1["target_progress"] == 5

    tasks = audit.list_measurable_tasks()
    assert len(tasks) == 1

    t_up = audit.update_measurable_task_progress("client", current_progress=2)
    assert t_up is not None
    assert t_up["current_progress"] == 2
    assert t_up["target_progress"] == 5

    t_get = audit.get_measurable_task(title="Client Outreach")
    assert t_get is not None
    assert t_get["current_progress"] == 2

    assert audit.delete_measurable_task(t1["id"]) is True
    assert len(audit.list_measurable_tasks()) == 0


def test_router_calendar_and_measurable_task_intents():
    settings = Settings.from_env()
    reg = Registry.load(settings.apps_file)

    # Calendar intent
    i_cal1 = route("do I have any meetings this week", settings, reg)
    assert i_cal1.kind == "calendar_query"
    assert "week" in (i_cal1.query or "")

    i_cal2 = route("what meetings do I have this week", settings, reg)
    assert i_cal2.kind == "calendar_query"

    i_cal3 = route("any meetings this week", settings, reg)
    assert i_cal3.kind == "calendar_query"

    # Measurable Task: Update
    i_up1 = route("Update my 5 client progress to 2", settings, reg)
    assert i_up1.kind == "measurable_task"
    assert i_up1.action == "update"
    assert i_up1.current_progress == 2
    assert i_up1.target_progress == 5
    assert "client" in i_up1.query.lower()

    # Measurable Task: Create
    i_cr1 = route("write a 25 RRL", settings, reg)
    assert i_cr1.kind == "measurable_task"
    assert i_cr1.action == "create"
    assert i_cr1.target_progress == 25
    assert "rrl" in i_cr1.query.lower()

    # User activity log voice queries
    i_act1 = route("Create a task. To inform my 5 clients.", settings, reg)
    assert i_act1.kind == "measurable_task"
    assert i_act1.action == "create"
    assert i_act1.target_progress == 5
    assert "clients" in (i_act1.unit or "")

    i_act2 = route("Create a task. To acquire or finish the chapter one to three and my progress is 1.", settings, reg)
    assert i_act2.kind == "measurable_task"
    assert i_act2.action == "create"
    assert i_act2.target_progress == 3
    assert i_act2.current_progress == 1

    i_act3 = route("Have any task?", settings, reg)
    assert i_act3.kind == "measurable_task"
    assert i_act3.action == "list"

    i_act4 = route("What are in my calendar?", settings, reg)
    assert i_act4.kind == "calendar_query"

    i_act5 = route("Create a meeting scheduled tomorrow afternoon.", settings, reg)
    assert i_act5.kind == "calendar_create"

    i_act6 = route("open file GE9-Lesson7-El-Filibusterismo-Presentation.pptx and open in powerpoint", settings, reg)
    assert i_act6.kind == "open_file"
    assert i_act6.query == "GE9-Lesson7-El-Filibusterismo-Presentation.pptx"
    assert i_act6.note_text.lower() == "powerpoint"

    i_act7 = route("Open it in PowerPoint and move to slide 11.", settings, reg)
    assert i_act7.kind == "ppt_open_slide"
    assert i_act7.query == "it"
    assert i_act7.slide == 11


@pytest.mark.anyio
async def test_orchestrator_calendar_and_tasks(tmp_path):
    db_file = tmp_path / "test_orch.db"
    audit = Audit(db_file)
    settings = Settings.from_env()
    settings = dataclasses.replace(settings, db_path=db_file)
    reg = Registry.load(settings.apps_file)
    orch = Orchestrator(settings, NoLLMProvider(), reg, audit)

    # 1. Calendar query empty
    rep1 = await orch.handle("do I have any meetings this week")
    assert rep1.ok
    assert "no meetings" in rep1.text.lower()

    # 2. Add meeting in current week
    now = datetime.now().astimezone()
    mon = (now - timedelta(days=now.weekday())).replace(hour=10, minute=0, second=0)
    meet_time = (mon + timedelta(days=2)).isoformat()
    audit.add_calendar_event("Committee Defense", "meeting", meet_time)

    rep2 = await orch.handle("do I have any meetings this week")
    assert rep2.ok
    assert "Committee Defense" in rep2.text

    # 3. Create meeting via voice
    rep_meet = await orch.handle("Create a meeting scheduled tomorrow afternoon.")
    assert rep_meet.ok
    assert "scheduled" in rep_meet.text.lower() and "meeting" in rep_meet.text.lower()

    # 4. What are in my calendar
    rep_cal = await orch.handle("What are in my calendar?")
    assert rep_cal.ok
    assert "meeting" in rep_cal.text.lower()

    # 5. Create task
    rep3 = await orch.handle("write a 25 RRL")
    assert rep3.ok
    assert "RRL" in rep3.text and "25" in rep3.text

    # 6. Create task with speech punctuation & unit
    rep_cli = await orch.handle("Create a task. To inform my 5 clients.")
    assert rep_cli.ok
    assert "5" in rep_cli.text and "clients" in rep_cli.text.lower()

    # 7. Create task with chapters & progress
    rep_chap = await orch.handle("Create a task. To acquire or finish the chapter one to three and my progress is 1.")
    assert rep_chap.ok
    assert "chapters 1 to 3" in rep_chap.text.lower()

    # 8. Have any task?
    rep_list = await orch.handle("Have any task?")
    assert rep_list.ok
    assert "measurable task" in rep_list.text.lower()

    # 9. Update task
    rep4 = await orch.handle("Update my 5 client progress to 2")
    assert rep4.ok
    assert "2 of 5" in rep4.text
