"""Team Timeline and Quota Tracker for Project Nightmare (Phase 8D & Phase 8D-2).

Parses shared Excel timelines (.xlsx) using Python's standard library
zipfile + xml.etree.ElementTree (zero external pip dependencies).
Supports the 4-tab CitizenGraph_Thesis_Timeline_2026_2027.xlsx structure:
  1. General 8-Month Roadmap (STG-01..STG-09)
  2. Detailed Weekly Gantt (1.1..1.12, 2.1..2.9)
  3. Objectives & KPI Alignment (GO-0, SO-1..SO-7, 10-column & legacy 8-column)
  4. Phase Summary & Dashboard (Live Python rollups & KPI targets)
Maintains baseline snapshot in SQLite Audit database, provides live Google Drive
spreadsheet (.xlsx) export & cross-reference diff engine, performs automatic 3-day
stale quota detection, and generates Level 5 email nudgers.
"""
from __future__ import annotations

import hashlib
import io
import logging
import os
import re
import time
import urllib.request
import zipfile
import xml.etree.ElementTree as ET
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from ..config import Settings
    from ..tools.audit import Audit

logger = logging.getLogger(__name__)

DEFAULT_GDRIVE_URL = (
    "https://docs.google.com/spreadsheets/d/1Kw4_zboMzpv2WKdJHeNVuSYSfW4Gg_xm/"
    "edit?usp=drive_link&ouid=109543692766011182977&rtpof=true&sd=true"
)
DEFAULT_EXCEL_FILENAME = "CitizenGraph_Thesis_Timeline_2026_2027.xlsx"

# Canonical fill colors & badges
COLOR_CORE_HEX = "9DC3E6"       # Core Work (#9DC3E6)
COLOR_BUFFER_HEX = "C6E0B4"     # Buffer / Polish (#C6E0B4)
COLOR_MILESTONE_HEX = "FFD966"  # Milestone (#FFD966)
COLOR_PHASE1_HEX = "0284C7"     # Sky Blue Phase 1 (#0284C7)
COLOR_PHASE2_HEX = "0D9488"     # Teal Phase 2 (#0D9488)
COLOR_INDIGO_HEX = "4F46E5"     # Indigo Milestone (#4F46E5)

# In-memory short-lived cache for GDrive export bytes so back-to-back calls don't block
_GDRIVE_CACHE: dict[str, tuple[float, bytes | None, dict[str, Any]]] = {}
_GDRIVE_CACHE_TTL = 25.0


def _strip_ns(tag: str) -> str:
    return tag.split("}")[-1] if "}" in tag else tag


def _col_str_to_idx(col_str: str) -> int:
    num = 0
    for c in col_str.upper():
        if "A" <= c <= "Z":
            num = num * 26 + (ord(c) - ord("A") + 1)
    return num


def _split_cell_ref(ref: str) -> tuple[int, int]:
    m = re.match(r"^([A-Z]+)([0-9]+)$", ref.upper())
    if not m:
        return 0, 0
    return int(m.group(2)), _col_str_to_idx(m.group(1))


def resolve_team_excel_path(settings: Settings | None = None) -> Path | None:
    """Finds the team Excel timeline file path from settings, env, OneDrive thesis dir, or desktop."""
    # 1. Configured path from settings or environment
    configured: Path | None = None
    if settings and settings.team_excel_path:
        configured = Path(settings.team_excel_path).expanduser()
    elif os.environ.get("NIGHTMARE_TEAM_EXCEL_PATH", "").strip():
        configured = Path(os.environ["NIGHTMARE_TEAM_EXCEL_PATH"].strip().strip('"\'')).expanduser()

    if configured:
        if configured.is_file():
            return configured
        # If configured path directory exists, check sibling timeline filenames
        if configured.parent.is_dir():
            for name in (
                configured.name,
                "CitizenGraph_Thesis_Timeline_2026_2027.xlsx",
                "CitizenGraph_Thesis_Timeline_2026_2027-v3.xlsx",
                "CitizenGraph_Thesis_Timeline_2026_2027-v2.xlsx",
            ):
                cand = configured.parent / name
                if cand.is_file():
                    return cand

    # 2. Check standard OneDrive Thesis folder and desktop root
    candidate_dirs: list[Path] = []
    if settings and settings.desktop_root:
        candidate_dirs.append(Path(settings.desktop_root))
    home = Path.home()
    for rel in (
        Path("OneDrive") / "Documents" / "4RTH-YEAR THESIS RESARCH AND DOCUMENTATION",
        Path("Documents") / "4RTH-YEAR THESIS RESARCH AND DOCUMENTATION",
        Path("Desktop"),
        Path("OneDrive") / "Desktop",
    ):
        d = home / rel
        if d.is_dir() and d not in candidate_dirs:
            candidate_dirs.append(d)

    candidate_names = (
        "CitizenGraph_Thesis_Timeline_2026_2027.xlsx",
        "CitizenGraph_Thesis_Timeline_2026_2027-v3.xlsx",
        "CitizenGraph_Thesis_Timeline_2026_2027-v2.xlsx",
        "CitizenGraph_Thesis_Timeline_2027-v2.xlsx",
        "NexEnroll_Development_Timeline.xlsx",
    )
    for d in candidate_dirs:
        for name in candidate_names:
            candidate = d / name
            if candidate.is_file():
                return candidate

    return None


def resolve_timeline_workbook(
    desktop_root: Path | None = None,
    configured_path: Path | None = None,
) -> Path | None:
    """Backward-compatible helper used by orchestrator._do_open_team_excel."""
    if configured_path and Path(configured_path).is_file():
        return Path(configured_path)
    if desktop_root:
        for name in (
            "CitizenGraph_Thesis_Timeline_2026_2027.xlsx",
            "CitizenGraph_Thesis_Timeline_2026_2027-v3.xlsx",
            "CitizenGraph_Thesis_Timeline_2026_2027-v2.xlsx",
            "NexEnroll_Development_Timeline.xlsx",
        ):
            cand = Path(desktop_root) / name
            if cand.is_file():
                return cand
    return resolve_team_excel_path(None)


