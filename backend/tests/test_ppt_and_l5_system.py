"""Tests for Phase 8C: Level 5 PowerPoint Exact-Slide Presenter & System Authority.

Mandatory Gates:
1. Zero-dependency XML slide parser extracts slide titles, numbers, and bodies accurately from a 5-slide .pptx.
2. 'find and open citizengraph ppt to powerpoint and show the slide 5' routes to ppt_open_slide with query='citizengraph' and slide=5.
3. COM automation call is mocked cleanly in pytest and blocked at Level 1 and Level 3 (requires Level 5).
4. 'restart my pc' and 'rerun yourself' require Level 5 AND return needs_confirm=True (never execute without confirmation).
"""
from __future__ import annotations

import asyncio
import json
from pathlib import Path
import time
import pytest
import zipfile

from backend.config import Settings
from backend.core.actions import Registry, plan_cancel_shutdown, plan_restart_nightmare, plan_restart_pc, plan_shutdown_pc
from backend.core.clearance import ClearanceManager, LEVEL_5
from backend.core.llm import NoLLMProvider
from backend.core.orchestrator import Orchestrator
from backend.core.router import route
from backend.tools.audit import Audit
from backend.tools.file_navigator import index_files
from backend.tools.ppt_controller import (
    PPTCOMAdapter,
    find_slide_by_topic,
    get_com_adapter,
    parse_ppt_slides,
    set_com_adapter,
)


def _create_minimal_pptx(dest_path: Path, slides: list[tuple[str, str]]) -> Path:
    """Helper creating a minimal valid .pptx archive with the provided (title, body) pairs."""
    with zipfile.ZipFile(dest_path, "w") as zf:
        for idx, (title, body) in enumerate(slides, start=1):
            slide_xml = f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<p:sld xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main"
       xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main">
  <p:cSld>
    <p:spTree>
      <p:sp>
        <p:nvSpPr>
          <p:cNvPr id="2" name="Title {idx}"/>
          <p:nvPr>
            <p:ph type="title"/>
          </p:nvPr>
        </p:nvSpPr>
        <p:txBody>
          <a:p>
            <a:r>
              <a:t>{title}</a:t>
            </a:r>
          </a:p>
        </p:txBody>
      </p:sp>
      <p:sp>
        <p:nvSpPr>
          <p:cNvPr id="3" name="Body {idx}"/>
          <p:nvPr>
            <p:ph type="body"/>
          </p:nvPr>
        </p:nvSpPr>
        <p:txBody>
          <a:p>
            <a:r>
              <a:t>{body}</a:t>
            </a:r>
          </a:p>
        </p:txBody>
      </p:sp>
    </p:spTree>
  </p:cSld>
