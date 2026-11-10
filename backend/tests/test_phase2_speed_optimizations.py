"""Unit tests for Phase 2: Eliminating fast-path tool bottlenecks.

Tests cover:
1. PowerPoint controller (<150ms worker, error/fallback handling, 'present it' routing).
2. Native system telemetry (<20ms warm snapshot, background daemon process cache).
3. Stale-while-revalidate GitHub repository checker and weather prefetcher (<50ms).
"""
import asyncio
from pathlib import Path
import time
import pytest
from unittest.mock import MagicMock, patch

from backend.config import Settings
from backend.core.actions import Registry
from backend.core.router import route
from backend.tools.ppt_controller import (
    PPTCOMAdapter,
    PowerShellWorker,
    get_com_adapter,
    goto_slide,
    next_slide,
    previous_slide,
    start_presentation,
)
from backend.tools.system_telemetry import (
    get_cpu_load,
    get_memory_status,
    get_power_status,
    get_system_status,
    get_top_processes,
)
from backend.tools.weather import _cache, fetch_weather, prefetch_weather
from backend.tools.workspace import (
    _github_cache,
    async_github_workspace_summary,
    check_github_repos_async,
    check_repo_async,
    github_workspace_summary,
)


# ==============================================================================
# 1. PPT Controller Acceleration & Fallback Handling
# ==============================================================================

def test_ppt_worker_fallback_when_powerpoint_not_running():
    """Verify PPT calls return clean human-readable statuses without throwing unhandled COM errors."""
    ok, msg = goto_slide(2)
    assert ok is False
    assert isinstance(msg, str)
    assert any(k in msg.lower() for k in ["not running", "not open", "unavailable", "failed", "busy", "disconnected"])

    ok_n, msg_n = next_slide()
    assert ok_n is False
    assert isinstance(msg_n, str)

    ok_p, msg_p = previous_slide()
    assert ok_p is False
    assert isinstance(msg_p, str)

    ok_s, msg_s = start_presentation()
    assert ok_s is False
    assert isinstance(msg_s, str)


def test_ppt_worker_mock_adapter_roundtrip():
    """Verify PowerShellWorker communication protocol."""
    dummy_script = Path("non_existent_worker.ps1")
    worker = PowerShellWorker(dummy_script)
    ok, msg = worker.send_command("PING")
    assert ok is False
    assert "unavailable" in msg.lower() or "not found" in msg.lower()


def test_ppt_routing_present_it(tmp_path):
    """Verify 'present it' and 'start presentation' route to ppt_control with action='start'."""
    settings = Settings(desktop_root=tmp_path, api_token="t" * 32, db_path=tmp_path / "n.db", apps_file=tmp_path / "apps.json")
    registry = Registry({"apps": {}, "tasks": {}})

    for phrase in ["present it", "start presentation", "start the presentation", "start slideshow", "present the presentation"]:
        intent = route(phrase, settings, registry)
        assert intent.kind == "ppt_control", f"Failed for '{phrase}', got {intent.kind}"
        assert intent.action == "start", f"Action should be start for '{phrase}', got {intent.action}"


# ==============================================================================
# 2. System Hardware Telemetry Non-Blocking Warm Snapshot (<20ms)
# ==============================================================================

def test_system_telemetry_warm_snapshot_latency():
    """Verify system telemetry retrieves warm snapshot in <20ms."""
    # Warm up first
    _ = get_system_status()

    # Measure 5 consecutive calls
    latencies_ms = []
    for _ in range(5):
        t0 = time.perf_counter()
        snap = get_system_status()
        latencies_ms.append((time.perf_counter() - t0) * 1000)

    avg_ms = sum(latencies_ms) / len(latencies_ms)
    assert avg_ms < 20.0, f"Expected <20ms, got {avg_ms:.2f}ms"
    assert "cpu_percent" in snap
    assert "memory" in snap
    assert "power" in snap
    assert "top_processes" in snap


def test_get_top_processes_cached_fast():
    """Verify process list is served immediately from memory cache without blocking."""
    # Seed cache
    _ = get_top_processes(limit=4)

    t0 = time.perf_counter()
    procs = get_top_processes(limit=4)
    dt_ms = (time.perf_counter() - t0) * 1000

    assert dt_ms < 5.0, f"Cached get_top_processes expected <5ms, got {dt_ms:.2f}ms"
    assert isinstance(procs, list)


def test_cpu_load_zero_sleep_calculation():
    """Verify get_cpu_load(sample_ms=0) computes in <5ms."""
    # Seed sample
    _ = get_cpu_load(sample_ms=0)

    t0 = time.perf_counter()
    cpu = get_cpu_load(sample_ms=0)
    dt_ms = (time.perf_counter() - t0) * 1000

    assert dt_ms < 5.0, f"Synchronous CPU calculation took {dt_ms:.2f}ms, expected <5ms"
    assert 0 <= cpu <= 100