class OpenXMLSheetReader:
    """Zero-dependency OpenXML (.xlsx) parser."""

    def __init__(self, file_path_or_bytes: Path | bytes):
        if isinstance(file_path_or_bytes, bytes):
            self.zf = zipfile.ZipFile(io.BytesIO(file_path_or_bytes))
        else:
            self.zf = zipfile.ZipFile(file_path_or_bytes)
        self._shared_strings: list[str] = []
        self._cell_styles: dict[int, str | None] = {}
        self._sheets: dict[str, str] = {}
        self._load_styles()
        self._load_shared_strings()
        self._load_workbook_sheets()

    def _load_styles(self) -> None:
        if "xl/styles.xml" not in self.zf.namelist():
            return
        try:
            root = ET.fromstring(self.zf.read("xl/styles.xml"))
            fills_el = None
            cell_xfs_el = None
            for el in root:
                tag = _strip_ns(el.tag)
                if tag == "fills":
                    fills_el = el
                elif tag == "cellXfs":
                    cell_xfs_el = el

            fills: list[str | None] = []
            if fills_el is not None:
                for fill in fills_el:
                    color_hex = None
                    for child in fill:
                        if _strip_ns(child.tag) == "patternFill":
                            for c in child:
                                if _strip_ns(c.tag) in ("fgColor", "bgColor"):
                                    rgb = c.attrib.get("rgb")
                                    if rgb:
                                        if len(rgb) == 8:
                                            rgb = rgb[2:]
                                        color_hex = rgb.upper()
                    fills.append(color_hex)

            if cell_xfs_el is not None:
                for idx, xf in enumerate(cell_xfs_el):
                    fill_id = int(xf.attrib.get("fillId", 0))
                    self._cell_styles[idx] = fills[fill_id] if fill_id < len(fills) else None
        except Exception as exc:
            logger.debug("Failed to parse xl/styles.xml: %s", exc)

    def _load_shared_strings(self) -> None:
        if "xl/sharedStrings.xml" not in self.zf.namelist():
            return
        try:
            root = ET.fromstring(self.zf.read("xl/sharedStrings.xml"))
            for si in root:
                parts = []
                for node in si.iter():
                    if _strip_ns(node.tag) == "t" and node.text:
                        parts.append(node.text)
                self._shared_strings.append("".join(parts))
        except Exception as exc:
            logger.debug("Failed to parse xl/sharedStrings.xml: %s", exc)

    def _load_workbook_sheets(self) -> None:
        wb_rels: dict[str, str] = {}
        if "xl/_rels/workbook.xml.rels" in self.zf.namelist():
            try:
                root = ET.fromstring(self.zf.read("xl/_rels/workbook.xml.rels"))
                for rel in root:
                    rid = rel.attrib.get("Id")
                    target = rel.attrib.get("Target")
                    if rid and target:
                        if not target.startswith("xl/") and not target.startswith("/xl/"):
                            target = "xl/" + target.lstrip("/")
                        wb_rels[rid] = target.lstrip("/")
            except Exception as exc:
                logger.debug("Failed to parse workbook rels: %s", exc)

        if "xl/workbook.xml" in self.zf.namelist():
            try:
                root = ET.fromstring(self.zf.read("xl/workbook.xml"))
                for el in root.iter():
                    if _strip_ns(el.tag) == "sheet":
                        name = el.attrib.get("name", "")
                        rid = (
                            el.attrib.get("{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id")
                            or el.attrib.get("r:id")
                        )
                        if name and rid and rid in wb_rels:
                            self._sheets[name.lower()] = wb_rels[rid]
            except Exception as exc:
                logger.debug("Failed to parse xl/workbook.xml: %s", exc)

    def sheet_names(self) -> list[str]:
        return list(self._sheets.keys())

    def find_sheet_target(self, *queries: str) -> str | None:
        """Finds worksheet XML path by checking multiple query keywords."""
        for q in queries:
            q_norm = q.lower().replace("_", " ").replace("-", " ").strip()
            # 1. Exact match
            for name, path in self._sheets.items():
                name_norm = name.replace("_", " ").replace("-", " ").strip()
                if q_norm == name_norm:
                    return path
            # 2. Substring match
            for name, path in self._sheets.items():
                name_norm = name.replace("_", " ").replace("-", " ").strip()
                if q_norm in name_norm or name_norm in q_norm:
                    return path
        return None

    def read_sheet(self, *queries: str) -> dict[tuple[int, int], dict[str, Any]]:
        """Reads cell grid (row, col) -> {"value": str, "color": str|None}."""
        target_path = self.find_sheet_target(*queries)
        if not target_path or target_path not in self.zf.namelist():
            return {}

        root = ET.fromstring(self.zf.read(target_path))
        grid: dict[tuple[int, int], dict[str, Any]] = {}

        for row in root.iter():
            if _strip_ns(row.tag) == "row":
                r_idx = int(row.attrib.get("r", 0))
                for c in row:
                    if _strip_ns(c.tag) == "c":
                        ref = c.attrib.get("r", "")
                        if ref:
                            c_row, c_col = _split_cell_ref(ref)
                        else:
                            c_row, c_col = r_idx, 1

                        s_idx = int(c.attrib.get("s", 0)) if "s" in c.attrib else 0
                        cell_color = self._cell_styles.get(s_idx)
                        t = c.attrib.get("t", "")

                        val = ""
                        v_el = None
                        is_el = None
                        for child in c:
                            tag = _strip_ns(child.tag)
                            if tag == "v":
                                v_el = child
                            elif tag in ("is", "inlineStr"):
                                is_el = child

                        if t == "s" and v_el is not None and v_el.text:
                            try:
                                s_id = int(v_el.text)
                                val = self._shared_strings[s_id] if s_id < len(self._shared_strings) else ""
                            except ValueError:
                                val = v_el.text
                        elif is_el is not None:
                            val = "".join(is_el.itertext())
                        elif v_el is not None and v_el.text:
                            val = v_el.text

                        grid[(c_row, c_col)] = {
                            "value": val.strip(),
                            "color": f"#{cell_color}" if cell_color else None,
                        }
        return grid


def _classify_month_cell(cell: dict[str, Any]) -> dict[str, Any]:
    val = cell.get("value", "")
    color = (cell.get("color") or "").upper().replace("#", "")

    # Priority 1: Milestone (Color FFD966 / 4F46E5 or Diamond ◆ / Star ★ / Milestone text)
    if (
        COLOR_MILESTONE_HEX in color
        or COLOR_INDIGO_HEX in color
        or "◆" in val
        or "★" in val
        or "⭐" in val
        or "star" in val.lower()
        or "milestone" in val.lower()
    ):
        return {
            "status": "milestone",
            "type": "Milestone",
            "color": "#4F46E5" if (COLOR_INDIGO_HEX in color or "◆" in val) else "#FFD966",
            "text": val,
            "active": True,
        }
    # Priority 2: Phase 1 / Core Work (#0284C7 or #9DC3E6)
    if (
        COLOR_PHASE1_HEX in color
        or COLOR_CORE_HEX in color
        or ("■" in val and COLOR_PHASE2_HEX not in color)
        or "●" in val
        or "core" in val.lower()
    ):
        return {
            "status": "core",
            "type": "Phase 1 / Core",
            "color": "#0284C7" if (COLOR_PHASE1_HEX in color or "■" in val) else "#9DC3E6",
            "text": val,
            "active": True,
        }
    # Priority 3: Phase 2 / Buffer / Polish (#0D9488 or #C6E0B4)
    if (
        COLOR_PHASE2_HEX in color
        or COLOR_BUFFER_HEX in color
        or "buffer" in val.lower()
        or "polish" in val.lower()
    ):
        return {
            "status": "buffer",
            "type": "Phase 2 / Polish",
            "color": "#0D9488" if COLOR_PHASE2_HEX in color else "#C6E0B4",
            "text": val,
            "active": True,
        }

    # Text indicator fallback
    if val and val.strip() in {"■", "◆", "●", "★", "⭐", "x", "X", "1", "v", "V"}:
        return {
            "status": "active",
            "type": "Active",
            "color": "#0284C7",
            "text": val,
            "active": True,
        }

    return {
        "status": "none",
        "type": "None",
        "color": None,
        "text": val,
        "active": False,
    }


def _normalize_status(val: str, fallback: str = "Pending") -> str:
    s = val.strip().lower()
    if "complete" in s or "done" in s:
        return "Completed"
    if "progress" in s or "ongoing" in s or "active" in s:
        return "In Progress"
    if "pending" in s or "queue" in s or "todo" in s or "planned" in s:
        return "Pending"
    return fallback


# ==============================================================================
# TAB 1: General 8-Month Roadmap (STG-01 .. STG-09)
# ==============================================================================

