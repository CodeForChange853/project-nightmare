"""Tests for Phase 8D: Level 5 Shared Drive Excel Timeline Sync,
Team Quota Tracker, and 3-Day Stale Email Nudger.
"""
from __future__ import annotations

import asyncio
import io
import time
import zipfile
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from backend.config import Settings
from backend.core.actions import Registry, execute, plan_send_team_nudge
from backend.core.clearance import ClearanceManager, LEVEL_5
from backend.core.orchestrator import Orchestrator
from backend.core.router import route
from backend.tools.audit import Audit
from backend.tools.email_notifier import create_nudge_email_draft, send_nudge_email
from backend.tools.team_tracker import (
    COLOR_BUFFER_HEX,
    COLOR_CORE_HEX,
    COLOR_MILESTONE_HEX,
    COLOR_PHASE1_HEX,
    COLOR_PHASE2_HEX,
    COLOR_INDIGO_HEX,
    OpenXMLSheetReader,
    parse_team_tasks_sheet,
    parse_timeline_sheet,
    parse_roadmap_sheet,
    parse_weekly_gantt_sheet,
    parse_objectives_sheet,
    compute_dashboard_metrics,
    compare_timeline_sources,
    check_gdrive_source,
    scan_team_progress,
)


def generate_nexenroll_test_fixture(days_ago: float = 4.0) -> bytes:
    """Generates an in-memory .xlsx file matching NexEnroll_Development_Timeline.xlsx."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        # [Content_Types].xml
        types_el = ET.Element("Types", {"xmlns": "http://schemas.openxmlformats.org/package/2006/content-types"})
        ET.SubElement(types_el, "Default", {"Extension": "rels", "ContentType": "application/vnd.openxmlformats-package.relationships+xml"})
        ET.SubElement(types_el, "Default", {"Extension": "xml", "ContentType": "application/xml"})
        ET.SubElement(types_el, "Override", {"PartName": "/xl/workbook.xml", "ContentType": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"})
        ET.SubElement(types_el, "Override", {"PartName": "/xl/worksheets/sheet1.xml", "ContentType": "application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"})
        ET.SubElement(types_el, "Override", {"PartName": "/xl/worksheets/sheet2.xml", "ContentType": "application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"})
        ET.SubElement(types_el, "Override", {"PartName": "/xl/styles.xml", "ContentType": "application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"})
        ET.SubElement(types_el, "Override", {"PartName": "/xl/sharedStrings.xml", "ContentType": "application/vnd.openxmlformats-officedocument.spreadsheetml.sharedStrings+xml"})
        z.writestr("[Content_Types].xml", ET.tostring(types_el, encoding="utf-8", xml_declaration=True))

        # _rels/.rels
        rels_el = ET.Element("Relationships", {"xmlns": "http://schemas.openxmlformats.org/package/2006/relationships"})
        ET.SubElement(rels_el, "Relationship", {"Id": "rId1", "Type": "http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument", "Target": "xl/workbook.xml"})
        z.writestr("_rels/.rels", ET.tostring(rels_el, encoding="utf-8", xml_declaration=True))

        # xl/_rels/workbook.xml.rels
        wb_rels_el = ET.Element("Relationships", {"xmlns": "http://schemas.openxmlformats.org/package/2006/relationships"})
        ET.SubElement(wb_rels_el, "Relationship", {"Id": "rId1", "Type": "http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet", "Target": "worksheets/sheet1.xml"})
        ET.SubElement(wb_rels_el, "Relationship", {"Id": "rId2", "Type": "http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet", "Target": "worksheets/sheet2.xml"})
        ET.SubElement(wb_rels_el, "Relationship", {"Id": "rId3", "Type": "http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles", "Target": "styles.xml"})
        ET.SubElement(wb_rels_el, "Relationship", {"Id": "rId4", "Type": "http://schemas.openxmlformats.org/officeDocument/2006/relationships/sharedStrings", "Target": "sharedStrings.xml"})
        z.writestr("xl/_rels/workbook.xml.rels", ET.tostring(wb_rels_el, encoding="utf-8", xml_declaration=True))

        # xl/workbook.xml
        wb_el = ET.Element("workbook", {
            "xmlns": "http://schemas.openxmlformats.org/spreadsheetml/2006/main",
            "xmlns:r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
        })
        sheets_el = ET.SubElement(wb_el, "sheets")
        ET.SubElement(sheets_el, "sheet", {"name": "Timeline", "sheetId": "1", "r:id": "rId1"})
        ET.SubElement(sheets_el, "sheet", {"name": "Team_Tasks", "sheetId": "2", "r:id": "rId2"})
        z.writestr("xl/workbook.xml", ET.tostring(wb_el, encoding="utf-8", xml_declaration=True))

        # xl/styles.xml:
        styles_el = ET.Element("styleSheet", {"xmlns": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"})
        fills_el = ET.SubElement(styles_el, "fills", {"count": "5"})
        f0 = ET.SubElement(fills_el, "fill"); ET.SubElement(f0, "patternFill", {"patternType": "none"})
        f1 = ET.SubElement(fills_el, "fill"); ET.SubElement(f1, "patternFill", {"patternType": "gray125"})
        # 2: Core Work #9DC3E6
        f2 = ET.SubElement(fills_el, "fill"); p2 = ET.SubElement(f2, "patternFill", {"patternType": "solid"}); ET.SubElement(p2, "fgColor", {"rgb": f"FF{COLOR_CORE_HEX}"})
        # 3: Buffer/Polish #C6E0B4
        f3 = ET.SubElement(fills_el, "fill"); p3 = ET.SubElement(f3, "patternFill", {"patternType": "solid"}); ET.SubElement(p3, "fgColor", {"rgb": f"FF{COLOR_BUFFER_HEX}"})
        # 4: Milestone #FFD966
        f4 = ET.SubElement(fills_el, "fill"); p4 = ET.SubElement(f4, "patternFill", {"patternType": "solid"}); ET.SubElement(p4, "fgColor", {"rgb": f"FF{COLOR_MILESTONE_HEX}"})

        cell_xfs_el = ET.SubElement(styles_el, "cellXfs", {"count": "4"})
        ET.SubElement(cell_xfs_el, "xf", {"numFmtId": "0", "fontId": "0", "fillId": "0", "borderId": "0", "xfId": "0"})
        ET.SubElement(cell_xfs_el, "xf", {"numFmtId": "0", "fontId": "0", "fillId": "2", "borderId": "0", "xfId": "0", "applyFill": "1"}) # 1: Core
        ET.SubElement(cell_xfs_el, "xf", {"numFmtId": "0", "fontId": "0", "fillId": "3", "borderId": "0", "xfId": "0", "applyFill": "1"}) # 2: Buffer
        ET.SubElement(cell_xfs_el, "xf", {"numFmtId": "0", "fontId": "0", "fillId": "4", "borderId": "0", "xfId": "0", "applyFill": "1"}) # 3: Milestone
        z.writestr("xl/styles.xml", ET.tostring(styles_el, encoding="utf-8", xml_declaration=True))

        # 18 Tasks for NexEnroll Development Timeline
        task_names = [
            "Requirements Gathering & Analysis",
            "System Architecture & Database Design",
            "Authentication & RBAC Module",
            "Student Information Management",
            "Course Catalog & Curriculum Planning",
            "Enrollment & Registration Engine",
            "Billing & Payment Gateway Integration",
            "Grade Management & Transcripts",
            "Faculty & Advisor Portal",
            "Student Self-Service Portal",
            "Administrative Dashboard & Reports",
            "Audit Logging & Security Hardening",
            "Data Migration & Legacy Sync",
            "System Integration & API Testing",
            "User Acceptance Testing (UAT)",
            "Performance Tuning & Stress Testing",
            "Deployment & Infrastructure Setup",
            "Final Documentation & Handover",
        ]

        shared_strings = [
            "#", "Phase / Task", "Deliverable",
            "Month 1", "Month 2", "Month 3", "Month 4", "Month 5", "Month 6", "Month 7",
            "⭐ Architecture Signed Off",
            "⭐ Core Engine Complete",
            "⭐ Beta Testing Ready",
            "⭐ Production Launch",
            "Task_ID", "Assigned_Team", "Owner_Email", "Task_Name", "Current_Count", "Target_Count", "Last_Updated",
            "TASK-1", "Team 1", "team1.lead@example.com", "Gather RRL",
            "TASK-2", "Team 2", "team2.lead@example.com", "API Integration Tests",
        ]
        # Append task names and deliverables
        for t in task_names:
            shared_strings.append(t)
            shared_strings.append(f"{t} Deliverable")

        dt_stale = (datetime.now() - timedelta(days=days_ago)).strftime("%Y-%m-%d")
        dt_fresh = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
        shared_strings.append(dt_stale)
        shared_strings.append(dt_fresh)

        sst_el = ET.Element("sst", {"xmlns": "http://schemas.openxmlformats.org/spreadsheetml/2006/main", "count": str(len(shared_strings))})
        for s in shared_strings:
            si = ET.SubElement(sst_el, "si")
            ET.SubElement(si, "t").text = s
        z.writestr("xl/sharedStrings.xml", ET.tostring(sst_el, encoding="utf-8", xml_declaration=True))

        s_map = {s: i for i, s in enumerate(shared_strings)}

        # sheet1: Timeline (18 tasks)
        ws1 = ET.Element("worksheet", {"xmlns": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"})
        sd1 = ET.SubElement(ws1, "sheetData")
        # Row 1 headers: #, Phase / Task, Deliverable, Month 1..Month 7
        r1 = ET.SubElement(sd1, "row", {"r": "1"})
        h_cols = ["A", "B", "C", "D", "E", "F", "G", "H", "I", "J"]
        headers = ["#", "Phase / Task", "Deliverable", "Month 1", "Month 2", "Month 3", "Month 4", "Month 5", "Month 6", "Month 7"]
        for col_l, h in zip(h_cols, headers):
            c = ET.SubElement(r1, "c", {"r": f"{col_l}1", "t": "s"})
            ET.SubElement(c, "v").text = str(s_map[h])

        # Rows 2 to 19 (18 tasks)
        for idx, t_name in enumerate(task_names, start=1):
            r_num = idx + 1
            row_el = ET.SubElement(sd1, "row", {"r": str(r_num)})
            # A: #
            c = ET.SubElement(row_el, "c", {"r": f"A{r_num}"})
            ET.SubElement(c, "v").text = str(idx)
            # B: Task
            c = ET.SubElement(row_el, "c", {"r": f"B{r_num}", "t": "s"})
            ET.SubElement(c, "v").text = str(s_map[t_name])
            # C: Deliverable
            c = ET.SubElement(row_el, "c", {"r": f"C{r_num}", "t": "s"})
            ET.SubElement(c, "v").text = str(s_map[f"{t_name} Deliverable"])

            # Month columns D..J (M1..M7)
            # Assign color styles & milestones
            if idx in (1, 2):
                # Month 1: Core (s=1), Month 2: Buffer (s=2)
                ET.SubElement(row_el, "c", {"r": f"D{r_num}", "s": "1"})
                ET.SubElement(row_el, "c", {"r": f"E{r_num}", "s": "2"})
                if idx == 2:
                    # M1 milestone: ⭐ Architecture Signed Off
                    c_m = ET.SubElement(row_el, "c", {"r": f"D{r_num}", "s": "3", "t": "s"})
                    ET.SubElement(c_m, "v").text = str(s_map["⭐ Architecture Signed Off"])
            elif idx in (3, 4, 5, 6):
                # Month 2-3 Core, Month 4 Buffer
                ET.SubElement(row_el, "c", {"r": f"E{r_num}", "s": "1"})
                ET.SubElement(row_el, "c", {"r": f"F{r_num}", "s": "1"})
                ET.SubElement(row_el, "c", {"r": f"G{r_num}", "s": "2"})
                if idx == 6:
                    c_m = ET.SubElement(row_el, "c", {"r": f"F{r_num}", "s": "3", "t": "s"})
                    ET.SubElement(c_m, "v").text = str(s_map["⭐ Core Engine Complete"])
            elif idx in (7, 8, 9, 10, 11, 12):
                # Month 4-5 Core, Month 6 Buffer
                ET.SubElement(row_el, "c", {"r": f"G{r_num}", "s": "1"})
                ET.SubElement(row_el, "c", {"r": f"H{r_num}", "s": "1"})
                ET.SubElement(row_el, "c", {"r": f"I{r_num}", "s": "2"})
                if idx == 12:
                    c_m = ET.SubElement(row_el, "c", {"r": f"H{r_num}", "s": "3", "t": "s"})
                    ET.SubElement(c_m, "v").text = str(s_map["⭐ Beta Testing Ready"])
            else:
                # Month 6-7 Core & Final Buffer
                ET.SubElement(row_el, "c", {"r": f"I{r_num}", "s": "1"})
                ET.SubElement(row_el, "c", {"r": f"J{r_num}", "s": "2"})
                if idx == 18:
                    c_m = ET.SubElement(row_el, "c", {"r": f"J{r_num}", "s": "3", "t": "s"})
                    ET.SubElement(c_m, "v").text = str(s_map["⭐ Production Launch"])

        z.writestr("xl/worksheets/sheet1.xml", ET.tostring(ws1, encoding="utf-8", xml_declaration=True))

        # sheet2: Team_Tasks
        ws2 = ET.Element("worksheet", {"xmlns": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"})
        sd2 = ET.SubElement(ws2, "sheetData")
        # Row 1 Headers
        r1 = ET.SubElement(sd2, "row", {"r": "1"})
        t_headers = ["Task_ID", "Assigned_Team", "Owner_Email", "Task_Name", "Current_Count", "Target_Count", "Last_Updated"]
        for col_l, h in zip(["A", "B", "C", "D", "E", "F", "G"], t_headers):
            c = ET.SubElement(r1, "c", {"r": f"{col_l}1", "t": "s"})
            ET.SubElement(c, "v").text = str(s_map[h])

        # Row 2: TASK-1, Team 1, team1.lead@example.com, Gather RRL, 10, 25, dt_stale (4 days ago)
        r2 = ET.SubElement(sd2, "row", {"r": "2"})
        c = ET.SubElement(r2, "c", {"r": "A2", "t": "s"}); ET.SubElement(c, "v").text = str(s_map["TASK-1"])
        c = ET.SubElement(r2, "c", {"r": "B2", "t": "s"}); ET.SubElement(c, "v").text = str(s_map["Team 1"])
        c = ET.SubElement(r2, "c", {"r": "C2", "t": "s"}); ET.SubElement(c, "v").text = str(s_map["team1.lead@example.com"])
        c = ET.SubElement(r2, "c", {"r": "D2", "t": "s"}); ET.SubElement(c, "v").text = str(s_map["Gather RRL"])
        c = ET.SubElement(r2, "c", {"r": "E2"}); ET.SubElement(c, "v").text = "10"
        c = ET.SubElement(r2, "c", {"r": "F2"}); ET.SubElement(c, "v").text = "25"
        c = ET.SubElement(r2, "c", {"r": "G2", "t": "s"}); ET.SubElement(c, "v").text = str(s_map[dt_stale])

        # Row 3: TASK-2, Team 2, team2.lead@example.com, API Integration Tests, 20, 20, dt_fresh (1 day ago)
        r3 = ET.SubElement(sd2, "row", {"r": "3"})
        c = ET.SubElement(r3, "c", {"r": "A3", "t": "s"}); ET.SubElement(c, "v").text = str(s_map["TASK-2"])
        c = ET.SubElement(r3, "c", {"r": "B3", "t": "s"}); ET.SubElement(c, "v").text = str(s_map["Team 2"])
        c = ET.SubElement(r3, "c", {"r": "C3", "t": "s"}); ET.SubElement(c, "v").text = str(s_map["team2.lead@example.com"])
        c = ET.SubElement(r3, "c", {"r": "D3", "t": "s"}); ET.SubElement(c, "v").text = str(s_map["API Integration Tests"])
        c = ET.SubElement(r3, "c", {"r": "E3"}); ET.SubElement(c, "v").text = "20"
        c = ET.SubElement(r3, "c", {"r": "F3"}); ET.SubElement(c, "v").text = "20"
        c = ET.SubElement(r3, "c", {"r": "G3", "t": "s"}); ET.SubElement(c, "v").text = str(s_map[dt_fresh])

        z.writestr("xl/worksheets/sheet2.xml", ET.tostring(ws2, encoding="utf-8", xml_declaration=True))

    return buf.getvalue()


@pytest.fixture
def test_xlsx_file(tmp_path: Path) -> Path:
    fixture_bytes = generate_nexenroll_test_fixture(days_ago=4.0)
    xlsx_path = tmp_path / "NexEnroll_Development_Timeline.xlsx"
    xlsx_path.write_bytes(fixture_bytes)
    return xlsx_path


@pytest.fixture
def audit_db(tmp_path: Path) -> Audit:
    db_file = tmp_path / "test_nightmare.db"
    return Audit(db_file)


# ==============================================================================
# Gate 1: Parser Verification
# ==============================================================================

def test_parse_timeline_sheet_18_tasks_and_colors(test_xlsx_file: Path):
    reader = OpenXMLSheetReader(test_xlsx_file)
    grid = reader.read_sheet("timeline")
    tasks = parse_timeline_sheet(grid)

    assert len(tasks) == 18, f"Expected 18 tasks, got {len(tasks)}"
    assert tasks[0]["number"] == 1
    assert tasks[0]["task"] == "Requirements Gathering & Analysis"
    assert len(tasks[0]["months"]) == 7

    # Check color classifications
    # Task 1: Month 1 is Core Work (#9DC3E6)
    m1 = tasks[0]["months"][0]
    assert m1["month"] == 1
    assert m1["status"] == "core"
    assert m1["color"] == "#9DC3E6"

    # Task 1: Month 2 is Buffer/Polish (#C6E0B4)
    m2 = tasks[0]["months"][1]
    assert m2["month"] == 2
    assert m2["status"] == "buffer"
    assert m2["color"] == "#C6E0B4"

    # Task 2: Month 1 has Milestone ⭐ Architecture Signed Off (#FFD966)
    t2_m1 = tasks[1]["months"][0]
    assert t2_m1["status"] == "milestone"
    assert "⭐" in t2_m1["text"]
    assert t2_m1["color"] == "#FFD966"

    # Task 18: Month 7 Milestone ⭐ Production Launch
    t18_m7 = tasks[17]["months"][6]
    assert t18_m7["status"] == "milestone"
    assert "⭐" in t18_m7["text"]


def test_parse_team_tasks_sheet_quota_and_stale(test_xlsx_file: Path, audit_db: Audit):
    reader = OpenXMLSheetReader(test_xlsx_file)
    grid = reader.read_sheet("team_tasks")
    quotas = parse_team_tasks_sheet(grid, audit=audit_db)

    assert len(quotas) == 2
    q1 = quotas[0]
    assert q1["task_id"] == "TASK-1"
    assert q1["assigned_team"] == "Team 1"
    assert q1["task_name"] == "Gather RRL"
    assert q1["current_count"] == 10.0
    assert q1["target_count"] == 25.0
    assert q1["progress_pct"] == 40.0
    assert q1["days_since_update"] >= 3.0
    assert q1["stale"] is True

    q2 = quotas[1]
    assert q2["task_id"] == "TASK-2"
    assert q2["current_count"] == 20.0
    assert q2["target_count"] == 20.0
    assert q2["progress_pct"] == 100.0
    assert q2["stale"] is False


# ==============================================================================
# Gate 2: SQLite State & Stale Detection
# ==============================================================================

def test_sqlite_audit_team_task_state_sync(audit_db: Audit):
    now = int(time.time())
    stale_ts = now - (4 * 86400) # 4 days ago

    # Sync initial state
    res = audit_db.sync_team_task_state(
        task_id="TASK-RRL",
        assigned_team="Team 1",
        owner_email="t1@example.com",
        task_name="Gather RRL",
        current_count=10,
        target_count=25,
        last_updated=stale_ts,
        now_ts=now,
    )
    assert res["stale"] is True
    assert res["progress_pct"] == 40.0
    assert res["days_since_update"] >= 3.9

    # Re-fetch from DB
    stored = audit_db.get_team_task_state("TASK-RRL", now_ts=now)
    assert stored is not None
    assert stored["stale"] is True
    assert stored["current_count"] == 10.0

    # Snooze for 24 hours
    audit_db.update_team_task_notified("TASK-RRL", notified_ts=now)
    stored_snoozed = audit_db.get_team_task_state("TASK-RRL", now_ts=now)
    assert stored_snoozed["snoozed"] is True

    # Advance 25 hours -> snooze expired
    stored_after_snooze = audit_db.get_team_task_state("TASK-RRL", now_ts=now + (25 * 3600))
    assert stored_after_snooze["snoozed"] is False

    # Update progress to completed 25 of 25
    res_done = audit_db.sync_team_task_state(
        task_id="TASK-RRL",
        assigned_team="Team 1",
        owner_email="t1@example.com",
        task_name="Gather RRL",
        current_count=25,
        target_count=25,
        last_updated=now,
        now_ts=now,
    )
    assert res_done["stale"] is False
    assert res_done["progress_pct"] == 100.0


# ==============================================================================
# Gate 3: Pending Action, Clearance Guard & SMTP Email Confirmation
# ==============================================================================

def test_stale_task_workflow_and_smtp_confirmation(tmp_path: Path, audit_db: Audit):
    async def _run():
        fixture_bytes = generate_nexenroll_test_fixture(days_ago=4.0)
        xlsx_file = tmp_path / "NexEnroll_Development_Timeline.xlsx"
        xlsx_file.write_bytes(fixture_bytes)

        settings = Settings(
            desktop_root=tmp_path,
            api_token="test_token_1234567890abcdef",
            team_excel_path=xlsx_file,
            smtp_host="smtp.gmail.com",
            smtp_port=587,
            smtp_user="nightmare@example.com",
            smtp_app_password="secret_password",
        )
        registry = Registry({})
        clearance = ClearanceManager()

        from backend.core.llm import NoLLMProvider
        orch = Orchestrator(
            settings=settings,
            provider=NoLLMProvider(),
            registry=registry,
            audit=audit_db,
            clearance=clearance,
        )

        # 1. Ask to show team progress
        with patch("smtplib.SMTP") as mock_smtp:
            reply = await orch.handle("show team progress", session="default")

            # Verify SMTP was NOT called
            mock_smtp.assert_not_called()

            assert reply.ok is True
            assert reply.ui == "team_progress"
            assert reply.needs_confirm is True
            assert reply.pending_id is not None
            assert "Team 1" in reply.text
            assert "10 of 25" in reply.text
            assert "40.0%" in reply.text

            # Verify pending action exists
            pending_plan = orch.pending._items.get(reply.pending_id)[1]
            assert pending_plan.kind == "send_team_nudge"
            assert pending_plan.extra["owner_email"] == "team1.lead@example.com"
            assert pending_plan.extra["task_name"] == "Gather RRL"

        # 2. Test DECLINE workflow
        with patch("smtplib.SMTP") as mock_smtp:
            dec_reply = await orch.confirm(reply.pending_id, approve=False, session="default")
            mock_smtp.assert_not_called()
            assert dec_reply.ok is True
            assert "snoozed for 24 hours" in dec_reply.text

            # Verify snooze in DB
            state = audit_db.get_team_task_state("TASK-1")
            assert state["snoozed"] is True

        # 3. Test APPROVE (Sends email)
        # Reset snooze for test
        audit_db.update_team_task_notified("TASK-1", notified_ts=0)
        # Generate a fresh pending action
        rescan = await orch.handle("show team progress", session="default")
        assert rescan.needs_confirm is True
        pid2 = rescan.pending_id

        with patch("smtplib.SMTP") as mock_smtp_cls:
            mock_server = MagicMock()
            mock_smtp_cls.return_value.__enter__.return_value = mock_server

            appr_reply = await orch.confirm(pid2, approve=True, session="default")

            # Verify SMTP was called
            mock_smtp_cls.assert_called_once_with("smtp.gmail.com", 587, timeout=10)
            mock_server.starttls.assert_called_once()
            mock_server.login.assert_called_once_with("nightmare@example.com", "secret_password")
            mock_server.send_message.assert_called_once()

            sent_msg = mock_server.send_message.call_args[0][0]
            assert sent_msg["To"] == "team1.lead@example.com"
            assert "Gather RRL" in sent_msg["Subject"]
            assert "10 / 25 (40.0% completed)" in sent_msg.get_content()

            assert appr_reply.ok is True
            assert "Reminder email successfully sent" in appr_reply.text

    asyncio.run(_run())


# ==============================================================================
# Gate 4: Router Phrasing & Voice Approvals
# ==============================================================================

def test_router_phrases():
    settings = Settings(desktop_root=Path("."), api_token="1234567890123456")
    registry = Registry({})

    # Team progress
    i1 = route("show team progress", settings, registry)
    assert i1.kind == "team_progress"

    i2 = route("open timeline tracker", settings, registry)
    assert i2.kind == "team_progress"

    i3 = route("check team 1 progress", settings, registry)
    assert i3.kind == "team_progress"
    assert "team 1" in i3.query.lower()

    i4 = route("timeline tracker", settings, registry)
    assert i4.kind == "team_progress"

    # Approve email
    i5 = route("approve email", settings, registry)
    assert i5.kind == "approve_email"

    i6 = route("send reminder email", settings, registry)
    assert i6.kind == "approve_email"


def test_voice_approve_email_intent(tmp_path: Path, audit_db: Audit):
    async def _run():
        fixture_bytes = generate_nexenroll_test_fixture(days_ago=4.0)
        xlsx_file = tmp_path / "NexEnroll_Development_Timeline.xlsx"
        xlsx_file.write_bytes(fixture_bytes)

        settings = Settings(
            desktop_root=tmp_path,
            api_token="test_token_1234567890abcdef",
            team_excel_path=xlsx_file,
        )
        clearance = ClearanceManager()

        from backend.core.llm import NoLLMProvider
        orch = Orchestrator(
            settings=settings,
            provider=NoLLMProvider(),
            registry=Registry({}),
            audit=audit_db,
            clearance=clearance,
        )

        # 1. First trigger team progress to stage the pending email
        await orch.handle("show team progress", session="default")
        assert any(p.kind == "send_team_nudge" for _, p in orch.pending._items.values())

        # 2. User says "approve email"
        with patch("smtplib.SMTP") as mock_smtp_cls:
            mock_server = MagicMock()
            mock_smtp_cls.return_value.__enter__.return_value = mock_server

            reply = await orch.handle("approve email", session="default")
            assert reply.ok is True
            assert "Reminder email successfully sent" in reply.text
            mock_server.send_message.assert_called_once()

    asyncio.run(_run())


# ==============================================================================
# Phase 8D-2: CitizenGraph 4-Tab Timeline & Diff Engine Tests
# ==============================================================================

def _idx_to_col(i: int) -> str:
    res = ""
    while i > 0:
        i, rem = divmod(i - 1, 26)
        res = chr(65 + rem) + res
    return res


def generate_citizengraph_v2_test_fixture(
    wbs_status_overrides: dict[str, str] | None = None,
    roadmap_status_overrides: dict[str, str] | None = None,
    obj_status_overrides: dict[str, str] | None = None,
) -> bytes:
    wbs_overrides = wbs_status_overrides or {}
    rdm_overrides = roadmap_status_overrides or {}
    obj_overrides = obj_status_overrides or {}

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        types_el = ET.Element("Types", {"xmlns": "http://schemas.openxmlformats.org/package/2006/content-types"})
        ET.SubElement(types_el, "Default", {"Extension": "rels", "ContentType": "application/vnd.openxmlformats-package.relationships+xml"})
        ET.SubElement(types_el, "Default", {"Extension": "xml", "ContentType": "application/xml"})
        ET.SubElement(types_el, "Override", {"PartName": "/xl/workbook.xml", "ContentType": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"})
        ET.SubElement(types_el, "Override", {"PartName": "/xl/worksheets/sheet1.xml", "ContentType": "application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"})
        ET.SubElement(types_el, "Override", {"PartName": "/xl/worksheets/sheet2.xml", "ContentType": "application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"})
        ET.SubElement(types_el, "Override", {"PartName": "/xl/worksheets/sheet3.xml", "ContentType": "application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"})
        ET.SubElement(types_el, "Override", {"PartName": "/xl/worksheets/sheet4.xml", "ContentType": "application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"})
        ET.SubElement(types_el, "Override", {"PartName": "/xl/styles.xml", "ContentType": "application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"})
        z.writestr("[Content_Types].xml", ET.tostring(types_el, encoding="utf-8", xml_declaration=True))

        rels_el = ET.Element("Relationships", {"xmlns": "http://schemas.openxmlformats.org/package/2006/relationships"})
        ET.SubElement(rels_el, "Relationship", {"Id": "rId1", "Type": "http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument", "Target": "xl/workbook.xml"})
        z.writestr("_rels/.rels", ET.tostring(rels_el, encoding="utf-8", xml_declaration=True))

        wb_rels_el = ET.Element("Relationships", {"xmlns": "http://schemas.openxmlformats.org/package/2006/relationships"})
        ET.SubElement(wb_rels_el, "Relationship", {"Id": "rId1", "Type": "http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet", "Target": "worksheets/sheet1.xml"})
        ET.SubElement(wb_rels_el, "Relationship", {"Id": "rId2", "Type": "http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet", "Target": "worksheets/sheet2.xml"})
        ET.SubElement(wb_rels_el, "Relationship", {"Id": "rId3", "Type": "http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet", "Target": "worksheets/sheet3.xml"})
        ET.SubElement(wb_rels_el, "Relationship", {"Id": "rId4", "Type": "http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet", "Target": "worksheets/sheet4.xml"})
        ET.SubElement(wb_rels_el, "Relationship", {"Id": "rId5", "Type": "http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles", "Target": "styles.xml"})
        z.writestr("xl/_rels/workbook.xml.rels", ET.tostring(wb_rels_el, encoding="utf-8", xml_declaration=True))

        wb_el = ET.Element("workbook", {
            "xmlns": "http://schemas.openxmlformats.org/spreadsheetml/2006/main",
            "xmlns:r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
        })
        sheets_el = ET.SubElement(wb_el, "sheets")
        ET.SubElement(sheets_el, "sheet", {"name": "General 8-Month Roadmap", "sheetId": "1", "r:id": "rId1"})
        ET.SubElement(sheets_el, "sheet", {"name": "Detailed Weekly Gantt", "sheetId": "2", "r:id": "rId2"})
        ET.SubElement(sheets_el, "sheet", {"name": "Objectives & KPI Alignment", "sheetId": "3", "r:id": "rId3"})
        ET.SubElement(sheets_el, "sheet", {"name": "Phase Summary & Dashboard", "sheetId": "4", "r:id": "rId4"})
        z.writestr("xl/workbook.xml", ET.tostring(wb_el, encoding="utf-8", xml_declaration=True))

        styles_el = ET.Element("styleSheet", {"xmlns": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"})
        fills_el = ET.SubElement(styles_el, "fills", {"count": "6"})
        f0 = ET.SubElement(fills_el, "fill"); ET.SubElement(f0, "patternFill", {"patternType": "none"})
        f1 = ET.SubElement(fills_el, "fill"); ET.SubElement(f1, "patternFill", {"patternType": "gray125"})
        f2 = ET.SubElement(fills_el, "fill"); p2 = ET.SubElement(f2, "patternFill", {"patternType": "solid"}); ET.SubElement(p2, "fgColor", {"rgb": f"FF{COLOR_PHASE1_HEX}"})
        f3 = ET.SubElement(fills_el, "fill"); p3 = ET.SubElement(f3, "patternFill", {"patternType": "solid"}); ET.SubElement(p3, "fgColor", {"rgb": f"FF{COLOR_PHASE2_HEX}"})
        f4 = ET.SubElement(fills_el, "fill"); p4 = ET.SubElement(f4, "patternFill", {"patternType": "solid"}); ET.SubElement(p4, "fgColor", {"rgb": f"FF{COLOR_INDIGO_HEX}"})
        f5 = ET.SubElement(fills_el, "fill"); p5 = ET.SubElement(f5, "patternFill", {"patternType": "solid"}); ET.SubElement(p5, "fgColor", {"rgb": f"FF{COLOR_MILESTONE_HEX}"})

        cell_xfs_el = ET.SubElement(styles_el, "cellXfs", {"count": "5"})
        ET.SubElement(cell_xfs_el, "xf", {"numFmtId": "0", "fontId": "0", "fillId": "0", "borderId": "0", "xfId": "0"})
        ET.SubElement(cell_xfs_el, "xf", {"numFmtId": "0", "fontId": "0", "fillId": "2", "borderId": "0", "xfId": "0", "applyFill": "1"})
        ET.SubElement(cell_xfs_el, "xf", {"numFmtId": "0", "fontId": "0", "fillId": "3", "borderId": "0", "xfId": "0", "applyFill": "1"})
        ET.SubElement(cell_xfs_el, "xf", {"numFmtId": "0", "fontId": "0", "fillId": "4", "borderId": "0", "xfId": "0", "applyFill": "1"})
        ET.SubElement(cell_xfs_el, "xf", {"numFmtId": "0", "fontId": "0", "fillId": "5", "borderId": "0", "xfId": "0", "applyFill": "1"})
        z.writestr("xl/styles.xml", ET.tostring(styles_el, encoding="utf-8", xml_declaration=True))

        def _make_ws(data_rows: dict[int, list[tuple[int, str, int | None]]]) -> bytes:
            ws_el = ET.Element("worksheet", {"xmlns": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"})
            sd_el = ET.SubElement(ws_el, "sheetData")
            for r_num in sorted(data_rows.keys()):
                r_el = ET.SubElement(sd_el, "row", {"r": str(r_num)})
                for col_idx, text_val, s_idx in data_rows[r_num]:
                    col_code = _idx_to_col(col_idx)
                    attrib = {"r": f"{col_code}{r_num}", "t": "inlineStr"}
                    if s_idx is not None:
                        attrib["s"] = str(s_idx)
                    c_el = ET.SubElement(r_el, "c", attrib)
                    is_el = ET.SubElement(c_el, "is")
                    t_el = ET.SubElement(is_el, "t")
                    t_el.text = text_val
            return ET.tostring(ws_el, encoding="utf-8", xml_declaration=True)

        # Sheet 1: General 8-Month Roadmap (Rows 4-13)
        s1_rows: dict[int, list[tuple[int, str, int | None]]] = {}
        s1_rows[4] = [
            (1, "Stage ID", None), (2, "Timeline Stage", None), (3, "Calendar Span", None),
            (4, "Thesis Phase", None), (5, "General Stage Title", None),
            (6, "Citizen Graph Aligned Activities & Core Focus", None),
            (7, "Major Milestone / Output", None), (8, "Status", None),
            (9, "M1 Aug '26", None), (10, "M2 Sept '26", None), (11, "M3 Oct '26", None),
            (12, "M4 Nov '26", None), (13, "M5 Dec '26", None), (14, "M6 Jan '27", None),
            (15, "M7 Feb '27", None), (16, "M8 Mar '27", None),
        ]
        roadmap_stages = [
            ("STG-01", "Month 1", "Aug '26", "Phase 1", "Problem Formulation & Literature Review", "Review related literature & formulate CitizenGraph DAG ontology", "Comprehensive RRL Document", "Completed", 1),
            ("STG-02", "Month 2", "Sept '26", "Phase 1", "Knowledge Graph Modeling & Ontology", "Design Neo4j DAG ontology for citizen procedures", "Validated Neo4j Schema Spec", "Completed", 2),
            ("STG-03", "Month 3", "Oct '26", "Phase 1", "QLoRA Dataset Preparation & Tuning", "Format instruction tuning pairs and train Llama-3-8B adapter", "QLoRA Checkpoint V1", "In Progress", 3),
            ("STG-04", "Month 4", "Nov '26", "Phase 1", "AST Guardrail & Sandbox Construction", "Build AST validator to enforce procedural DAG schema constraints", "AST Node Visitor Guardrail Suite", "Pending", 4),
            ("STG-05", "Month 5", "Dec '26", "Phase 1", "System Integration & Phase 1 Defense", "End-to-end integration and defense of Chapters 1 to 3", "Approved Chapters 1-3 Proposal", "Pending", 5),
            ("STG-06", "Month 6", "Jan '27", "Phase 2", "Empirical Evaluation & Benchmark Testing", "Run return-trip prevention and latency benchmarks on Calbayog dataset", "Benchmark Results Dataset", "Pending", 6),
            ("STG-07", "Month 7", "Feb '27", "Phase 2", "User Acceptance & Citizen Trial", "Collect LGU officer and citizen satisfaction feedback", "Usability Analysis Report", "Pending", 7),
            ("STG-08", "Month 8", "Mar '27", "Phase 2", "Thesis Manuscript Final Polish", "Complete Chapters 4 to 6 discussion and final manuscript", "Final Thesis Manuscript", "Pending", 8),
            ("STG-09", "Months 7-8", "Mar '27", "Phase 2", "Oral Defense & System Handover", "Final thesis defense and open-source release", "Thesis Defense Approval", "Pending", 8),
        ]
        for idx, (stg_id, stg_name, span, phase, title, act, deliv, default_stat, active_m) in enumerate(roadmap_stages, 5):
            st = rdm_overrides.get(stg_id, default_stat)
            row = [
                (1, stg_id, None), (2, stg_name, None), (3, span, None),
                (4, phase, None), (5, title, None), (6, act, None),
                (7, deliv, None), (8, st, None),
            ]
            for m in range(1, 9):
                is_active = (m == active_m)
                row.append((8 + m, "●" if is_active else "", 1 if is_active else None))
            s1_rows[idx] = row

        z.writestr("xl/worksheets/sheet1.xml", _make_ws(s1_rows))

        # Sheet 2: Detailed Weekly Gantt (Rows 5-26)
        s2_rows: dict[int, list[tuple[int, str, int | None]]] = {}
        s2_header = [
            (1, "WBS ID", None), (2, "Phase / Stage", None),
            (3, "Task / Activity Description", None),
            (4, "Aligned Thesis Section / System Module", None),
            (5, "Key Deliverable / Target Metric", None),
            (6, "Period", None), (7, "Status", None),
        ]
        std_weeks = [
            "S-W1", "S-W2", "S-W3", "S-W4", "O-W1", "O-W2", "O-W3", "O-W4",
            "N-W1", "N-W2", "N-W3", "N-W4", "D-W1", "D-W2", "D-W3", "D-W4",
            "J-W1", "J-W2", "J-W3", "J-W4", "F-W1", "F-W2", "F-W3", "F-W4",
        ]
        for w_idx, w_code in enumerate(std_weeks, 8):
            s2_header.append((w_idx, w_code, None))
        s2_rows[5] = s2_header

        wbs_tasks_def = [
            ("1.1", "Phase 1: Chapters 1-3 & Core Dev", "Domain Ontology Definition", "Chapter 3 / Neo4j Graph DB", "Draft Ontology Spec", "Sept W1 - Sept W2", "Completed", [1, 2]),
            ("1.2", "Phase 1: Chapters 1-3 & Core Dev", "Citizen Charter Ingestion & Pipeline", "Chapter 3 / Data Pipeline", "Cleaned JSONL Corpus", "Sept W2 - Sept W3", "Completed", [2, 3]),
            ("1.3", "Phase 1: Chapters 1-3 & Core Dev", "Neo4j Graph Schema Setup", "Chapter 3 / Knowledge Graph", "Verified Neo4j Constraints", "Sept W3 - Sept W4", "Completed", [3, 4]),
            ("1.4", "Phase 1: Chapters 1-3 & Core Dev", "Prerequisite Walk Algorithm Design", "Chapter 3 / Graph Walk Engine", "Core Graph Traversal Logic", "Sept W4 - Oct W1", "Completed", [4, 5]),
            ("1.5", "Phase 1: Chapters 1-3 & Core Dev", "Review of Related Literature", "Chapter 2 / State of the Art", "Comprehensive RRL Document", "Oct W1 - Oct W3", "In Progress", [5, 6, 7]),
            ("1.6", "Phase 1: Chapters 1-3 & Core Dev", "QLoRA Instruction Dataset Curation", "Chapter 3 / Training Corpus", "5,000 Curated Tuning Pairs", "Oct W2 - Oct W4", "In Progress", [6, 7, 8]),
            ("1.7", "Phase 1: Chapters 1-3 & Core Dev", "Llama-3-8B QLoRA Fine-Tuning", "Chapter 3 / Model Weights", "QLoRA Adapter Weights", "Oct W3 - Nov W1", "Pending", [7, 8, 9]),
            ("1.8", "Phase 1: Chapters 1-3 & Core Dev", "Python AST Guardrail", "Chapter 3 / AST Validator", "AST Node Visitor Suite", "Nov W1 - Nov W3", "Pending", [9, 10, 11]),
            ("1.9", "Phase 1: Chapters 1-3 & Core Dev", "Topological Sort Engine", "Chapter 3 / DAG Topological Engine", "M = R \\ H Topological Sorter", "Nov W2 - Nov W4", "Pending", [10, 11, 12]),
            ("1.10", "Phase 1: Chapters 1-3 & Core Dev", "Gap Analysis Implementation", "Chapter 3 / Difference Engine", "Set-Theoretic Gap Analyzer", "Nov W3 - Dec W1", "Pending", [11, 12, 13]),
            ("1.11", "Phase 1: Chapters 1-3 & Core Dev", "Integration Testing & Bug Fixing", "System Integration", "Passing Test Suite", "Dec W1 - Dec W2", "Pending", [13, 14]),
            ("1.12", "Phase 1: Chapters 1-3 & Core Dev", "Proposal Manuscript Chapters 1-3", "Chapters 1-3", "Final Proposal Draft", "Dec W2", "Pending", [14]),
            ("2.1", "Phase 2: Evaluation & Chapters 4-6", "Benchmark Dataset Assembly", "Chapter 4 / Benchmark Corpus", "200 Verified Test Scenarios", "Dec W3 - Dec W4", "Pending", [15, 16]),
            ("2.2", "Phase 2: Evaluation & Chapters 4-6", "Exact-Match Metric Testing", "Chapter 4 / Metrics Engine", "Precision & Recall Metrics", "Dec W4 - Jan W1", "Pending", [16, 17]),
            ("2.3", "Phase 2: Evaluation & Chapters 4-6", "Return-Trip Prevention Evaluation", "Chapter 4 / Efficiency Analysis", "Prevention Rate >= 90%", "Jan W1 - Jan W2", "Pending", [17, 18]),
            ("2.4", "Phase 2: Evaluation & Chapters 4-6", "Latency & Throughput Benchmark", "Chapter 4 / Performance", "Edge Latency <= 5.0s", "Jan W2 - Jan W3", "Pending", [18, 19]),
            ("2.5", "Phase 2: Evaluation & Chapters 4-6", "User Acceptance Testing (UAT)", "Chapter 4 / Usability", "LGU Officer Survey Results", "Jan W3 - Jan W4", "Pending", [19, 20]),
            ("2.6", "Phase 2: Evaluation & Chapters 4-6", "Chapter 4 Results Analysis", "Chapter 4", "Draft Chapter 4 Results", "Feb W1 - Feb W2", "Pending", [21, 22]),
            ("2.7", "Phase 2: Evaluation & Chapters 4-6", "Chapter 5 Discussion & Conclusion", "Chapter 5", "Draft Chapter 5 Discussion", "Feb W2 - Feb W3", "Pending", [22, 23]),
            ("2.8", "Phase 2: Evaluation & Chapters 4-6", "Thesis Final Manuscript Polish", "Complete Thesis", "Defensible Thesis Draft", "Feb W3 - Feb W4", "Pending", [23, 24]),
            ("2.9", "Phase 2: Evaluation & Chapters 4-6", "Oral Defense Preparation", "Final Defense", "Approved Defense Slide Deck", "Feb W4", "Pending", [24]),
        ]

        for r_offset, (w_id, ph, desc, mod, deliv, per, def_st, act_weeks) in enumerate(wbs_tasks_def, 6):
            st = wbs_overrides.get(w_id, def_st)
            row = [
                (1, w_id, None), (2, ph, None), (3, desc, None),
                (4, mod, None), (5, deliv, None), (6, per, None),
                (7, st, None),
            ]
            for w in range(1, 25):
                is_active = (w in act_weeks)
                row.append((7 + w, "●" if is_active else "", 1 if is_active else None))
            s2_rows[r_offset] = row

        z.writestr("xl/worksheets/sheet2.xml", _make_ws(s2_rows))

        # Sheet 3: Objectives & KPI Alignment (Rows 4-11)
        s3_rows: dict[int, list[tuple[int, str, int | None]]] = {}
        s3_rows[4] = [
            (1, "Obj ID", None), (2, "Chapter 1 Specific Objective Statement", None),
            (3, "Core Architectural Component", None), (4, "Target Evaluation Dataset / Scope", None),
            (5, "Target Benchmark / KPI", None), (6, "Primary Phase", None),
            (7, "Scheduled Window", None), (8, "Current Status", None),
        ]
        objectives_def = [
            ("SO-1", "Design domain ontology for citizen charters", "Neo4j DAG", "Calbayog City LGU Citizen Charters", "Ontology Coverage >= 95%", "Phase 1", "Sept - Oct 2026", "Completed"),
            ("SO-2", "Develop AST-guided Llama-3-8B semantic query engine", "Llama-3-8B QLoRA + AST Guardrail", "Synthetic & Real Citizen Requests", "Accuracy >= 95%", "Phase 1", "Oct - Nov 2026", "In Progress"),
            ("SO-3", "Formulate topological gap analysis algorithm M = R \\ H", "M = R \\ H Topological Engine", "Procedural Dependency Subgraphs", "Gap Analysis Precision >= 90%", "Phase 1", "Nov - Dec 2026", "Pending"),
            ("SO-4", "Evaluate return-trip prevention rate", "Neo4j Prerequisite Walk", "LGU Municipal Transactions", "Return-Trip Prevention >= 90%", "Phase 2", "Dec 2026 - Jan 2027", "Pending"),
            ("SO-5", "Benchmark exact-match citizen resolution", "Topological Graph Engine", "Standard Benchmark Scenarios", "Exact-Match Accuracy >= 95%", "Phase 2", "Jan 2027", "Pending"),
            ("SO-6", "Validate execution sequence against AST constraints", "Python AST Node Visitor", "AST Execution Traces", "Post-AST Execution >= 95%", "Phase 2", "Jan - Feb 2027", "Pending"),
            ("SO-7", "Assess edge query latency and response time", "Local Neo4j Graph DB", "Local Host Edge Server", "Edge Latency <= 5.0s", "Phase 2", "Feb 2027", "Pending"),
        ]
        for r_offset, (obj_id, stmt, comp, scope, kpi, ph, win, def_st) in enumerate(objectives_def, 5):
            st = obj_overrides.get(obj_id, def_st)
            s3_rows[r_offset] = [
                (1, obj_id, None), (2, stmt, None), (3, comp, None),
                (4, scope, None), (5, kpi, None), (6, ph, None),
                (7, win, None), (8, st, None),
            ]
        z.writestr("xl/worksheets/sheet3.xml", _make_ws(s3_rows))

        # Sheet 4: Phase Summary & Dashboard (Placeholder)
        s4_rows: dict[int, list[tuple[int, str, int | None]]] = {}
        s4_rows[1] = [(1, "CITIZEN GRAPH THESIS TIMELINE DASHBOARD", None)]
        z.writestr("xl/worksheets/sheet4.xml", _make_ws(s4_rows))

    return buf.getvalue()


def test_parse_citizengraph_v2_sheets(tmp_path: Path, audit_db: Audit):
    """Verifies OpenXML parsing of all 4 tabs of CitizenGraph_Thesis_Timeline_2026_2027-v2.xlsx."""
    fixture_bytes = generate_citizengraph_v2_test_fixture()
    xlsx_file = tmp_path / "CitizenGraph_Thesis_Timeline_2026_2027-v2.xlsx"
    xlsx_file.write_bytes(fixture_bytes)

    settings = Settings(
        desktop_root=tmp_path,
        api_token="test_token_1234567890abcdef",
        team_excel_path=xlsx_file,
    )

    scan = scan_team_progress(settings=settings, audit=audit_db, excel_path=xlsx_file)
    assert scan["ok"] is True

    # 1. Tab 1: General 8-Month Roadmap (9 stages)
    roadmap = scan["roadmap"]
    assert len(roadmap) == 9
    assert roadmap[0]["stage_id"] == "STG-01"
    assert roadmap[0]["title"] == "Problem Formulation & Literature Review"
    assert roadmap[0]["status"] == "Completed"
    assert roadmap[8]["stage_id"] == "STG-09"
    assert len(roadmap[0]["months"]) == 8

    # 2. Tab 2: Detailed Weekly Gantt (21 tasks)
    wbs = scan["wbs"]
    assert len(wbs) == 21
    p1_tasks = [t for t in wbs if t["wbs_id"].startswith("1.")]
    p2_tasks = [t for t in wbs if t["wbs_id"].startswith("2.")]
    assert len(p1_tasks) == 12
    assert len(p2_tasks) == 9
    assert wbs[0]["wbs_id"] == "1.1"
    assert wbs[0]["status"] == "Completed"
    assert len(wbs[0]["weeks"]) == 24
    assert wbs[4]["wbs_id"] == "1.5"
    assert wbs[4]["status"] == "In Progress"

    # 3. Tab 3: Objectives & KPI Alignment (7 objectives)
    objectives = scan["objectives"]
    assert len(objectives) == 7
    assert objectives[0]["obj_id"] == "SO-1"
    assert objectives[0]["status"] == "Completed"
    assert objectives[6]["obj_id"] == "SO-7"
    assert "Edge Latency <= 5.0s" in objectives[6]["target_kpi"]

    # 4. Tab 4: Phase Summary & Dashboard (Calculated live in Python)
    dash = scan["dashboard"]
    assert dash["roadmap"]["total"] == 9
    assert dash["phase_1"]["total"] == 12
    assert dash["phase_1"]["completed"] == 4
    assert dash["phase_1"]["in_progress"] == 2
    assert dash["phase_1"]["pending"] == 6
    assert dash["phase_1"]["completion_pct"] == round((4 / 12) * 100, 1)

    assert dash["phase_2"]["total"] == 9
    assert dash["phase_2"]["completed"] == 0
    assert dash["phase_2"]["pending"] == 9
    assert dash["phase_2"]["completion_pct"] == 0.0

    assert dash["overall_wbs"]["total"] == 21
    assert len(dash["quantitative_targets"]) == 6


def test_timeline_diff_engine_and_spoken_summary(tmp_path: Path, audit_db: Audit):
    """Verifies baseline snapshot comparison, diff detection, and deterministic spoken summary."""
    # Step 1: Initial baseline scan
    fixture_v1 = generate_citizengraph_v2_test_fixture()
    xlsx_file = tmp_path / "CitizenGraph_Thesis_Timeline_2026_2027-v2.xlsx"
    xlsx_file.write_bytes(fixture_v1)

    settings = Settings(
        desktop_root=tmp_path,
        api_token="test_token_1234567890abcdef",
        team_excel_path=xlsx_file,
    )

    scan_v1 = scan_team_progress(settings=settings, audit=audit_db, excel_path=xlsx_file)
    assert scan_v1["diff"]["has_changes"] is False
    assert scan_v1["diff"]["change_count"] == 0
    assert "Timeline is up to date with 0 changes detected" in scan_v1["diff"]["spoken_summary"]

    # Step 2: Update file on disk (1.5 In Progress -> Completed, SO-2 In Progress -> Completed)
    fixture_v2 = generate_citizengraph_v2_test_fixture(
        wbs_status_overrides={"1.5": "Completed"},
        obj_status_overrides={"SO-2": "Completed"},
    )
    xlsx_file.write_bytes(fixture_v2)

    scan_v2 = scan_team_progress(settings=settings, audit=audit_db, excel_path=xlsx_file)
    diff = scan_v2["diff"]
    assert diff["has_changes"] is True
    assert diff["change_count"] == 2

    trans_keys = [t["item_key"] for t in diff["status_transitions"]]
    assert "1.5" in trans_keys
    assert "SO-2" in trans_keys

    spoken = diff["spoken_summary"]
    assert "Cross-referencing the CitizenGraph timeline against the baseline." in spoken
    assert "2 items changed" in spoken
    assert "1.5" in spoken
    assert "In Progress to Completed" in spoken
    assert "Opening the Timeline Diff tab." in spoken


def test_timeline_diff_router_and_clearance(tmp_path: Path, audit_db: Audit):
    """Verifies intent routing and strict Level 5 clearance enforcement."""
    async def _run():
        fixture_bytes = generate_citizengraph_v2_test_fixture()
        xlsx_file = tmp_path / "CitizenGraph_Thesis_Timeline_2026_2027-v2.xlsx"
        xlsx_file.write_bytes(fixture_bytes)

        settings = Settings(
            desktop_root=tmp_path,
            api_token="test_token_1234567890abcdef",
            team_excel_path=xlsx_file,
        )
        registry = Registry({})

        # 1. Routing Checks
        phrases = [
            "nightmare what change in the citizengraph timeline from the gdrive",
            "what changed in the citizengraph timeline",
            "compare citizengraph timeline with gdrive",
            "check gdrive timeline updates",
            "what did my team update in the timeline",
        ]
        for p in phrases:
            it = route(p, settings, registry)
            assert it.kind == "timeline_diff", f"Failed to route '{p}' to timeline_diff"

        it_progress = route("citizengraph timeline", settings, registry)
        assert it_progress.kind == "team_progress"

        it_progress2 = route("/timeline", settings, registry)
        assert it_progress2.kind == "team_progress"

        # 2. Remote / Readonly Session Blocked
        clearance = ClearanceManager()
        from backend.core.llm import NoLLMProvider
        orch = Orchestrator(
            settings=settings,
            provider=NoLLMProvider(),
            registry=registry,
            audit=audit_db,
            clearance=clearance,
        )

        rep_remote = await orch.handle("what changed in the citizengraph timeline", session="user_ro", readonly=True)
        assert rep_remote.ok is True
        assert rep_remote.ui == "team_progress:diff"

        # 3. Local Level 5 Session Allowed
        rep_l5 = await orch.handle("what changed in the citizengraph timeline", session="user_l5")
        assert rep_l5.ok is True
        assert rep_l5.ui == "team_progress:diff"
        assert "Cross-referencing the CitizenGraph timeline against the baseline." in rep_l5.text

    asyncio.run(_run())


def test_api_endpoints_team_tracker(tmp_path: Path):
    """Verifies Level 5 clearance enforcement on team-tracker REST API endpoints."""
    from fastapi.testclient import TestClient
    from backend.main import create_app
    from backend.core.llm import NoLLMProvider

    fixture_bytes = generate_citizengraph_v2_test_fixture()
    xlsx_file = tmp_path / "CitizenGraph_Thesis_Timeline_2026_2027-v2.xlsx"
    xlsx_file.write_bytes(fixture_bytes)

    token = "test_token_1234567890abcdef"
    settings = Settings(
        desktop_root=tmp_path,
        api_token=token,
        db_path=tmp_path / "test.db",
        team_excel_path=xlsx_file,
    )
    app = create_app(settings, NoLLMProvider())
    c = TestClient(app, base_url="http://127.0.0.1:8000")
    headers = {"X-Nightmare-Token": token}
    remote_headers = {"X-Nightmare-Token": token, "X-Forwarded-For": "100.64.0.99"}

    # 1. Remote Session -> mutation endpoints block with 403
    r_sync = c.post("/api/team-tracker/sync", headers=remote_headers)
    assert r_sync.status_code == 403

    r_open = c.post("/api/team-tracker/open-excel", headers=remote_headers)
    assert r_open.status_code == 403

    # 2. Local Level 5 Session -> endpoints succeed
    r_diff_l5 = c.get("/api/team-tracker/diff", headers=headers)
    assert r_diff_l5.status_code == 200
    assert "has_changes" in r_diff_l5.json()

    r_sync_l5 = c.post("/api/team-tracker/sync", headers=headers)
    assert r_sync_l5.status_code == 200
    assert r_sync_l5.json()["ok"] is True
    assert r_sync_l5.json()["committed_count"] >= 9

    with patch("backend.tools.file_navigator.safe_open_file", return_value=(True, "Opened file")):
        r_open_l5 = c.post("/api/team-tracker/open-excel", headers=headers)
        assert r_open_l5.status_code == 200
        assert r_open_l5.json()["ok"] is True


def test_voice_intent_and_file_opening_fixes(tmp_path: Path):
    """Verifies fixes for open timeline in excel, wakeup/greet, model identity, usage quota and slide jump."""
    import asyncio
    from backend.core.orchestrator import Orchestrator
    from backend.core.router import route
    from backend.core.llm import NoLLMProvider
    from backend.core.clearance import ClearanceManager, LEVEL_5

    fixture_bytes = generate_citizengraph_v2_test_fixture()
    xlsx_file = tmp_path / "CitizenGraph_Thesis_Timeline_2026_2027-v2.xlsx"
    xlsx_file.write_bytes(fixture_bytes)

    audit = Audit(tmp_path / "audit.db")
    clearance = ClearanceManager()
    settings = Settings(
        desktop_root=tmp_path,
        api_token="test_token_1234567890abcdef",
        db_path=tmp_path / "audit.db",
        team_excel_path=xlsx_file,
    )
    orch = Orchestrator(
        settings=settings,
        provider=NoLLMProvider(),
        registry=Registry(),
        audit=audit,
        clearance=clearance,
    )

    # 1. Test "open citizengraph timeline in excel" intent routing & execution
    i_excel = route("open citizengraph timeline in excel", settings, Registry())
    assert i_excel.kind == "open_team_excel"

    i_excel2 = route("open citizengraph thesis timeline in excel", settings, Registry())
    assert i_excel2.kind == "open_team_excel"

    i_excel3 = route("open timeline in excel", settings, Registry())
    assert i_excel3.kind == "open_team_excel"

    # Execution requires Level 5
    rep_ro = asyncio.run(orch.handle("open citizengraph timeline in excel", session="test_sess", readonly=True))
    assert rep_ro.ok is False
    assert "read-only" in rep_ro.text.lower()

    with patch("backend.tools.file_navigator.safe_open_file", return_value=(True, "Opened file")):
        rep_l5 = asyncio.run(orch.handle("open citizengraph timeline in excel", session="test_sess"))
        assert rep_l5.ok is True
        assert "CitizenGraph_Thesis_Timeline_2026_2027-v2.xlsx" in rep_l5.text
        assert rep_l5.ui == "team_progress:excel"

    # 2. Test Wakeup / Greet Intent (must NEVER route to sleep)
    i_wake1 = route("wakeup", settings, Registry())
    assert i_wake1.kind == "quick_reply"
    assert i_wake1.note_text == "greet"

    i_wake2 = route("Wake up. Nightmare wake up.", settings, Registry())
    assert i_wake2.kind == "quick_reply"
    assert i_wake2.note_text == "greet"

    rep_wake = asyncio.run(orch.handle("wakeup", session="test_sess"))
    assert "awake" in rep_wake.text.lower()
    assert "sleep" not in rep_wake.text.lower()

    # 3. Test Model Identity Intent
    i_model = route("what model powers you", settings, Registry())
    assert i_model.kind == "quick_reply"
    assert i_model.note_text == "model_identity"

    i_model2 = route("who trained you", settings, Registry())
    assert i_model2.kind == "quick_reply"
    assert i_model2.note_text == "model_identity"

    rep_model = asyncio.run(orch.handle("what model powers you", session="test_sess"))
    assert "not powered by any model" in rep_model.text
    assert "trained by my developer" in rep_model.text

    # 4. Test Usage & Quota:
    # "how many calls today" -> matches usage, reply does NOT contain Google AI Pro quota sentence
    i_usage = route("how many calls today", settings, Registry())
    assert i_usage.kind == "usage"

    rep_usage = asyncio.run(orch.handle("how many calls today", session="test_sess"))
    assert "model calls" in rep_usage.text
    assert "Google AI Pro quota" not in rep_usage.text

    # "don't need to include this Google AI Pro quota" -> must NOT route to usage
    i_no_usage = route("don't need to include this Google AI Pro quota", settings, Registry())
    assert i_no_usage.kind != "usage"

    # 5. Test PowerPoint "go to next slide 11"
    i_ppt = route("go to next slide 11", settings, Registry())
    assert i_ppt.kind == "ppt_control"
    assert i_ppt.slide == 11


def test_remodeled_10col_objectives_and_summary_footer_filtering():
    """Verifies remodeled CitizenGraph_Thesis_Timeline_2026_2027.xlsx schema:
    - Tab 1 stops before '8-MONTH ROADMAP STATUS SUMMARY' and ignores summary rows.
    - Tab 1 classifies '■' and '◆' markers properly.
    - Tab 3 parses 10-column schema (GO-0 + SO-1..SO-7) without matching Row 2 subtitle.
    """
    from backend.tools.team_tracker import (
        extract_gdrive_file_id,
        parse_roadmap_sheet,
        parse_objectives_sheet,
    )

    # 1. Verify extract_gdrive_file_id
    sheet_url = "https://docs.google.com/spreadsheets/d/1Kw4_zboMzpv2WKdJHeNVuSYSfW4Gg_xm/edit?usp=drive_link&ouid=109543692766011182977&rtpof=true&sd=true"
    assert extract_gdrive_file_id(sheet_url) == "1Kw4_zboMzpv2WKdJHeNVuSYSfW4Gg_xm"
    assert extract_gdrive_file_id("https://drive.google.com/drive/folders/1P4CWnBnYfLkkGKnrAswe9lwX5HcCQYDg") is None

    # 2. Verify Tab 1 summary footer filtering & ■ / ◆ markers
    roadmap_grid = {
        (4, 1): {"value": "Stage ID"},
        (4, 2): {"value": "Timeline Stage"},
        (4, 3): {"value": "Calendar Span"},
        (4, 4): {"value": "Thesis Phase"},
        (4, 5): {"value": "General Stage Title"},
        (4, 6): {"value": "Citizen Graph Aligned Activities & Core Focus"},
        (4, 7): {"value": "Major Milestone / Output"},
        (4, 8): {"value": "Status"},
        (4, 9): {"value": "M1\nAug '26"},
        (4, 10): {"value": "M2\nSep '26"},
        (5, 1): {"value": "STG-01"},
        (5, 2): {"value": "Stage 1"},
        (5, 3): {"value": "Aug – Sep 2026"},
        (5, 4): {"value": "Phase 1"},
        (5, 5): {"value": "Topic Formulation & Adviser Alignment"},
        (5, 6): {"value": "Select research topic"},
        (5, 7): {"value": "Approved Topic"},
        (5, 8): {"value": "Completed"},
        (5, 9): {"value": "■", "fill_rgb": "0284C7"},
        (5, 10): {"value": "◆", "fill_rgb": "4F46E5"},
        (15, 1): {"value": "8-MONTH ROADMAP STATUS SUMMARY"},
        (16, 1): {"value": "Completed Stages"},
        (16, 2): {"value": "2"},
        (17, 1): {"value": "In Progress Stages"},
        (17, 2): {"value": "1"},
        (18, 1): {"value": "Pending Stages"},
        (18, 2): {"value": "6"},
    }
    stages = parse_roadmap_sheet(roadmap_grid)
    assert len(stages) == 1
    assert stages[0]["stage_id"] == "STG-01"
    assert stages[0]["months"][0]["active"] is True
    assert stages[0]["months"][0]["status"] == "core"
    assert stages[0]["months"][0]["color"] == "#0284C7"
    assert stages[0]["months"][1]["active"] is True
    assert stages[0]["months"][1]["status"] == "milestone"

    # 3. Verify Tab 3 10-column layout with Row 2 subtitle containing 'Objective' and 'Target'
    obj_grid = {
        (1, 1): {"value": "CITIZEN GRAPH: STUDY OBJECTIVES, TEAM GOALS & QUANTITATIVE KPI ALIGNMENT MATRIX"},
        (2, 1): {"value": "Direct Traceability from Chapter 1 Objectives → Team Action Plan → System Modules → Target Benchmarks"},
        (4, 1): {"value": "Obj ID"},
        (4, 2): {"value": "Task Filter / Type"},
        (4, 3): {"value": "Metric Category"},
        (4, 4): {"value": "Study Objective Statement (General & Specific)"},
        (4, 5): {"value": "Team Goal / Action Plan"},
        (4, 6): {"value": "Core Architectural Component"},
        (4, 7): {"value": "Target Evaluation Dataset / Scope"},
        (4, 8): {"value": "Quantitative Target Benchmark / KPI"},
        (4, 9): {"value": "Primary Phase & Window"},
        (4, 10): {"value": "Current Status"},
        (5, 1): {"value": "GO-0"},
        (5, 2): {"value": "General Objective"},
        (5, 3): {"value": "End-to-End System"},
        (5, 4): {"value": "Design, develop, and evaluate CitizenGraph."},
        (5, 5): {"value": "Deliver full 6-stage pipeline"},
        (5, 6): {"value": "Full 6-Stage CitizenGraph Architecture"},
        (5, 7): {"value": "Pasig City Public Complaint Corpus"},
        (5, 8): {"value": "End-to-End Pipeline Operational"},
        (5, 9): {"value": "Phase 1 & Phase 2\n(Aug 2026 – Mar 2027)"},
        (5, 10): {"value": "In Progress"},
        (6, 1): {"value": "SO-1"},
        (6, 2): {"value": "Data & Corpus"},
        (6, 3): {"value": "Data Quality"},
        (6, 4): {"value": "Construct and preprocess a multilingual complaint dataset."},
        (6, 5): {"value": "Collect, clean, and annotate complaints"},
        (6, 6): {"value": "Stage 1: Data Acquisition"},
        (6, 7): {"value": "Pasig City Complaints"},
        (6, 8): {"value": "Cohen's Kappa κ ≥ 0.80"},
        (6, 9): {"value": "Phase 1 & 2\n(Nov 2026 – Jan 2027)"},
        (6, 10): {"value": "Pending"},
    }
    objs = parse_objectives_sheet(obj_grid)
    assert len(objs) == 2
    assert objs[0]["obj_id"] == "GO-0"
    assert objs[0]["task_filter_type"] == "General Objective"
    assert objs[0]["metric_category"] == "End-to-End System"
    assert objs[0]["status"] == "In Progress"
    assert objs[0]["scheduled_window"] == "Aug 2026 – Mar 2027"
    assert objs[1]["obj_id"] == "SO-1"
    assert objs[1]["status"] == "Pending"
    assert "0.80" in objs[1]["target_kpi"]


def test_gdrive_live_diff_and_sync(tmp_path: Path, audit_db: Audit):
    """Verifies GDrive vs local/baseline diffing and sync_timeline_with_gdrive."""
    from backend.tools.team_tracker import sync_timeline_with_gdrive

    local_bytes = generate_citizengraph_v2_test_fixture()
    gdrive_modified_bytes = generate_citizengraph_v2_test_fixture(
        wbs_status_overrides={"1.6": "Completed"},
        roadmap_status_overrides={"STG-03": "Completed"},
    )
    xlsx_file = tmp_path / "CitizenGraph_Thesis_Timeline_2026_2027.xlsx"
    xlsx_file.write_bytes(local_bytes)

    settings = Settings(
        desktop_root=tmp_path,
        api_token="test_token_1234567890abcdef",
        team_excel_path=xlsx_file,
        team_gdrive_folder_url="https://docs.google.com/spreadsheets/d/1Kw4_zboMzpv2WKdJHeNVuSYSfW4Gg_xm/edit?usp=drive_link",
    )

    mock_gd_info = {
        "folder_url": settings.team_gdrive_folder_url,
        "file_id": "1Kw4_zboMzpv2WKdJHeNVuSYSfW4Gg_xm",
        "reachable": True,
        "xlsx_downloaded": True,
        "xlsx_size": len(gdrive_modified_bytes),
        "status": "synced",
        "status_code": 200,
    }

    # 1. Seed baseline from local_bytes
    with patch("backend.tools.team_tracker.fetch_gdrive_excel_bytes", return_value=(local_bytes, mock_gd_info)):
        initial_scan = scan_team_progress(settings=settings, audit=audit_db)
        assert initial_scan["diff"]["has_changes"] is False

    # 2. Simulate team updating Google Sheet (STG-03 & 1.6 -> Completed)
    with patch("backend.tools.team_tracker.fetch_gdrive_excel_bytes", return_value=(gdrive_modified_bytes, mock_gd_info)):
        diff_scan = scan_team_progress(settings=settings, audit=audit_db)
        assert diff_scan["diff"]["has_changes"] is True
        assert diff_scan["diff"]["change_count"] == 2
        assert diff_scan["gdrive_info"]["status"] == "gdrive_changes_detected"

        # 3. Sync pulls GDrive bytes to local Excel and commits new baseline
        sync_res = sync_timeline_with_gdrive(settings=settings, audit=audit_db, pull_gdrive=True)
        assert sync_res["ok"] is True
        assert sync_res["gdrive_pulled"] is True
        assert sync_res["committed_count"] == 37

        # 4. Subsequent scan reports 0 changes and in_sync_with_gdrive
        post_sync_scan = scan_team_progress(settings=settings, audit=audit_db)
        assert post_sync_scan["diff"]["has_changes"] is False
        assert post_sync_scan["gdrive_info"]["status"] == "in_sync_with_gdrive"



