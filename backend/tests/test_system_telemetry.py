"""Unit tests for Phase 9A System Hardware Telemetry & Thermal/Battery Cockpit."""
import asyncio
from pathlib import Path

from backend.config import Settings
from backend.core.actions import Registry
from backend.core.clearance import ClearanceManager
from backend.core.llm import NoLLMProvider
from backend.core.orchestrator import Orchestrator
from backend.core.router import route
from backend.tools.audit import Audit
from backend.tools.system_telemetry import (
    format_battery_spoken,
    format_processes_spoken,
    format_telemetry_spoken,
    get_cpu_load,
    get_memory_status,
    get_power_status,
    get_system_status,
    get_top_processes,
)


def _make_orch(tmp_path: Path):
    desktop = tmp_path / "desktop"
    desktop.mkdir(exist_ok=True)
    db_path = tmp_path / "n.db"
    apps_file = tmp_path / "apps.json"
    apps_file.write_text('{"apps": {}, "tasks": {}}')
    settings = Settings(
        desktop_root=desktop,
        api_token="t" * 32,
        db_path=db_path,
        apps_file=apps_file,
    )
    registry = Registry({"apps": {}, "tasks": {}})
    clearance = ClearanceManager()
    audit = Audit(db_path)
    orch = Orchestrator(
        settings=settings,
        provider=NoLLMProvider(),
        registry=registry,
        audit=audit,
        clearance=clearance,
    )
    return orch, settings, registry


def test_native_power_status_kernel32():
    status = get_power_status()
    assert isinstance(status, dict)
    assert "battery_percent" in status
    assert 0 <= status["battery_percent"] <= 100
    assert "ac_online" in status
    assert isinstance(status["ac_online"], bool)


def test_native_memory_status_kernel32():
    mem = get_memory_status()
    assert isinstance(mem, dict)
    assert mem["total_gb"] > 0
    assert mem["used_gb"] >= 0
    assert 0 <= mem["load_percent"] <= 100


def test_native_cpu_load_kernel32():
    cpu = get_cpu_load(sample_ms=50)
    assert isinstance(cpu, int)
    assert 0 <= cpu <= 100


def test_tasklist_processes():
    procs = get_top_processes(limit=4)
    assert isinstance(procs, list)
    if procs:
        name, mb = procs[0]
        assert isinstance(name, str)
        assert mb >= 0


def test_system_status_snapshot():
    snap = get_system_status()
    assert "cpu_percent" in snap
    assert "memory" in snap
    assert "power" in snap
    assert "top_processes" in snap
    assert snap["timestamp"] > 0


def test_formatters():
    snap = {
        "cpu_percent": 15,
        "memory": {"load_percent": 65, "total_gb": 16.0, "used_gb": 10.4, "free_gb": 5.6},
        "power": {"ac_online": True, "battery_percent": 85, "charging": True, "seconds_left": None},
    }
    spoken_tel = format_telemetry_spoken(snap)
    assert "CPU load is at 15%" in spoken_tel
    assert "10.4 gigabytes" in spoken_tel
    assert "85%" in spoken_tel

    spoken_bat = format_battery_spoken(snap)
    assert "85%" in spoken_bat
    assert "charging" in spoken_bat

    procs = [("chrome.exe", 2048.0), ("Antigravity IDE.exe", 1024.0)]
    spoken_proc = format_processes_spoken(procs)
    assert "Chrome using 2.0 gigabytes" in spoken_proc


def test_router_system_telemetry(tmp_path):
    _, settings, registry = _make_orch(tmp_path)

    for p in ["system status", "how is my laptop running", "check system status", "hardware telemetry", "how is the pc running"]:
        intent = route(p, settings, registry)
        assert intent.kind == "system_telemetry", f"Failed for '{p}', got {intent.kind}"

    for p in ["check battery", "battery status", "how is my battery", "check battery and thermals"]:
        intent = route(p, settings, registry)
        assert intent.kind == "system_battery", f"Failed for '{p}', got {intent.kind}"

    for p in ["what is using my memory", "which app is eating ram", "top processes", "heavy processes"]:
        intent = route(p, settings, registry)
        assert intent.kind == "system_processes", f"Failed for '{p}', got {intent.kind}"


def test_orchestrator_system_telemetry(tmp_path):
    orch, _, _ = _make_orch(tmp_path)

    rep = asyncio.run(orch.handle("system status", session="s1"))
    assert rep.intent == "system_telemetry"
    assert rep.ok
    assert "CPU load is at" in rep.text
    assert "RAM in use" in rep.text
    assert rep.ui == "system_telemetry"

    rep_bat = asyncio.run(orch.handle("check battery", session="s1"))
    assert rep_bat.intent == "system_battery"
    assert rep_bat.ok
    assert "Battery is" in rep_bat.text

    rep_proc = asyncio.run(orch.handle("what is using my memory", session="s1"))
    assert rep_proc.intent == "system_processes"
    assert rep_proc.ok
    assert "processes" in rep_proc.text


def test_readonly_phone_hardware_access(tmp_path):
    orch, _, _ = _make_orch(tmp_path)

    # Level 1 read-only sessions (e.g. phone companion) can query telemetry safely
    rep = asyncio.run(orch.handle("system status", readonly=True, session="phone"))
    assert rep.ok
    assert rep.intent == "system_telemetry"