def parse_roadmap_sheet(grid: dict[tuple[int, int], dict[str, Any]]) -> list[dict[str, Any]]:
    """Extracts General 8-Month Roadmap (Rows 5-13, STG-01..STG-09), ignoring summary footer rows."""
    if not grid:
        return []

    max_row = max(r for r, _ in grid.keys()) if grid else 1
    header_row = None
    col_map: dict[str, int] = {}
    month_cols: dict[int, tuple[int, str]] = {}  # m_idx (1..8) -> (col_idx, label)

    for r in range(1, min(max_row + 1, 15)):
        row_vals = {c: grid.get((r, c), {}).get("value", "").strip() for c in range(1, 30)}
        row_lower = {c: v.lower() for c, v in row_vals.items()}

        found_stage = any("stage id" in v or v in ("stg", "stage #") for v in row_lower.values())
        found_m = any("m1" in v or "aug" in v or "month 1" in v for v in row_lower.values())

        if found_stage and found_m:
            header_row = r
            for c, text in row_vals.items():
                tl = text.lower()
                if "stage id" in tl or tl in {"stg", "stage #", "id"}:
                    col_map["stage_id"] = c
                elif "timeline stage" in tl or tl == "stage":
                    col_map["stage_name"] = c
                elif "calendar span" in tl or "span" in tl or "calendar" in tl:
                    col_map["calendar_span"] = c
                elif "thesis phase" in tl or "phase" in tl:
                    col_map["phase"] = c
                elif "general stage title" in tl or "stage title" in tl or "title" in tl:
                    col_map["title"] = c
                elif "aligned activities" in tl or "core activities" in tl or "team goals" in tl or "core focus" in tl or "activities" in tl:
                    col_map["activities"] = c
                elif "milestone" in tl or "output" in tl:
                    col_map["milestone"] = c
                elif tl == "status":
                    col_map["status"] = c

                for m in range(1, 9):
                    if f"m{m}" in tl or f"month {m}" in tl:
                        month_cols[m] = (c, " ".join(text.split()))
            break

    if header_row is None:
        header_row = 4

    col_map.setdefault("stage_id", 1)
    col_map.setdefault("stage_name", 2)
    col_map.setdefault("calendar_span", 3)
    col_map.setdefault("phase", 4)
    col_map.setdefault("title", 5)
    col_map.setdefault("activities", 6)
    col_map.setdefault("milestone", 7)
    col_map.setdefault("status", 8)

    month_labels = [
        "M1 Aug '26", "M2 Sep '26", "M3 Oct '26", "M4 Nov '26",
        "M5 Dec '26", "M6 Jan '27", "M7 Feb '27", "M8 Mar '27",
    ]
    if not month_cols:
        for m in range(1, 9):
            month_cols[m] = (8 + m, month_labels[m - 1])

    stages = []
    for r in range(header_row + 1, max_row + 1):
        stg_id = grid.get((r, col_map["stage_id"]), {}).get("value", "").strip()
        title = grid.get((r, col_map["title"]), {}).get("value", "").strip()

        # Stop immediately if we reach the summary block at the bottom of the sheet
        if stg_id and ("status summary" in stg_id.lower() or stg_id.lower() in {"completed stages", "in progress stages", "pending stages"}):
            break

        if not stg_id and not title:
            continue

        # Strictly require STG-XX, Stage X, or digit stage ID (reject footer labels like "Completed Stages")
        if stg_id:
            if not (re.match(r"^STG-\d+$", stg_id, re.I) or re.match(r"^Stage\s*\d+$", stg_id, re.I) or stg_id.isdigit()):
                continue
        elif not title:
            continue

        stg_name = grid.get((r, col_map["stage_name"]), {}).get("value", "").strip()
        span = grid.get((r, col_map["calendar_span"]), {}).get("value", "").strip()
        phase = grid.get((r, col_map["phase"]), {}).get("value", "").strip()
        activities = grid.get((r, col_map["activities"]), {}).get("value", "").strip()
        milestone = grid.get((r, col_map["milestone"]), {}).get("value", "").strip()
        raw_status = grid.get((r, col_map["status"]), {}).get("value", "").strip()
        status = _normalize_status(raw_status)

        months = []
        active_month_names = []
        for m in range(1, 9):
            c_idx, m_label = month_cols.get(m, (8 + m, month_labels[m - 1]))
            cell = grid.get((r, c_idx), {"value": "", "color": None})
            classified = _classify_month_cell(cell)
            classified["month_index"] = m
            classified["label"] = m_label
            if classified["active"]:
                active_month_names.append(m_label.split()[1] if " " in m_label else m_label)
            months.append(classified)

        stages.append({
            "stage_id": stg_id or f"STG-{len(stages)+1:02d}",
            "stage_name": stg_name or f"Month {len(stages)+1}",
            "calendar_span": span,
            "phase": phase or ("Phase 1" if len(stages) < 5 else "Phase 2"),
            "title": title or f"Roadmap Stage {len(stages)+1}",
            "activities": activities,
            "milestone": milestone,
            "status": status,
            "months": months,
            "active_months": active_month_names,
        })

    return stages


# ==============================================================================
# TAB 2: Detailed Weekly Gantt (WBS 1.1..1.12, 2.1..2.9)
# ==============================================================================

def parse_weekly_gantt_sheet(grid: dict[tuple[int, int], dict[str, Any]]) -> list[dict[str, Any]]:
    """Extracts Detailed Weekly Gantt (Rows 6-26, WBS 1.1..1.12, 2.1..2.9)."""
    if not grid:
        return []

    max_row = max(r for r, _ in grid.keys()) if grid else 1
    header_row = None
    col_map: dict[str, int] = {}
    week_cols: dict[int, tuple[int, str]] = {}  # week_idx (1..24) -> (col_idx, code)

    for r in range(1, min(max_row + 1, 15)):
        row_vals = {c: grid.get((r, c), {}).get("value", "").strip() for c in range(1, 40)}
        row_lower = {c: v.lower() for c, v in row_vals.items()}

        found_wbs = any("wbs id" in v or v in ("wbs", "wbs #") for v in row_lower.values())
        found_week = any("s-w1" in v or "o-w1" in v for v in row_lower.values())

        if found_wbs or (found_week and any("deliverable" in v for v in row_lower.values())):
            header_row = r
            for c, text in row_vals.items():
                tl = text.lower()
                if "wbs id" in tl or tl in {"wbs", "wbs #", "id"}:
                    col_map["wbs_id"] = c
                elif "phase" in tl or "stage" in tl:
                    col_map["phase"] = c
                elif "task / activity" in tl or "task description" in tl or "shared team goal" in tl or tl in {"task", "activity"}:
                    col_map["task"] = c
                elif "aligned thesis" in tl or "study objective" in tl or "system module" in tl or "module" in tl:
                    col_map["module"] = c
                elif "deliverable" in tl or "target metric" in tl or "benchmark result" in tl:
                    col_map["deliverable"] = c
                elif tl in {"period", "scheduled window", "window"}:
                    col_map["period"] = c
                elif tl == "status":
                    col_map["status"] = c

                m_week = re.match(r"^([A-Z])[-_]?W?(\d+)$", text.upper())
                if m_week or text.upper().endswith(("-W1", "-W2", "-W3", "-W4")):
                    idx = len(week_cols) + 1
                    if idx <= 24:
                        week_cols[idx] = (c, text)
            break

    if header_row is None:
        header_row = 5

    col_map.setdefault("wbs_id", 1)
    col_map.setdefault("phase", 2)
    col_map.setdefault("task", 3)
    col_map.setdefault("module", 4)
    col_map.setdefault("deliverable", 5)
    col_map.setdefault("period", 6)
    col_map.setdefault("status", 7)

    # 24 standard week codes: S-W1..S-W4, O-W1..O-W4, N-W1..N-W4, D-W1..D-W4, J-W1..J-W4, F-W1..F-W4
    standard_weeks = [
        ("Sept", 1), ("Sept", 2), ("Sept", 3), ("Sept", 4),
        ("Oct", 1), ("Oct", 2), ("Oct", 3), ("Oct", 4),
        ("Nov", 1), ("Nov", 2), ("Nov", 3), ("Nov", 4),
        ("Dec", 1), ("Dec", 2), ("Dec", 3), ("Dec", 4),
        ("Jan", 1), ("Jan", 2), ("Jan", 3), ("Jan", 4),
        ("Feb", 1), ("Feb", 2), ("Feb", 3), ("Feb", 4),
    ]

    tasks = []
    for r in range(header_row + 1, max_row + 1):
        wbs_id = grid.get((r, col_map["wbs_id"]), {}).get("value", "").strip()
        task_desc = grid.get((r, col_map["task"]), {}).get("value", "").strip()

        if not wbs_id and not task_desc:
            continue
        # Filter rows: must look like WBS task (1.1..1.12, 2.1..2.9)
        if wbs_id and not re.match(r"^\d+\.\d+$", wbs_id):
            continue

        phase = grid.get((r, col_map["phase"]), {}).get("value", "").strip()
        module = grid.get((r, col_map["module"]), {}).get("value", "").strip()
        deliverable = grid.get((r, col_map["deliverable"]), {}).get("value", "").strip()
        period = grid.get((r, col_map["period"]), {}).get("value", "").strip()
        raw_status = grid.get((r, col_map["status"]), {}).get("value", "").strip()
        status = _normalize_status(raw_status)

        weeks = []
        active_indices = []
        active_months = set()

        for w_idx in range(1, 25):
            c_info = week_cols.get(w_idx)
            c_col = c_info[0] if c_info else (7 + w_idx)
            cell = grid.get((r, c_col), {"value": "", "color": None})
            classified = _classify_month_cell(cell)

            m_name, w_num = standard_weeks[w_idx - 1]
            code = f"{m_name[:1]}-W{w_num}"
            classified["week_code"] = code
            classified["month"] = m_name
            classified["week_num"] = w_num
            classified["week_index"] = w_idx

            if classified["active"]:
                active_indices.append(w_idx)
                active_months.add(m_name)
            weeks.append(classified)

        # Summarize into compressed span
        if active_indices:
            start_w = standard_weeks[active_indices[0] - 1]
            end_w = standard_weeks[active_indices[-1] - 1]
            if active_indices[0] == active_indices[-1]:
                computed_span = f"{start_w[0]} W{start_w[1]}"
            else:
                computed_span = f"{start_w[0]} W{start_w[1]} - {end_w[0]} W{end_w[1]}"
        else:
            computed_span = period or "TBD"

        tasks.append({
            "wbs_id": wbs_id or f"1.{len(tasks)+1}",
            "phase": phase or ("Phase 1" if wbs_id.startswith("1.") else "Phase 2"),
            "task_description": task_desc or f"WBS Task {wbs_id}",
            "module": module,
            "deliverable": deliverable,
            "period": period or computed_span,
            "active_span": computed_span,
            "active_months": sorted(list(active_months)),
            "status": status,
            "weeks": weeks,
        })

    return tasks