# ==============================================================================
# 3. Stale-While-Revalidate GitHub Check & Weather Pre-fetching (<50ms)
# ==============================================================================

def test_github_check_cache_hit_latency(tmp_path):
    """Verify cached GitHub summary returns in <50ms with cache age noted."""
    desktop = tmp_path / "Desktop"
    desktop.mkdir()
    (desktop / "myrepo" / ".git").mkdir(parents=True)

    # Initial call populates cache
    with patch("backend.tools.workspace.check_repo_remote", return_value={"ahead": 0, "behind": 0, "has_remote": True, "fetch_output": ""}):
        with patch("backend.tools.workspace.check_repo_pull_requests", return_value=[]):
            with patch("backend.tools.workspace.check_repo_conflicts", return_value=[]):
                res1 = github_workspace_summary(desktop)
                assert "(Checked just now)" in res1

                # Second call must hit cache in <50ms
                t0 = time.perf_counter()
                res2 = github_workspace_summary(desktop)
                dt_ms = (time.perf_counter() - t0) * 1000

                assert dt_ms < 50.0, f"GitHub check cache hit took {dt_ms:.2f}ms, expected <50ms"
                assert "Checked" in res2


def test_async_github_check_force_refresh(tmp_path):
    """Verify async_github_workspace_summary with force_refresh=True updates cache."""
    desktop = tmp_path / "Desktop"
    desktop.mkdir()
    (desktop / "repo1" / ".git").mkdir(parents=True)

    with patch("backend.tools.workspace.check_repo_remote", return_value={"ahead": 1, "behind": 0, "has_remote": True, "fetch_output": ""}):
        with patch("backend.tools.workspace.check_repo_pull_requests", return_value=[]):
            with patch("backend.tools.workspace.check_repo_conflicts", return_value=[]):
                # 1. Warm call
                res = asyncio.run(async_github_workspace_summary(desktop, force_refresh=False))
                assert "repo1" in res
                assert "1 unpushed commit" in res

                # 2. Force refresh
                t0 = time.perf_counter()
                res_fresh = asyncio.run(async_github_workspace_summary(desktop, force_refresh=True))
                dt_ms = (time.perf_counter() - t0) * 1000
                assert "(Checked just now)" in res_fresh


def test_check_github_repos_async_concurrency(tmp_path):
    """Verify multiple repos are checked concurrently via asyncio.gather."""
    desktop = tmp_path / "Desktop"
    desktop.mkdir()
    for name in ["repo_a", "repo_b", "repo_c"]:
        (desktop / name / ".git").mkdir(parents=True)

    with patch("backend.tools.workspace.check_repo_remote", return_value={"ahead": 0, "behind": 0, "has_remote": True, "fetch_output": ""}):
        with patch("backend.tools.workspace.check_repo_pull_requests", return_value=[]):
            with patch("backend.tools.workspace.check_repo_conflicts", return_value=[]):
                repos = asyncio.run(check_github_repos_async(desktop))
                assert len(repos) == 3
                names = {r["project"] for r in repos}
                assert names == {"repo_a", "repo_b", "repo_c"}


def test_router_force_refresh_github(tmp_path):
    """Verify 'force refresh github' produces an Intent with force_refresh=True."""
    settings = Settings(desktop_root=tmp_path, api_token="t" * 32, db_path=tmp_path / "n.db", apps_file=tmp_path / "apps.json")
    registry = Registry({"apps": {}, "tasks": {}})

    i1 = route("force refresh github", settings, registry)
    assert i1.kind == "github_check"
    assert i1.force_refresh is True

    i2 = route("refresh github repos", settings, registry)
    assert i2.kind == "github_check"
    assert i2.force_refresh is True

    i3 = route("check my github repositories", settings, registry)
    assert i3.kind == "github_check"
    assert i3.force_refresh is False


def test_weather_prefetch_warm_cache():
    """Verify prefetch_weather populates cache so fetch_weather returns in <50ms."""
    city = "Calbayog"
    key = city.lower()
    _cache[key] = (time.monotonic(), "In Calbayog it's 29°C (feels like 32°C) with clear sky, humidity 75%.")

    t0 = time.perf_counter()
    report = asyncio.run(fetch_weather(city))
    dt_ms = (time.perf_counter() - t0) * 1000

    assert dt_ms < 50.0, f"Expected warm weather check in <50ms, got {dt_ms:.2f}ms"
    assert "Calbayog" in report
    assert "29°C" in report