</p:sld>"""
            zf.writestr(f"ppt/slides/slide{idx}.xml", slide_xml)
    return dest_path


# ==============================================================================
# Gate 1: Zero-Dependency XML Slide Parser
# ==============================================================================

def test_gate1_zero_dependency_xml_slide_parser(tmp_path):
    """Create a minimal valid .pptx zip archive in tmp_path with 5 slides and verify
    the zero-dependency XML slide parser extracts slide titles and numbers accurately."""
    pptx_path = tmp_path / "citizengraph_presentation.pptx"
    slides_data = [
        ("Introduction to CitizenGraph", "A graph neural network system for legal intelligence."),
        ("System Architecture", "Frontend React GSAP, Backend FastAPI, SQLite database."),
        ("Data Pipeline", "Ingesting case laws and parsing legal concepts into knowledge graphs."),
        ("Evaluation and Results", "Accuracy reached 94.2% across benchmark datasets."),
        ("Conclusion and Future Work", "Expanding to real-time graph visualization and export."),
    ]
    _create_minimal_pptx(pptx_path, slides_data)

    parsed = parse_ppt_slides(pptx_path)
    assert len(parsed) == 5

    # Check slide numbers and titles
    assert parsed[0]["slide_number"] == 1
    assert parsed[0]["title"] == "Introduction to CitizenGraph"
    assert "graph neural network" in parsed[0]["body"]

    assert parsed[1]["slide_number"] == 2
    assert parsed[1]["title"] == "System Architecture"
    assert "FastAPI" in parsed[1]["body"]

    assert parsed[2]["slide_number"] == 3
    assert parsed[2]["title"] == "Data Pipeline"

    assert parsed[3]["slide_number"] == 4
    assert parsed[3]["title"] == "Evaluation and Results"
    assert "94.2%" in parsed[3]["body"]

    assert parsed[4]["slide_number"] == 5
    assert parsed[4]["title"] == "Conclusion and Future Work"

    # Verify topic search resolution
    assert find_slide_by_topic(pptx_path, "architecture") == 2
    assert find_slide_by_topic(pptx_path, "results") == 4
    assert find_slide_by_topic(pptx_path, "pipeline") == 3
    assert find_slide_by_topic(pptx_path, "conclusion") == 5
    assert find_slide_by_topic(pptx_path, "citizengraph") == 1
    assert find_slide_by_topic(pptx_path, "nonexistent query xyz") is None


# ==============================================================================
# Gate 2: Intent Routing Verification
# ==============================================================================

def test_gate2_router_ppt_open_slide_and_controls(tmp_path):
    """Verify 'find and open citizengraph ppt to powerpoint and show the slide 5'
    routes to ppt_open_slide with query='citizengraph' and slide=5."""
    apps_file = tmp_path / "apps.json"
    apps_file.write_text(json.dumps({"apps": {}, "tasks": {}}))
    desktop = tmp_path / "Desktop"
    desktop.mkdir()
    settings = Settings(desktop_root=desktop, api_token="t" * 32, db_path=tmp_path / "n.db", apps_file=apps_file)
    registry = Registry({"apps": {}, "tasks": {}})

    # Mandatory Gate 2 prompt
    i1 = route("find and open citizengraph ppt to powerpoint and show the slide 5", settings, registry)
    assert i1.kind == "ppt_open_slide"
    assert i1.query == "citizengraph"
    assert i1.slide == 5

    # Variations of presentation opening at slide
    i2 = route("open citizengraph presentation at slide 3", settings, registry)
    assert i2.kind == "ppt_open_slide"
    assert i2.query == "citizengraph"
    assert i2.slide == 3

    i3 = route("open quarterly report ppt at slide 10", settings, registry)
    assert i3.kind == "ppt_open_slide"
    assert i3.query == "quarterly report"
    assert i3.slide == 10

    i4 = route("open thesis slides in powerpoint and show slide 4", settings, registry)
    assert i4.kind == "ppt_open_slide"
    assert i4.query == "thesis"
    assert i4.slide == 4

    # Presentation opening by topic
    i5 = route("find and open citizengraph ppt to powerpoint and show the slide about architecture", settings, registry)
    assert i5.kind == "ppt_open_slide"
    assert i5.query == "citizengraph"
    assert i5.note_text == "architecture"

    # Slide navigation controls
    c1 = route("go to slide 4", settings, registry)
    assert c1.kind == "ppt_control"
    assert c1.action == "goto"
    assert c1.slide == 4

    c2 = route("slide 8", settings, registry)
    assert c2.kind == "ppt_control"
    assert c2.action == "goto"
    assert c2.slide == 8

    c3 = route("next slide", settings, registry)
    assert c3.kind == "ppt_control"
    assert c3.action == "next"

    c4 = route("previous slide", settings, registry)
    assert c4.kind == "ppt_control"
    assert c4.action == "previous"

    c5 = route("show the slide about evaluation", settings, registry)
    assert c5.kind == "ppt_control"
    assert c5.action == "topic"
    assert c5.query == "evaluation"


# ==============================================================================
# Gate 3: COM Automation Mocking & Clearance Enforcement
# ==============================================================================

class MockPPTAdapter(PPTCOMAdapter):
    def __init__(self):
        self.calls: list[tuple] = []

    def open_presentation_at_slide(self, file_path: str, slide_number: int = 1) -> tuple[bool, str]:
        self.calls.append(("open", file_path, slide_number))
        return True, f"Mock opened {Path(file_path).name} at slide {slide_number}."

    def goto_slide(self, slide_number: int) -> tuple[bool, str]:
        self.calls.append(("goto", slide_number))
        return True, f"Mock goto {slide_number}."

    def next_slide(self) -> tuple[bool, str]:
        self.calls.append(("next",))
        return True, "Mock next slide."

    def previous_slide(self) -> tuple[bool, str]:
        self.calls.append(("previous",))
        return True, "Mock previous slide."


def test_gate3_com_automation_mocked_and_blocked_at_level1_and_level3(tmp_path):
    """Verify COM automation call is mocked cleanly in pytest and blocked at Level 1
    and Level 3 (requires Level 5)."""
    mock_adapter = MockPPTAdapter()
    original_adapter = get_com_adapter()
    set_com_adapter(mock_adapter)
    try:
        desktop = tmp_path / "Desktop"
        desktop.mkdir()
        pptx_file = desktop / "citizengraph.pptx"
        _create_minimal_pptx(pptx_file, [
            ("Slide 1", "Content 1"),
            ("Slide 2", "Content 2"),
            ("Slide 3", "Content 3"),
            ("Slide 4", "Content 4"),
            ("Slide 5", "Content 5"),
        ])

        db_path = tmp_path / "audit.db"
        audit = Audit(db_path)
        index_files(roots=[desktop], audit=audit)

        apps_file = tmp_path / "apps.json"
        apps_file.write_text(json.dumps({"apps": {}, "tasks": {}}))
        settings = Settings(desktop_root=desktop, api_token="t" * 32, db_path=db_path, apps_file=apps_file)
        registry = Registry({"apps": {}, "tasks": {}})
        clearance = ClearanceManager()

        orch = Orchestrator(settings, NoLLMProvider(), registry, audit, clearance=clearance)

        # 1. Remote read-only: Blocked
        rep_ro = asyncio.run(orch.handle("find and open citizengraph ppt to powerpoint and show the slide 5", readonly=True))
        assert rep_ro.ok is False
        assert "read-only" in rep_ro.text.lower()
        assert len(mock_adapter.calls) == 0  # COM call must NOT execute

        # 2. Local Level 5: Allowed!
        rep_l5 = asyncio.run(orch.handle("find and open citizengraph ppt to powerpoint and show the slide 5"))
        assert rep_l5.ok is True
        assert len(mock_adapter.calls) == 1
        assert mock_adapter.calls[0][0] == "open"
        assert "citizengraph.pptx" in mock_adapter.calls[0][1]
        assert mock_adapter.calls[0][2] == 5

        # 4. Active presentation controls at Level 5
        rep_next = asyncio.run(orch.handle("next slide"))
        assert rep_next.ok is True
        assert mock_adapter.calls[-1] == ("next",)

        rep_prev = asyncio.run(orch.handle("previous slide"))
        assert rep_prev.ok is True
        assert mock_adapter.calls[-1] == ("previous",)

        rep_goto = asyncio.run(orch.handle("go to slide 4"))
        assert rep_goto.ok is True
        assert mock_adapter.calls[-1] == ("goto", 4)

        # 5. Remote read-only blocks presentation controls
        rep_ro_again = asyncio.run(orch.handle("next slide", readonly=True))
        assert rep_ro_again.ok is False
        assert "read-only" in rep_ro_again.text.lower()

    finally:
        set_com_adapter(original_adapter)


# ==============================================================================
# Gate 4: System Authority Requires Level 5 AND Confirmation
# ==============================================================================

def test_gate4_system_authority_requires_level5_and_confirmation(tmp_path):
    """Verify 'restart my pc' and 'rerun yourself' require Level 5 AND return
    needs_confirm=True (never execute without confirmation)."""
    desktop = tmp_path / "Desktop"
    desktop.mkdir()
    db_path = tmp_path / "audit.db"
    audit = Audit(db_path)
    apps_file = tmp_path / "apps.json"
    apps_file.write_text(json.dumps({"apps": {}, "tasks": {}}))
    settings = Settings(desktop_root=desktop, api_token="t" * 32, db_path=db_path, apps_file=apps_file)
    registry = Registry({"apps": {}, "tasks": {}})
    clearance = ClearanceManager()

    orch = Orchestrator(settings, NoLLMProvider(), registry, audit, clearance=clearance)

    # 1. Remote read-only: Blocked, no confirmation prompt generated
    r1 = asyncio.run(orch.handle("restart my pc", readonly=True))
    assert r1.ok is False
    assert "read-only" in r1.text.lower()
    assert r1.as_dict()["needs_confirm"] is False
    assert r1.pending_id is None

    r2 = asyncio.run(orch.handle("rerun yourself", readonly=True))
    assert r2.ok is False
    assert "read-only" in r2.text.lower()
    assert r2.as_dict()["needs_confirm"] is False
    assert r2.pending_id is None

    r3 = asyncio.run(orch.handle("shut down my pc", readonly=True))
    assert r3.ok is False
    assert "read-only" in r3.text.lower()

    # 2. Local Level 5: Allowed AND strictly requires click confirmation

    # Restart PC
    r_pc = asyncio.run(orch.handle("restart my pc"))
    assert r_pc.as_dict()["needs_confirm"] is True
    assert r_pc.pending_id is not None
    assert "restart the PC" in r_pc.text
    # Verify the plan inside pending store
    plan_pc = orch.pending.pop(r_pc.pending_id)
    assert plan_pc is not None
    assert plan_pc.argv == ["shutdown", "/r", "/t", "10"]
    assert plan_pc.needs_confirm is True

    # Rerun Yourself / Restart Nightmare
    r_nightmare = asyncio.run(orch.handle("rerun yourself"))
    assert r_nightmare.as_dict()["needs_confirm"] is True
    assert r_nightmare.pending_id is not None
    assert "restart Nightmare" in r_nightmare.text
    plan_nightmare = orch.pending.pop(r_nightmare.pending_id)
    assert plan_nightmare is not None
    assert "start_nightmare.ps1" in plan_nightmare.argv[4]
    assert "-Rebuild" in plan_nightmare.argv
    assert "-Background" in plan_nightmare.argv
    assert plan_nightmare.needs_confirm is True

    # Alternate phrasing: "restart nightmare"
    r_alt = asyncio.run(orch.handle("restart nightmare"))
    assert r_alt.as_dict()["needs_confirm"] is True
    assert r_alt.pending_id is not None

    # Shut down PC
    r_shut = asyncio.run(orch.handle("shut down my pc"))
    assert r_shut.as_dict()["needs_confirm"] is True
    assert r_shut.pending_id is not None
    plan_shut = orch.pending.pop(r_shut.pending_id)
    assert plan_shut is not None
    assert plan_shut.argv == ["shutdown", "/s", "/t", "10"]

    # Cancel shutdown: requires Level 5, executes without click confirmation
    r_cancel = asyncio.run(orch.handle("cancel shutdown"))
    assert r_cancel.as_dict()["needs_confirm"] is False