# ==============================================================================
# TAB 3: Objectives & KPI Alignment (GO-0, SO-1 .. SO-7)
# ==============================================================================

def _split_phase_and_window(raw_phase_win: str, raw_window: str = "") -> tuple[str, str]:
    """Splits combined 'Phase 1: Ch 1–3 (Oct W2 – Oct W4, 2026)' into (phase, window)."""
    p = raw_phase_win.strip()
    w = raw_window.strip()
    if w:
        return p, w
    m = re.match(r"^(.+?)\s*\(([^()]+)\)\s*$", p)
    if m:
        cand_phase = m.group(1).strip()
        cand_win = m.group(2).strip()
        # Check if parenthesized part looks like a calendar window (month / week / year)
        if any(k in cand_win.lower() for k in ("jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec", "w1", "w2", "w3", "w4", "2026", "2027")):
            return cand_phase, cand_win
    return p, w


def parse_objectives_sheet(grid: dict[tuple[int, int], dict[str, Any]]) -> list[dict[str, Any]]:
    """Extracts Objectives & KPI Alignment (supports both remodeled 10-column GO-0..SO-7 and legacy 8-column SO-1..SO-7)."""
    if not grid:
        return []

    max_row = max(r for r, _ in grid.keys()) if grid else 1
    header_row = None
    col_map: dict[str, int] = {}

    for r in range(1, min(max_row + 1, 15)):
        row_vals = {c: grid.get((r, c), {}).get("value", "").strip() for c in range(1, 20)}
        non_empty = {c: v for c, v in row_vals.items() if v}
        if len(non_empty) < 4:
            continue

        row_lower = {c: v.lower() for c, v in non_empty.items()}
        found_obj_id = any("obj id" in v or v in ("id", "objective id") for v in row_lower.values())
        found_status = any("status" in v for v in row_lower.values())

        if found_obj_id or (found_status and any("kpi" in v or "benchmark" in v for v in row_lower.values())):
            header_row = r
            for c, text in non_empty.items():
                tl = text.lower()
                if "obj id" in tl or tl in {"id", "objective id", "so"}:
                    col_map["obj_id"] = c
                elif "task filter" in tl or "action category" in tl:
                    col_map["task_filter_type"] = c
                elif "evaluation metric filter" in tl or "metric filter" in tl or "metric category" in tl:
                    col_map["metric_category"] = c
                elif "objective statement" in tl or "study objective" in tl or ("objective" in tl and "filter" not in tl and "id" not in tl):
                    col_map["statement"] = c
                elif "shared team goal" in tl or "measurable task" in tl or "friendly action" in tl:
                    col_map["team_goal"] = c
                elif "architectural" in tl or "system scope" in tl or "component" in tl:
                    col_map["component"] = c
                elif "dataset" in tl or "test condition" in tl or ("scope" in tl and "system scope" not in tl):
                    col_map["scope"] = c
                elif "kpi" in tl or "benchmark" in tl:
                    col_map["kpi"] = c
                elif "primary phase" in tl and "window" in tl:
                    col_map["phase_and_window"] = c
                elif "primary phase" in tl or tl == "phase":
                    col_map["phase"] = c
                elif "scheduled window" in tl or tl == "window" or "schedule" in tl:
                    col_map["window"] = c
                elif tl == "status" or "current status" in tl:
                    col_map["status"] = c
            break

    if header_row is None:
        header_row = 4

    # Detect whether this sheet is 10-column (remodeled) or 8-column (legacy)
    is_remodeled_10col = (
        "task_filter_type" in col_map
        or "team_goal" in col_map
        or "phase_and_window" in col_map
        or col_map.get("status", 0) >= 10
    )

    if is_remodeled_10col:
        col_map.setdefault("obj_id", 1)
        col_map.setdefault("task_filter_type", 2)
        col_map.setdefault("metric_category", 3)
        col_map.setdefault("statement", 4)
        col_map.setdefault("team_goal", 5)
        col_map.setdefault("component", 6)
        col_map.setdefault("scope", 7)
        col_map.setdefault("kpi", 8)
        col_map.setdefault("phase_and_window", 9)
        col_map.setdefault("status", 10)
    else:
        col_map.setdefault("obj_id", 1)
        col_map.setdefault("statement", 2)
        col_map.setdefault("component", 3)
        col_map.setdefault("scope", 4)
        col_map.setdefault("kpi", 5)
        col_map.setdefault("phase", 6)
        col_map.setdefault("window", 7)
        col_map.setdefault("status", 8)

    objectives = []
    for r in range(header_row + 1, max_row + 1):
        obj_id = grid.get((r, col_map["obj_id"]), {}).get("value", "").strip()
        stmt = grid.get((r, col_map["statement"]), {}).get("value", "").strip()

        if not obj_id and not stmt:
            continue
        # Strictly require GO-X or SO-X or numeric ID (never header or subtitle rows)
        if obj_id:
            if not (re.match(r"^(?:GO|SO)-\d+$", obj_id, re.I) or obj_id.isdigit()):
                continue
        else:
            continue

        task_filter = grid.get((r, col_map["task_filter_type"]), {}).get("value", "").strip() if "task_filter_type" in col_map else ""
        metric_cat = grid.get((r, col_map["metric_category"]), {}).get("value", "").strip() if "metric_category" in col_map else ""
        team_goal = grid.get((r, col_map["team_goal"]), {}).get("value", "").strip() if "team_goal" in col_map else ""
        component = grid.get((r, col_map["component"]), {}).get("value", "").strip()
        scope = grid.get((r, col_map["scope"]), {}).get("value", "").strip()
        kpi = grid.get((r, col_map["kpi"]), {}).get("value", "").strip()

        if "phase_and_window" in col_map:
            raw_pw = grid.get((r, col_map["phase_and_window"]), {}).get("value", "").strip()
            phase, window = _split_phase_and_window(raw_pw)
        else:
            raw_p = grid.get((r, col_map.get("phase", 6)), {}).get("value", "").strip()
            raw_w = grid.get((r, col_map.get("window", 7)), {}).get("value", "").strip()
            phase, window = _split_phase_and_window(raw_p, raw_w)

        raw_status = grid.get((r, col_map["status"]), {}).get("value", "").strip()
        status = _normalize_status(raw_status)

        objectives.append({
            "obj_id": obj_id.upper(),
            "task_filter_type": task_filter,
            "metric_category": metric_cat,
            "statement": stmt or f"Study Objective {obj_id}",
            "team_goal": team_goal,
            "component": component,
            "dataset_scope": scope,
            "target_kpi": kpi,
            "primary_phase": phase or ("Phase 1" if len(objectives) < 4 else "Phase 2"),
            "scheduled_window": window,
            "status": status,
        })

    return objectives


# ==============================================================================
# TAB 4: Live Rollup Metric Calculations & Quantitative Target Parsing
# ==============================================================================

def parse_dashboard_sheet_targets(
    grid: dict[tuple[int, int], dict[str, Any]],
    obj_by_id: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    """Extracts Quantitative Evaluation Targets (Rows 12-17) from Tab 4 if present."""
    if not grid:
        return []

    max_row = max(r for r, _ in grid.keys()) if grid else 1
    target_header_row = None
    for r in range(1, max_row + 1):
        c1_val = grid.get((r, 1), {}).get("value", "").strip().lower()
        c2_val = grid.get((r, 2), {}).get("value", "").strip().lower()
        if "evaluation metric" in c1_val and ("target benchmark" in c2_val or "criterion" in c2_val):
            target_header_row = r
            break

    if target_header_row is None:
        return []

    parsed_targets: list[dict[str, Any]] = []
    for r in range(target_header_row + 1, max_row + 1):
        metric_name = grid.get((r, 1), {}).get("value", "").strip()
        criterion = grid.get((r, 2), {}).get("value", "").strip()
        sample_cond = grid.get((r, 3), {}).get("value", "").strip()
        chapter_ref = grid.get((r, 4), {}).get("value", "").strip()
        filter_type = grid.get((r, 5), {}).get("value", "").strip()

        if not metric_name or not criterion:
            continue

        m_so = re.search(r"(SO-\d+)", chapter_ref, re.I)
        so_id = m_so.group(1).upper() if m_so else f"SO-{len(parsed_targets) + 4}"
        obj_status = obj_by_id.get(so_id, {}).get("status", "Pending")

        parsed_targets.append({
            "id": so_id,
            "name": metric_name,
            "component": filter_type or chapter_ref,
            "target": criterion,
            "sample": sample_cond,
            "chapter": chapter_ref,
            "status": obj_status,
        })

    return parsed_targets


def compute_dashboard_metrics(
    roadmap: list[dict[str, Any]],
    wbs: list[dict[str, Any]],
    objectives: list[dict[str, Any]],
    dashboard_grid: dict[tuple[int, int], dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Computes exact live rollup metrics from parsed sheets in plain Python."""
    def _summarize(items: list[dict[str, Any]]) -> dict[str, Any]:
        tot = len(items)
        c = sum(1 for x in items if x["status"] == "Completed")
        p = sum(1 for x in items if x["status"] == "In Progress")
        pend = sum(1 for x in items if x["status"] == "Pending")
        pct = round((c / tot) * 100, 1) if tot > 0 else 0.0
        return {
            "total": tot,
            "completed": c,
            "in_progress": p,
            "pending": pend,
            "completion_pct": pct,
        }

    # 1. General Roadmap Rollup
    roadmap_summary = _summarize(roadmap)
    roadmap_summary["label"] = f"General 8-Month Roadmap ({len(roadmap)} Stages)"

    # 2. Detailed WBS Rollups: Phase 1 & Phase 2
    p1_tasks = [t for t in wbs if t["wbs_id"].startswith("1.") or "phase 1" in t["phase"].lower()]
    p2_tasks = [t for t in wbs if t["wbs_id"].startswith("2.") or "phase 2" in t["phase"].lower()]

    p1_summary = _summarize(p1_tasks)
    p1_summary["deadline"] = "2nd Week of Dec 2026"
    p1_summary["label"] = "Phase 1: Chapters 1-3 & Core Dev"

    p2_summary = _summarize(p2_tasks)
    p2_summary["deadline"] = "Feb 2027"
    p2_summary["label"] = "Phase 2: Evaluation & Chapters 4-6"

    wbs_overall = _summarize(wbs)
    wbs_overall["label"] = f"Overall Detailed WBS ({len(wbs)} Tasks)"

    # 3. Study Objectives Rollup (GO-0 + SO-1..SO-7)
    obj_summary = _summarize(objectives)
    obj_summary["label"] = f"Chapter 1.3 Study Objectives ({len(objectives)} Objectives)"

    # 4. Quantitative Benchmark Targets (SO-4 to SO-7)
    obj_by_id = {o["obj_id"].upper(): o for o in objectives}
    quantitative_targets = parse_dashboard_sheet_targets(dashboard_grid or {}, obj_by_id)

    if not quantitative_targets:
        quantitative_targets = [
            {
                "id": "SO-4",
                "name": "Citizen Return-Trip Prevention",
                "component": "Neo4j DAG Verification",
                "target": ">= 90%",
                "target_num": 90,
                "unit": "%",
                "status": obj_by_id.get("SO-4", {}).get("status", "Pending"),
            },
            {
                "id": "SO-4",
                "name": "Exact-Match Citizen Resolution",
                "component": "Prerequisite Graph Walk",
                "target": ">= 95%",
                "target_num": 95,
                "unit": "%",
                "status": obj_by_id.get("SO-4", {}).get("status", "Pending"),
            },
            {
                "id": "SO-5",
                "name": "Gap Analysis Metric (M = R \\ H)",
                "component": "M = R \\ H Topological Engine",
                "target": ">= 90%",
                "target_num": 90,
                "unit": "%",
                "status": obj_by_id.get("SO-5", {}).get("status", "Pending"),
            },
            {
                "id": "SO-6",
                "name": "Topological Sequence Accuracy",
                "component": "Topological Sorter / DAG",
                "target": ">= 90%",
                "target_num": 90,
                "unit": "%",
                "status": obj_by_id.get("SO-6", {}).get("status", "Pending"),
            },
            {
                "id": "SO-6",
                "name": "Post-AST Execution Guardrail",
                "component": "Python AST Validator",
                "target": ">= 95%",
                "target_num": 95,
                "unit": "%",
                "status": obj_by_id.get("SO-6", {}).get("status", "Pending"),
            },
            {
                "id": "SO-7",
                "name": "Edge Query Latency",
                "component": "Local Neo4j Graph DB",
                "target": "<= 5.0s",
                "target_num": 5.0,
                "unit": "s",
                "status": obj_by_id.get("SO-7", {}).get("status", "Pending"),
            },
        ]

    return {
        "roadmap": roadmap_summary,
        "phase_1": p1_summary,
        "phase_2": p2_summary,
        "overall_wbs": wbs_overall,
        "objectives": obj_summary,
        "quantitative_targets": quantitative_targets,
    }


# ==============================================================================
# Legacy Timeline & Team Quotas (Backward Compatibility)
# ==============================================================================

def parse_timeline_sheet(grid: dict[tuple[int, int], dict[str, Any]]) -> list[dict[str, Any]]:
    """Extracts #, Phase / Task, Deliverable, and Month 1..Month 7 from legacy Timeline grid."""
    if not grid:
        return []

    header_row = None
    num_col = 1
    task_col = 2
    deliv_col = 3
    month_cols: dict[int, int] = {}

    max_row = max(r for r, _ in grid.keys()) if grid else 1
    for r in range(1, min(max_row + 1, 10)):
        row_vals = {c: grid.get((r, c), {}).get("value", "").lower() for c in range(1, 20)}
        found_num = any(text in ("#", "no", "id", "task #", "phase #") for text in row_vals.values())
        found_task = any("phase" in text or "task" in text for text in row_vals.values())
        found_month = any("month" in text or "m1" in text for text in row_vals.values())
        if (found_num or found_task) and found_month:
            header_row = r
            for c, text in row_vals.items():
                if text in ("#", "no", "id", "task #", "phase #"):
                    num_col = c
                elif "phase" in text or "task" in text:
                    task_col = c
                elif "deliverable" in text or "output" in text:
                    deliv_col = c
                for m in range(1, 8):
                    if f"month {m}" in text or f"m{m}" in text or f"month {m:02d}" in text:
                        month_cols[m] = c
            break

    if header_row is None:
        header_row = 1

    if not month_cols:
        for m in range(1, 8):
            month_cols[m] = 3 + m

    tasks = []
    for r in range(header_row + 1, max_row + 1):
        num_cell = grid.get((r, num_col), {}).get("value", "")
        task_cell = grid.get((r, task_col), {}).get("value", "")
        deliv_cell = grid.get((r, deliv_col), {}).get("value", "")

        if not num_cell and not task_cell:
            continue

        months = []
        for m in range(1, 8):
            c_idx = month_cols.get(m, 3 + m)
            cell = grid.get((r, c_idx), {"value": "", "color": None})
            classified = _classify_month_cell(cell)
            classified["month"] = m
            months.append(classified)

        tasks.append({
            "number": int(num_cell) if num_cell.isdigit() else (len(tasks) + 1),
            "task": task_cell or f"Task {len(tasks) + 1}",
            "deliverable": deliv_cell,
            "months": months,
        })

    return tasks


def parse_team_tasks_sheet(
    grid: dict[tuple[int, int], dict[str, Any]],
    audit: Audit | None = None,
    now_ts: int | None = None,
) -> list[dict[str, Any]]:
    """Extracts team quotas from Team_Tasks sheet and syncs with SQLite Audit."""
    if not grid:
        return []

    max_row = max(r for r, _ in grid.keys()) if grid else 1
    header_row = None
    col_map: dict[str, int] = {}

    for r in range(1, min(max_row + 1, 10)):
        row_vals = {c: grid.get((r, c), {}).get("value", "").lower().replace(" ", "_") for c in range(1, 20)}
        found_team = any("team" in text for text in row_vals.values())
        found_quota = any("count" in text or "quota" in text or "target" in text for text in row_vals.values())
        if found_team or found_quota:
            header_row = r
            for c, text in row_vals.items():
                if "task_id" in text or text == "id":
                    col_map["task_id"] = c
                elif "team" in text:
                    col_map["assigned_team"] = c
                elif "email" in text:
                    col_map["owner_email"] = c
                elif "task_name" in text or "name" in text or text == "task":
                    col_map["task_name"] = c
                elif "current" in text or "count" in text or "done" in text or "completed" in text:
                    if "target" not in text:
                        col_map["current_count"] = c
                elif "target" in text or "total" in text or "quota" in text or "goal" in text:
                    col_map["target_count"] = c
                elif "updated" in text or "date" in text:
                    col_map["last_updated"] = c
            break

    if header_row is None:
        header_row = 1

    col_map.setdefault("task_id", 1)
    col_map.setdefault("assigned_team", 2)
    col_map.setdefault("owner_email", 3)
    col_map.setdefault("task_name", 4)
    col_map.setdefault("current_count", 5)
    col_map.setdefault("target_count", 6)
    col_map.setdefault("last_updated", 7)

    results = []
    for r in range(header_row + 1, max_row + 1):
        task_id = grid.get((r, col_map["task_id"]), {}).get("value", "")
        team = grid.get((r, col_map["assigned_team"]), {}).get("value", "")
        email = grid.get((r, col_map["owner_email"]), {}).get("value", "")
        name = grid.get((r, col_map["task_name"]), {}).get("value", "")
        curr_raw = grid.get((r, col_map["current_count"]), {}).get("value", "0")
        tgt_raw = grid.get((r, col_map["target_count"]), {}).get("value", "0")
        updated_raw = grid.get((r, col_map["last_updated"]), {}).get("value", "")

        if not task_id and not name:
            continue

        try:
            curr_val = float(curr_raw)
        except ValueError:
            curr_val = 0.0

        try:
            tgt_val = float(tgt_raw)
        except ValueError:
            tgt_val = 0.0

        if audit is not None:
            state = audit.sync_team_task_state(
                task_id=task_id or f"TASK-{len(results)+1}",
                assigned_team=team or "General Team",
                owner_email=email,
                task_name=name or "Assigned Task",
                current_count=curr_val,
                target_count=tgt_val,
                last_updated=updated_raw,
                now_ts=now_ts,
            )
        else:
            pct = round((curr_val / tgt_val) * 100, 1) if tgt_val > 0 else 0.0
            state = {
                "task_id": task_id,
                "assigned_team": team,
                "owner_email": email,
                "task_name": name,
                "current_count": curr_val,
                "target_count": tgt_val,
                "progress_pct": pct,
                "last_change_ts": 0,
                "last_notified_ts": 0,
                "days_since_update": 0.0,
                "stale": False,
                "snoozed": False,
            }
        results.append(state)

    return results


# ==============================================================================
# Google Drive Spreadsheet Export, Cross-Reference & Diff Engine
# ==============================================================================

def extract_gdrive_file_id(url: str) -> str | None:
    """Extracts the Google Spreadsheet / Drive file ID from a URL (ignores folder URLs)."""
    if not url or "/drive/folders/" in url:
        return None
    m = re.search(r"/(?:spreadsheets|file)/d/([a-zA-Z0-9_-]{15,})", url)
    if m:
        return m.group(1)
    m_id = re.search(r"[?&]id=([a-zA-Z0-9_-]{15,})", url)
    if m_id:
        return m_id.group(1)
    return None


def fetch_gdrive_excel_bytes(
    settings: Settings | None = None,
    timeout: int = 8,
    force: bool = False,
) -> tuple[bytes | None, dict[str, Any]]:
    """Downloads the live .xlsx bytes from Google Sheets / Google Drive if configured."""
    folder_url = (
        settings.team_gdrive_folder_url
        if settings and settings.team_gdrive_folder_url
        else os.environ.get("NIGHTMARE_TEAM_GDRIVE_FOLDER_URL", "").strip().strip('"\'') or DEFAULT_GDRIVE_URL
    )
    sync_path = settings.team_gdrive_sync_path if settings else None
    sync_exists = bool(sync_path and sync_path.exists())
    sync_file_str = str(sync_path) if sync_exists else None

    file_id = extract_gdrive_file_id(folder_url)
    now = time.monotonic()

    if not force and folder_url in _GDRIVE_CACHE:
        cached_ts, cached_bytes, cached_info = _GDRIVE_CACHE[folder_url]
        if now - cached_ts < _GDRIVE_CACHE_TTL:
            return cached_bytes, dict(cached_info)

    export_url = f"https://docs.google.com/spreadsheets/d/{file_id}/export?format=xlsx" if file_id else None
    xlsx_bytes: bytes | None = None
    url_reachable = False
    status_code = None

    if export_url:
        for candidate_url in (
            export_url,
            f"https://drive.google.com/uc?export=download&id={file_id}",
        ):
            try:
                req = urllib.request.Request(
                    candidate_url,
                    headers={"User-Agent": "Mozilla/5.0 Nightmare/1.0"},
                )
                with urllib.request.urlopen(req, timeout=timeout) as resp:
                    status_code = getattr(resp, "status", 200)
                    raw = resp.read()
                    url_reachable = (status_code == 200)
                    if isinstance(raw, bytes) and raw[:2] == b"PK":
                        xlsx_bytes = raw
                        break
            except Exception as exc:
                logger.debug("GDrive export download failed (%s): %s", candidate_url, exc)

    if not url_reachable:
        try:
            req = urllib.request.Request(
                folder_url,
                headers={"User-Agent": "Mozilla/5.0 Nightmare/1.0"},
            )
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                status_code = getattr(resp, "status", 200)
                url_reachable = (status_code == 200)
        except Exception as exc:
            logger.debug("GDrive reachability check failed (offline/timeout): %s", exc)
            url_reachable = False

    info = {
        "folder_url": folder_url,
        "file_id": file_id,
        "export_url": export_url,
        "sync_path": sync_file_str,
        "sync_exists": sync_exists,
        "reachable": url_reachable,
        "xlsx_downloaded": xlsx_bytes is not None,
        "xlsx_size": len(xlsx_bytes) if xlsx_bytes else 0,
        "status": "synced" if (sync_exists or xlsx_bytes is not None) else ("reachable" if url_reachable else "offline"),
        "status_code": status_code,
    }
    _GDRIVE_CACHE[folder_url] = (now, xlsx_bytes, info)
    return xlsx_bytes, info


def check_gdrive_source(settings: Settings | None = None) -> dict[str, Any]:
    """Checks Google Drive spreadsheet / folder reachability and export status."""
    _, info = fetch_gdrive_excel_bytes(settings=settings, timeout=6, force=False)
    return info


def _hash_record(rec: dict[str, Any]) -> str:
    key_fields = f"{rec.get('item_key')}|{rec.get('sheet_name')}|{rec.get('title')}|{rec.get('status')}|{rec.get('period')}|{rec.get('deliverable')}"
    return hashlib.sha256(key_fields.encode("utf-8")).hexdigest()[:12]


def _build_state_items(
    roadmap: list[dict[str, Any]],
    wbs: list[dict[str, Any]],
    objectives: list[dict[str, Any]],
    now_int: int,
) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for s in roadmap:
        rec = {
            "item_key": s["stage_id"],
            "sheet_name": "roadmap",
            "title": s["title"],
            "phase": s["phase"],
            "status": s["status"],
            "period": s["calendar_span"],
            "deliverable": s["milestone"],
            "updated_at": now_int,
        }
        rec["source_hash"] = _hash_record(rec)
        items.append(rec)

    for t in wbs:
        rec = {
            "item_key": t["wbs_id"],
            "sheet_name": "wbs",
            "title": t["task_description"],
            "phase": t["phase"],
            "status": t["status"],
            "period": t["period"],
            "deliverable": t["deliverable"],
            "updated_at": now_int,
        }
        rec["source_hash"] = _hash_record(rec)
        items.append(rec)

    for o in objectives:
        rec = {
            "item_key": o["obj_id"],
            "sheet_name": "objectives",
            "title": o["statement"],
            "phase": o["primary_phase"],
            "status": o["status"],
            "period": o["scheduled_window"],
            "deliverable": o["target_kpi"],
            "updated_at": now_int,
        }
        rec["source_hash"] = _hash_record(rec)
        items.append(rec)
    return items


def compare_timeline_sources(
    current_items: list[dict[str, Any]],
    audit: Audit | None = None,
    settings: Settings | None = None,
    current_dashboard: dict[str, Any] | None = None,
    gdrive_items: list[dict[str, Any]] | None = None,
    gdrive_info: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Compares current timeline items (and optional live GDrive items) against stored baseline in SQLite Audit."""
    if gdrive_info is None:
        gdrive_info = check_gdrive_source(settings)

    if audit is None:
        return {
            "has_changes": False,
            "change_count": 0,
            "changes": [],
            "status_transitions": [],
            "schedule_shifts": [],
            "deliverable_edits": [],
            "completion_deltas": {},
            "spoken_summary": "Cross-referencing the CitizenGraph timeline against the baseline. Baseline store not connected.",
            "gdrive_info": gdrive_info,
        }

    baseline_rows = audit.get_timeline_baseline()
    # Auto-heal corrupted legacy baseline if it contains footer/header rows or outdated v2 schema count
    has_corrupted_rows = any(
        r["item_key"] in ("Completed Stages", "In Progress Stages", "Pending Stages", "Obj ID")
        or r["item_key"].startswith("Direct Traceability")
        or r["title"] == r["item_key"]
        for r in baseline_rows
    )
    if (not baseline_rows or has_corrupted_rows) and current_items:
        audit.commit_timeline_baseline(current_items)
        baseline_rows = audit.get_timeline_baseline()

    base_map = {(r["sheet_name"], r["item_key"]): r for r in baseline_rows}

    # If live GDrive items were fetched and differ from local current_items, compare GDrive against baseline
    effective_items = gdrive_items if gdrive_items else current_items

    status_transitions = []
    schedule_shifts = []
    deliverable_edits = []
    all_changes = []

    for curr in effective_items:
        key = (curr["sheet_name"], curr["item_key"])
        base = base_map.get(key)
        if not base:
            item_ch = {
                "item_key": curr["item_key"],
                "sheet_name": curr["sheet_name"],
                "title": curr["title"],
                "phase": curr.get("phase", ""),
                "type": "item_added",
                "old_val": "None",
                "new_val": curr["status"],
                "detail": f"{curr['item_key']} {curr['title']} added ({curr['status']})",
            }
            all_changes.append(item_ch)
            continue

        # 1. Status transition
        if curr["status"].strip().lower() != base["status"].strip().lower():
            ch = {
                "item_key": curr["item_key"],
                "sheet_name": curr["sheet_name"],
                "title": curr["title"],
                "phase": curr.get("phase", ""),
                "type": "status_transition",
                "old_val": base["status"],
                "new_val": curr["status"],
                "detail": f"{curr['item_key']} {curr['title']} moved from {base['status']} to {curr['status']}",
            }
            status_transitions.append(ch)
            all_changes.append(ch)

        # 2. Period / schedule shift
        curr_p = curr.get("period", "").strip().lower()
        base_p = base.get("period", "").strip().lower()
        if curr_p and base_p and curr_p != base_p:
            ch = {
                "item_key": curr["item_key"],
                "sheet_name": curr["sheet_name"],
                "title": curr["title"],
                "phase": curr.get("phase", ""),
                "type": "period_shift",
                "old_val": base.get("period", ""),
                "new_val": curr.get("period", ""),
                "detail": f"{curr['item_key']} schedule shifted from {base.get('period', '')} to {curr.get('period', '')}",
            }
            schedule_shifts.append(ch)
            all_changes.append(ch)

        # 3. Deliverable / text edit
        curr_d = curr.get("deliverable", "").strip()
        base_d = base.get("deliverable", "").strip()
        if curr_d and base_d and curr_d != base_d:
            ch = {
                "item_key": curr["item_key"],
                "sheet_name": curr["sheet_name"],
                "title": curr["title"],
                "phase": curr.get("phase", ""),
                "type": "deliverable_edit",
                "old_val": base_d,
                "new_val": curr_d,
                "detail": f"{curr['item_key']} deliverable updated",
            }
            deliverable_edits.append(ch)
            all_changes.append(ch)

    # Compute baseline rollups for delta
    base_wbs = [r for r in baseline_rows if r["sheet_name"] == "wbs"]
    base_p1 = [r for r in base_wbs if r["item_key"].startswith("1.")]
    base_p1_comp = sum(1 for r in base_p1 if r["status"].lower() == "completed")
    base_p1_pct = round((base_p1_comp / len(base_p1)) * 100, 1) if base_p1 else 0.0

    curr_p1_pct = (current_dashboard or {}).get("phase_1", {}).get("completion_pct", base_p1_pct)
    curr_p1_comp = (current_dashboard or {}).get("phase_1", {}).get("completed", base_p1_comp)

    comp_delta = {
        "phase_1": {
            "old_pct": base_p1_pct,
            "new_pct": curr_p1_pct,
            "delta_pct": round(curr_p1_pct - base_p1_pct, 1),
            "completed_delta": curr_p1_comp - base_p1_comp,
        }
    }

    # Spoken summary formatting
    count = len(all_changes)
    if count > 0:
        parts = []
        for ch in status_transitions[:2]:
            parts.append(f"{ch['item_key']} {ch['title']} moved from {ch['old_val']} to {ch['new_val']}")
        for ch in deliverable_edits[:1]:
            parts.append(f"{ch['item_key']} status updated")
        for ch in schedule_shifts[:1]:
            if len(parts) < 2:
                parts.append(f"{ch['item_key']} schedule shifted")
        if not parts:
            parts.append(all_changes[0]["detail"])

        summary_detail = ", and ".join(parts) if len(parts) > 1 else parts[0]
        spoken = (
            f"Cross-referencing the CitizenGraph timeline against the baseline. "
            f"{count} items changed: {summary_detail}. Phase 1 is now at {curr_p1_pct:.0f}% completion. "
            f"Opening the Timeline Diff tab."
        )
    else:
        spoken = (
            f"Cross-referencing the CitizenGraph timeline against the baseline. "
            f"Timeline is up to date with 0 changes detected. Phase 1 is at {curr_p1_pct:.1f}% completion. "
            f"Opening the Timeline Diff tab."
        )

    gdrive_info_out = dict(gdrive_info) if gdrive_info else {}
    if gdrive_items is not None:
        gdrive_info_out["status"] = "gdrive_changes_detected" if count > 0 else "in_sync_with_gdrive"

    return {
        "has_changes": count > 0,
        "change_count": count,
        "changes": all_changes,
        "status_transitions": status_transitions,
        "schedule_shifts": schedule_shifts,
        "deliverable_edits": deliverable_edits,
        "completion_deltas": comp_delta,
        "spoken_summary": spoken,
        "gdrive_info": gdrive_info_out,
    }


# ==============================================================================
# Full Scan and Sync Orchestrator
# ==============================================================================

def _parse_workbook_reader(
    reader: OpenXMLSheetReader,
    audit: Audit | None = None,
    now_ts: int | None = None,
) -> tuple[list[dict], list[dict], list[dict], dict, list[dict], list[dict]]:
    # 1. Parse Tab 1: General 8-Month Roadmap
    roadmap_grid = reader.read_sheet("general 8-month roadmap", "roadmap", "general")
    roadmap = parse_roadmap_sheet(roadmap_grid)

    # 2. Parse Tab 2: Detailed Weekly Gantt
    wbs_grid = reader.read_sheet("detailed weekly gantt", "weekly gantt", "gantt")
    wbs = parse_weekly_gantt_sheet(wbs_grid)

    # 3. Parse Tab 3: Objectives & KPI Alignment
    obj_grid = reader.read_sheet("objectives & kpi alignment", "objectives", "kpi")
    objectives = parse_objectives_sheet(obj_grid)

    # 4. Parse Tab 4 & Compute Live Rollups
    dash_grid = reader.read_sheet("phase summary & dashboard", "phase summary", "dashboard")
    dashboard = compute_dashboard_metrics(roadmap, wbs, objectives, dashboard_grid=dash_grid)

    # 5. Legacy Timeline sheet check (if new tabs absent)
    legacy_timeline_grid = reader.read_sheet("timeline")
    legacy_timeline = parse_timeline_sheet(legacy_timeline_grid) if legacy_timeline_grid else []

    # 6. Parse Team_Tasks sheet (quotas & 3-day stale tracking)
    tasks_grid = reader.read_sheet("team_tasks", "tasks")
    quotas = parse_team_tasks_sheet(tasks_grid, audit=audit, now_ts=now_ts)

    return roadmap, wbs, objectives, dashboard, legacy_timeline, quotas


def _should_use_live_gdrive(
    settings: Settings | None,
    resolved_path: Path | None,
    explicit_excel_supplied: bool = False,
) -> bool:
    """Returns True when live Google Drive spreadsheet export should be queried."""
    if explicit_excel_supplied:
        return False
    if settings and settings.team_gdrive_folder_url and settings.team_gdrive_folder_url != DEFAULT_GDRIVE_URL:
        return True
    if resolved_path is None:
        return True
    return resolved_path.name.lower() == DEFAULT_EXCEL_FILENAME.lower()


def sync_timeline_with_gdrive(
    settings: Settings | None = None,
    audit: Audit | None = None,
    pull_gdrive: bool = True,
) -> dict[str, Any]:
    """Pulls latest .xlsx from Google Drive (if reachable), updates local Excel file, and commits SQLite baseline."""
    resolved_path = resolve_team_excel_path(settings)
    if not resolved_path and settings and settings.team_excel_path:
        resolved_path = Path(settings.team_excel_path).expanduser()

    gdrive_synced_to_local = False
    gdrive_bytes: bytes | None = None
    gdrive_info: dict[str, Any] = {}

    if pull_gdrive and _should_use_live_gdrive(settings, resolved_path):
        gdrive_bytes, gdrive_info = fetch_gdrive_excel_bytes(settings=settings, timeout=10, force=True)
        if gdrive_bytes and resolved_path:
            try:
                resolved_path.parent.mkdir(parents=True, exist_ok=True)
                resolved_path.write_bytes(gdrive_bytes)
                gdrive_synced_to_local = True
            except OSError as exc:
                logger.warning("Could not write GDrive .xlsx to %s: %s", resolved_path, exc)

    scan = scan_team_progress(
        settings=settings,
        audit=audit,
        excel_path=resolved_path if (resolved_path and resolved_path.is_file()) else gdrive_bytes,
    )
    count = 0
    if audit is not None:
        now_int = int(datetime.now().timestamp())
        items = _build_state_items(
            scan.get("roadmap", []),
            scan.get("wbs", []),
            scan.get("objectives", []),
            now_int,
        )
        count = audit.commit_timeline_baseline(items)

    return {
        "ok": True,
        "committed_count": count,
        "gdrive_pulled": gdrive_synced_to_local,
        "gdrive_info": gdrive_info or scan.get("gdrive_info", {}),
        "file_path": str(resolved_path) if resolved_path else None,
        "message": (
            f"Synced latest Google Drive spreadsheet to {resolved_path.name} and committed {count} baseline records."
            if gdrive_synced_to_local and resolved_path
            else f"Successfully updated baseline with {count} records."
        ),
    }


def scan_team_progress(
    settings: Settings | None = None,
    audit: Audit | None = None,
    excel_path: Path | bytes | None = None,
    team_filter: str | None = None,
    now_ts: int | None = None,
) -> dict[str, Any]:
    """Full scan and sync of the 4-tab timeline, baseline diff, and team quotas."""
    resolved_path: Path | None = None
    explicit_excel_supplied = excel_path is not None

    if isinstance(excel_path, bytes):
        reader = OpenXMLSheetReader(excel_path)
    elif excel_path is not None:
        resolved_path = Path(excel_path)
        if not resolved_path.is_file():
            return {
                "ok": False,
                "error": f"Excel file not found at {resolved_path}",
                "roadmap": [],
                "wbs": [],
                "objectives": [],
                "dashboard": {},
                "timeline": [],
                "quotas": [],
                "stale_tasks": [],
            }
        reader = OpenXMLSheetReader(resolved_path)
    else:
        resolved_path = resolve_team_excel_path(settings)
        if not resolved_path or not resolved_path.is_file():
            # Fallback: try live Google Drive export bytes if local file is missing
            gd_bytes, _ = fetch_gdrive_excel_bytes(settings=settings, timeout=8)
            if gd_bytes:
                if settings and settings.team_excel_path:
                    try:
                        target_p = Path(settings.team_excel_path).expanduser()
                        target_p.parent.mkdir(parents=True, exist_ok=True)
                        target_p.write_bytes(gd_bytes)
                        resolved_path = target_p
                    except OSError:
                        pass
                reader = OpenXMLSheetReader(gd_bytes)
            else:
                return {
                    "ok": False,
                    "error": "No timeline Excel file found. Set NIGHTMARE_TEAM_EXCEL_PATH in backend/.env.",
                    "roadmap": [],
                    "wbs": [],
                    "objectives": [],
                    "dashboard": {},
                    "timeline": [],
                    "quotas": [],
                    "stale_tasks": [],
                }
        else:
            reader = OpenXMLSheetReader(resolved_path)

    roadmap, wbs, objectives, dashboard, legacy_timeline, quotas = _parse_workbook_reader(
        reader, audit=audit, now_ts=now_ts
    )

    filtered_quotas = quotas
    if team_filter:
        norm = team_filter.strip().lower()
        filtered_quotas = [
            q for q in quotas if norm in q["assigned_team"].lower() or norm in q["task_name"].lower()
        ]

    stale_tasks = [q for q in quotas if q.get("stale") and not q.get("snoozed")]

    now_int = int(now_ts or datetime.now().timestamp())
    current_items = _build_state_items(roadmap, wbs, objectives, now_int)

    # Sync current items to SQLite as current state (is_baseline = 0)
    if audit is not None and current_items:
        audit.upsert_timeline_state(current_items, is_baseline=0)

    # Check live Google Drive source (and parse GDrive items when scanning the live configured workbook)
    gdrive_items: list[dict[str, Any]] | None = None
    gdrive_info: dict[str, Any] | None = None
    if _should_use_live_gdrive(settings, resolved_path, explicit_excel_supplied):
        gdrive_bytes, gdrive_info = fetch_gdrive_excel_bytes(settings=settings, timeout=6)
        if gdrive_bytes:
            try:
                gd_reader = OpenXMLSheetReader(gdrive_bytes)
                gd_roadmap, gd_wbs, gd_obj, _, _, _ = _parse_workbook_reader(gd_reader, audit=None, now_ts=now_ts)
                if gd_roadmap or gd_wbs or gd_obj:
                    gdrive_items = _build_state_items(gd_roadmap, gd_wbs, gd_obj, now_int)
            except Exception as exc:
                logger.debug("Failed parsing GDrive workbook bytes: %s", exc)
    else:
        gdrive_info = {
            "folder_url": (settings.team_gdrive_folder_url if settings else DEFAULT_GDRIVE_URL),
            "sync_path": str(settings.team_gdrive_sync_path) if (settings and settings.team_gdrive_sync_path) else None,
            "sync_exists": bool(settings and settings.team_gdrive_sync_path and settings.team_gdrive_sync_path.exists()),
            "reachable": True,
            "status": "local_cache",
        }

    # Run Cross-Reference & Diff Engine
    diff = compare_timeline_sources(
        current_items,
        audit=audit,
        settings=settings,
        current_dashboard=dashboard,
        gdrive_items=gdrive_items,
        gdrive_info=gdrive_info,
    )

    # Backward compatibility: timeline points to wbs if roadmap/wbs present, else legacy
    effective_timeline = wbs if wbs else legacy_timeline

    return {
        "ok": True,
        "file_path": str(resolved_path) if resolved_path else "in_memory.xlsx",
        "file_name": resolved_path.name if resolved_path else DEFAULT_EXCEL_FILENAME,
        "roadmap": roadmap,
        "wbs": wbs,
        "objectives": objectives,
        "dashboard": dashboard,
        "timeline": effective_timeline,
        "quotas": filtered_quotas,
        "all_quotas": quotas,
        "stale_tasks": stale_tasks,
        "diff": diff,
        "gdrive_info": diff.get("gdrive_info", {}),
        "summary": {
            "total_roadmap_stages": len(roadmap),
            "total_wbs_tasks": len(wbs),
            "total_objectives": len(objectives),
            "total_timeline_tasks": len(effective_timeline),
            "total_quotas": len(quotas),
            "stale_count": len(stale_tasks),
            "has_diff": diff.get("has_changes", False),
            "diff_count": diff.get("change_count", 0),
        },
    }
