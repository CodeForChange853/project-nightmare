import json
import os
from pathlib import Path
import subprocess
from unittest.mock import MagicMock

import pytest

from backend.config import Settings
from backend.core.actions import Registry
from backend.core.clearance import ClearanceManager, LEVEL_1, LEVEL_3
from backend.core.llm import NoLLMProvider
from backend.core.orchestrator import Orchestrator
from backend.core.router import route
from backend.tools.audit import Audit
from backend.tools.file_navigator import (
    FileMatch,
    SecurityBlockError,
    find_files,
    get_allowed_roots,
    index_files,
    parse_file_query,
    safe_open_file,
)
from backend.tools.workspace import (
    check_repo_conflicts,
    check_repo_pull_requests,
    check_repo_remote,
    github_workspace_summary,
)


# 1. Directory indexing using tmp_path fixtures with mock .pptx, .docx, .xlsx, and forbidden .env
def test_directory_indexing_excludes_forbidden_files(tmp_path):
    desktop = tmp_path / "Desktop"
    documents = tmp_path / "Documents"
    downloads = tmp_path / "Downloads"
    desktop.mkdir()
    documents.mkdir()
    downloads.mkdir()

    # Allowed safe files
    (desktop / "slides.pptx").write_text("presentation")
    (documents / "report.docx").write_text("document")
    (downloads / "financials.xlsx").write_text("spreadsheet")
    (desktop / "notes.txt").write_text("notes")

    # Forbidden files & dirs
    (desktop / ".env").write_text("SECRET_KEY=12345")
    (desktop / "my_password.txt").write_text("password123")
    (desktop / "credentials.json").write_text("{}")
    (desktop / "cert.pem").write_text("cert")
    (desktop / "id_rsa.key").write_text("key")
    (desktop / "binary.bin").write_text("bin")

    git_dir = documents / ".git"
    git_dir.mkdir()
    (git_dir / "hidden.docx").write_text("should be skipped")

    node_modules = downloads / "node_modules"
    node_modules.mkdir()
    (node_modules / "pkg.docx").write_text("should be skipped")

    db_path = tmp_path / "test_audit.db"
    audit = Audit(db_path)

    roots = [desktop, documents, downloads]
    count = index_files(roots=roots, audit=audit)
    assert count == 4

    indexed = audit.get_indexed_files()
    filenames = {f["filename"] for f in indexed}
    assert filenames == {"slides.pptx", "report.docx", "financials.xlsx", "notes.txt"}

    # Verify forbidden files are excluded
    assert ".env" not in filenames
    assert "my_password.txt" not in filenames
    assert "credentials.json" not in filenames
    assert "cert.pem" not in filenames
    assert "id_rsa.key" not in filenames
    assert "hidden.docx" not in filenames
    assert "pkg.docx" not in filenames
    assert "binary.bin" not in filenames


# 2. Extension-aware resolution for complex queries
def test_extension_aware_resolution(tmp_path, monkeypatch):
    desktop = tmp_path / "Desktop"
    desktop.mkdir()

    (desktop / "timeline.pptx").write_text("ppt timeline")
    (desktop / "timeline.docx").write_text("doc timeline")
    (desktop / "budget.xlsx").write_text("budget")
    (desktop / "citizengraph_presentation.ppt").write_text("citizengraph ppt")

    db_path = tmp_path / "test_audit.db"
    audit = Audit(db_path)
    index_files(roots=[desktop], audit=audit)

    # Test query with multiple extension hints: word or powerpoint
    matches = find_files("find file related to timeline and open it in word or powerpoint", audit=audit)
    assert len(matches) >= 2
    matched_names = {m.filename for m in matches}
    assert "timeline.pptx" in matched_names
    assert "timeline.docx" in matched_names
    assert "budget.xlsx" not in matched_names

    # Test query with specific extension hint: ppt
    cg_matches = find_files("open citizengraph ppt", audit=audit)
    assert len(cg_matches) >= 1
    assert cg_matches[0].filename == "citizengraph_presentation.ppt"
    assert cg_matches[0].ext in {".ppt", ".pptx"}

    # Mock os.startfile so no real app opens
    opened = []
    if hasattr(os, "startfile"):
        monkeypatch.setattr(os, "startfile", lambda p: opened.append(str(p)))
    else:
        monkeypatch.setattr(subprocess, "Popen", lambda cmd, **kw: opened.append(str(cmd)))

    ok, msg = safe_open_file(desktop / "timeline.pptx", allowed_roots=[desktop])
    assert ok is True
    assert "timeline.pptx" in msg
    assert len(opened) == 1
    assert "timeline.pptx" in opened[0]


# 3. Path traversal defense
def test_path_traversal_defense(tmp_path):
    safe_root = tmp_path / "Desktop"
    safe_root.mkdir()
    secret_dir = tmp_path / "Secret"
    secret_dir.mkdir()

    secret_file = secret_dir / "confidential.docx"
    secret_file.write_text("top secret")

    # Outside root directly
    with pytest.raises(SecurityBlockError):
        safe_open_file(secret_file, allowed_roots=[safe_root])

    # Path traversal via ..
    traversal_path = safe_root / ".." / "Secret" / "confidential.docx"
    with pytest.raises(SecurityBlockError):
        safe_open_file(traversal_path, allowed_roots=[safe_root])

    # Blocked sensitive filename
    env_file = safe_root / ".env"
    env_file.write_text("KEY=val")
    with pytest.raises(SecurityBlockError):
        safe_open_file(env_file, allowed_roots=[safe_root])


# 4. Level 1 blocks file opening while Level 3 allows it
def test_level_1_blocks_file_opening_while_level_3_allows(tmp_path, monkeypatch):
    import asyncio

    desktop = tmp_path / "Desktop"
    desktop.mkdir()
    target_file = desktop / "timeline.pptx"
    target_file.write_text("presentation")

    db_path = tmp_path / "n.db"
    audit = Audit(db_path)
    index_files(roots=[desktop], audit=audit)

    opened = []
    if hasattr(os, "startfile"):
        monkeypatch.setattr(os, "startfile", lambda p: opened.append(str(p)))
    else:
        monkeypatch.setattr(subprocess, "Popen", lambda cmd, **kw: opened.append(str(cmd)))

    apps_file = tmp_path / "apps.json"
    apps_file.write_text(json.dumps({"apps": {}, "tasks": {}}))
    settings = Settings(desktop_root=desktop, api_token="t" * 32, db_path=db_path, apps_file=apps_file)
    registry = Registry({"apps": {}, "tasks": {}})
    clearance = ClearanceManager()

    orchestrator = Orchestrator(
        settings=settings,
        provider=NoLLMProvider(),
        registry=registry,
        audit=audit,
        clearance=clearance,
    )

    query = "find file related to timeline and open it in powerpoint"
    session_id = "test_sess"

    # Default session is Level 1 (Observer) -> must be blocked
    reply_l1 = asyncio.run(orchestrator.handle(query, readonly=False, session=session_id))
    assert reply_l1.ok is False
    assert "Level 3" in reply_l1.text
    assert len(opened) == 0

    # Verify clearance block logged in SQLite actions table
    recent = audit.recent_actions(limit=5)
    assert any(a["kind"] == "clearance_blocked" and "open_file" in a["detail"] for a in recent)

    # Elevate session to Level 3 (Operator)
    clearance.set_level(session_id, LEVEL_3)
    assert clearance.get_level(session_id) == LEVEL_3

    # Now Level 3 allows opening
    reply_l3 = asyncio.run(orchestrator.handle(query, readonly=False, session=session_id))
    assert reply_l3.ok is True
    assert "timeline.pptx" in reply_l3.text
    assert len(opened) == 1
    assert "timeline.pptx" in opened[0]


# 5. GitHub conflict / PR check parser with mocked subprocess.run outputs
def test_github_conflict_and_pr_check_parser(tmp_path, monkeypatch):
    repo_dir = tmp_path / "Desktop" / "citizengraph"
    repo_dir.mkdir(parents=True)
    (repo_dir / ".git").mkdir()

    def mock_subprocess_run(cmd, cwd=None, **kwargs):
        cmd_str = " ".join(cmd)
        mock_res = MagicMock()
        mock_res.returncode = 0
        mock_res.stderr = b""

        if "git remote" in cmd_str:
            mock_res.stdout = b"origin\n"
        elif "git fetch --dry-run" in cmd_str:
            mock_res.stdout = b"   a1b2c3d..e4f5g6h  main       -> origin/main\n"
        elif "git rev-list --left-right --count" in cmd_str:
            mock_res.stdout = b"1\t3\n"  # 1 ahead, 3 behind
        elif "gh pr list" in cmd_str:
            pr_data = [
                {
                    "number": 14,
                    "title": "Add graph visualizer",
                    "author": {"login": "student"},
                    "state": "OPEN",
                }
            ]
            mock_res.stdout = json.dumps(pr_data).encode("utf-8")
        elif "git status --porcelain" in cmd_str:
            mock_res.stdout = b"UU frontend/src/Graph.jsx\n M package.json\n"
        else:
            mock_res.stdout = b""
        return mock_res

    monkeypatch.setattr(subprocess, "run", mock_subprocess_run)
    monkeypatch.setattr("shutil.which", lambda name: f"/usr/bin/{name}")

    # Check remote updates
    rem = check_repo_remote(repo_dir)
    assert rem["has_remote"] is True
    assert rem["ahead"] == 1
    assert rem["behind"] == 3

    # Check pull requests
    prs = check_repo_pull_requests(repo_dir)
    assert len(prs) == 1
    assert prs[0]["number"] == 14
    assert prs[0]["title"] == "Add graph visualizer"
    assert prs[0]["author"] == "student"

    # Check conflicts
    conflicts = check_repo_conflicts(repo_dir)
    assert len(conflicts) == 1
    assert "frontend/src/Graph.jsx" in conflicts[0]

    # Check workspace summary
    summary = github_workspace_summary(tmp_path / "Desktop")
    assert "citizengraph" in summary
    assert "3 incoming commits" in summary
    assert "1 unpushed commit" in summary
    assert "#14 (Add graph visualizer)" in summary
    assert "frontend/src/Graph.jsx" in summary


# 6. Intent routing checks
def test_router_file_navigator_and_github_intents(tmp_path):
    apps_file = tmp_path / "apps.json"
    apps_file.write_text(json.dumps({"apps": {}, "tasks": {}}))
    desktop = tmp_path / "Desktop"
    desktop.mkdir()
    settings = Settings(desktop_root=desktop, api_token="t" * 32, db_path=tmp_path / "n.db", apps_file=apps_file)
    registry = Registry({"apps": {}, "tasks": {}})

    # File navigator intents
    i1 = route("find file related to timeline and open it in word or powerpoint", settings, registry)
    assert i1.kind == "open_file"
    assert "timeline" in (i1.query or "").lower()

    i2 = route("open citizengraph ppt", settings, registry)
    assert i2.kind == "open_file"
    assert "citizengraph" in (i2.query or "").lower()

    i3 = route("open budget in excel", settings, registry)
    assert i3.kind == "open_file"
    assert "budget" in (i3.query or "").lower()

    # GitHub checks intent
    i4 = route("check my github repositories for commits/pull requests/merge conflicts", settings, registry)
    assert i4.kind == "github_check"

    i5 = route("check github repositories", settings, registry)
    assert i5.kind == "github_check"

    # Spoken lead-ins and office app queries must route to open_file, NOT open_folder or unknown_app
    i6 = route("comments and find citizen graph chapter 1 docs and open it on word", settings, registry)
    assert i6.kind == "open_file"
    assert "citizen graph" in (i6.query or "").lower()

    i7 = route("ilcro interview checklist and open it in word", settings, registry)
    assert i7.kind == "open_file"
    assert "checklist" in (i7.query or "").lower()

    i8 = route("clear cache", settings, registry)
    assert i8.kind == "clear_cache"


def test_speech_patterns_fuzzy_matching_and_lock_files(tmp_path):
    downloads = tmp_path / "Downloads"
    docs_dir = tmp_path / "Documents"
    downloads.mkdir()
    docs_dir.mkdir()

    # Real filenames from user activity log
    target_cg = downloads / "CITIZEN_GRAPH_Chapter1_and_Outline.docx"
    lock_cg = downloads / "~$tizen Graph Revised Chapter 1.docx"
    target_lcro = docs_dir / "LCRO Interview checklist.docx"

    target_cg.write_text("thesis chapter 1")
    lock_cg.write_text("lock file")
    target_lcro.write_text("interview checklist")

    db_path = tmp_path / "audit.db"
    audit = Audit(db_path)
    index_files(roots=[downloads, docs_dir], audit=audit)

    # 1. Lock file must be ignored
    indexed = audit.get_indexed_files()
    indexed_names = {f["filename"] for f in indexed}
    assert "CITIZEN_GRAPH_Chapter1_and_Outline.docx" in indexed_names
    assert "LCRO Interview checklist.docx" in indexed_names
    assert "~$tizen Graph Revised Chapter 1.docx" not in indexed_names

    # 2. Spoken query matching with speech lead-in and preposition "on word"
    matches_cg = find_files("comments and find citizen graph chapter 1 docs and open it on word", audit=audit)
    assert len(matches_cg) > 0
    assert matches_cg[0].filename == "CITIZEN_GRAPH_Chapter1_and_Outline.docx"

    # 3. Fuzzy phonetic matching: "ilcro" matches "lcro"
    matches_lcro = find_files("ilcro interview checklist and open it in word", audit=audit)
    assert len(matches_lcro) > 0
    assert matches_lcro[0].filename == "LCRO Interview checklist.docx"


def test_progress_caching_freshness_and_cache_clear(tmp_path):
    import asyncio
    from backend.core.llm import LLMProvider

    desktop = tmp_path / "Desktop"
    desktop.mkdir()
    proj = desktop / "project-nightmare"
    proj.mkdir()
    (proj / "handoff.md").write_text("# Handoff\nOct 20 work completed.")

    db_path = tmp_path / "audit.db"
    audit = Audit(db_path)
    apps_file = tmp_path / "apps.json"
    apps_file.write_text(json.dumps({"apps": {}, "tasks": {}}))
    settings = Settings(desktop_root=desktop, api_token="t" * 32, db_path=db_path, apps_file=apps_file)
    registry = Registry({"apps": {}, "tasks": {}})

    call_count = 0

    class CountingLLM(LLMProvider):
        name = "mock_counting"

        async def complete(self, prompt: str, smart: bool = False) -> str:
            nonlocal call_count
            call_count += 1
            return f"Summary version {call_count}"

    orch = Orchestrator(settings, CountingLLM(), registry, audit)

    # 1. First ask -> generates summary (call_count == 1)
    rep1 = asyncio.run(orch.handle("what is the progress of project nightmare"))
    assert rep1.ok is True
    assert "Summary version 1" in rep1.text
    assert call_count == 1

    # 2. Second ask without "latest/fresh" -> uses cache (call_count stays 1)
    rep2 = asyncio.run(orch.handle("what is the progress of project nightmare"))
    assert "Summary version 1" in rep2.text
    assert "(cached)" in rep2.understood
    assert call_count == 1

    # 3. Third ask with "latest" -> bypasses cache, calls LLM (call_count == 2)
    rep3 = asyncio.run(orch.handle("what's the latest progress of project nightmare"))
    assert rep3.ok is True
    assert "Summary version 2" in rep3.text
    assert "(fresh)" in rep3.understood
    assert call_count == 2

    # 4. "clear cache" command clears summary cache
    rep_clear = asyncio.run(orch.handle("clear cache"))
    assert rep_clear.ok is True
    assert "Summary cache cleared" in rep_clear.text

    # 5. Subsequent ask calls LLM again because cache was cleared
    rep4 = asyncio.run(orch.handle("progress of project nightmare"))
    assert "Summary version 3" in rep4.text
    assert call_count == 3


def test_exact_and_clear_winner_bypass_and_stateful_disambiguation(tmp_path, monkeypatch):
    import asyncio
    import time

    desktop = tmp_path / "Desktop"
    desktop.mkdir()

    # The exact 3 filenames
    f_lcro = desktop / "LCRO.docx"
    f_cg = desktop / "CitizenGraph_Interview_Checklist.docx"
    f_checklist = desktop / "LCRO Interview checklist.docx"

    f_lcro.write_text("lcro doc")
    f_cg.write_text("citizengraph interview checklist doc")
    f_checklist.write_text("lcro interview checklist doc")

    # Set mtime so f_checklist is newer than f_cg so choice #1 is LCRO Interview checklist.docx
    # and choice #2 is CitizenGraph_Interview_Checklist.docx
    now = time.time()
    os.utime(f_lcro, (now - 30, now - 30))
    os.utime(f_cg, (now - 20, now - 20))
    os.utime(f_checklist, (now - 10, now - 10))

    db_path = tmp_path / "audit.db"
    audit = Audit(db_path)
    index_files(roots=[desktop], audit=audit)

    opened = []
    if hasattr(os, "startfile"):
        monkeypatch.setattr(os, "startfile", lambda p: opened.append(Path(p).name))
    else:
        monkeypatch.setattr(subprocess, "Popen", lambda cmd, **kw: opened.append(Path(cmd[-1]).name))

    apps_file = tmp_path / "apps.json"
    apps_file.write_text(json.dumps({"apps": {}, "tasks": {}}))
    settings = Settings(desktop_root=desktop, api_token="t" * 32, db_path=db_path, apps_file=apps_file)
    registry = Registry({"apps": {}, "tasks": {}})
    clearance = ClearanceManager()

    orchestrator = Orchestrator(
        settings=settings,
        provider=NoLLMProvider(),
        registry=registry,
        audit=audit,
        clearance=clearance,
    )

    session_id = "test_sess"
    clearance.set_level(session_id, LEVEL_3)

    # 1. "open LCRO Interview checklist.docx in word" immediately opens without disambiguation
    rep1 = asyncio.run(orchestrator.handle("open LCRO Interview checklist.docx in word", session=session_id))
    assert rep1.ok is True
    assert "LCRO Interview checklist.docx" in rep1.text
    assert len(opened) == 1
    assert opened[-1] == "LCRO Interview checklist.docx"
    assert "multiple" not in rep1.text.lower()

    # 2. "find LCRO interview checklist and open in word" immediately opens without disambiguation
    rep2 = asyncio.run(orchestrator.handle("find LCRO interview checklist and open in word", session=session_id))
    assert rep2.ok is True
    assert "LCRO Interview checklist.docx" in rep2.text
    assert len(opened) == 2
    assert opened[-1] == "LCRO Interview checklist.docx"
    assert "multiple" not in rep2.text.lower()

    # Also test "openfile LCRO Interview checklist.docx (word)"
    rep_openfile = asyncio.run(orchestrator.handle("openfile LCRO Interview checklist.docx (word)", session=session_id))
    assert rep_openfile.ok is True
    assert "LCRO Interview checklist.docx" in rep_openfile.text
    assert len(opened) == 3
    assert opened[-1] == "LCRO Interview checklist.docx"

    # 3. Ambiguous query "open interview checklist" prompts with numbered choices
    rep3 = asyncio.run(orchestrator.handle("open interview checklist", session=session_id))
    assert rep3.ok is False
    assert (
        rep3.text
        == "I found multiple files: 1, LCRO Interview checklist.docx; 2, CitizenGraph_Interview_Checklist.docx. Say the number or filename to open it."
    )
    assert orchestrator._pending_file_choices is not None
    assert len(orchestrator._pending_file_choices) == 2
    assert len(opened) == 3  # not opened yet

    # 4. Follow-up turn "the first one" opens choice #1 immediately
    rep4 = asyncio.run(orchestrator.handle("the first one", session=session_id))
    assert rep4.ok is True
    assert "LCRO Interview checklist.docx" in rep4.text
    assert len(opened) == 4
    assert opened[-1] == "LCRO Interview checklist.docx"
    assert orchestrator._pending_file_choices is None

    # 5. Ambiguous query followed by "1"
    rep5 = asyncio.run(orchestrator.handle("open interview checklist", session=session_id))
    assert rep5.ok is False
    assert "I found multiple files" in rep5.text
    assert orchestrator._pending_file_choices is not None

    rep6 = asyncio.run(orchestrator.handle("1", session=session_id))
    assert rep6.ok is True
    assert "LCRO Interview checklist.docx" in rep6.text
    assert len(opened) == 5
    assert opened[-1] == "LCRO Interview checklist.docx"
    assert orchestrator._pending_file_choices is None

    # 6. Ambiguous query followed by "the second one" opens choice #2
    rep7 = asyncio.run(orchestrator.handle("open interview checklist", session=session_id))
    assert rep7.ok is False
    rep8 = asyncio.run(orchestrator.handle("the second one", session=session_id))
    assert rep8.ok is True
    assert "CitizenGraph_Interview_Checklist.docx" in rep8.text
    assert len(opened) == 6
    assert opened[-1] == "CitizenGraph_Interview_Checklist.docx"

    # 7. Ambiguous query followed by "2"
    rep9 = asyncio.run(orchestrator.handle("open interview checklist", session=session_id))
    assert rep9.ok is False
    rep10 = asyncio.run(orchestrator.handle("2", session=session_id))
    assert rep10.ok is True
    assert "CitizenGraph_Interview_Checklist.docx" in rep10.text
    assert len(opened) == 7
    assert opened[-1] == "CitizenGraph_Interview_Checklist.docx"

    # 8. Follow-up turn selecting by naming the file
    rep11 = asyncio.run(orchestrator.handle("open interview checklist", session=session_id))
    assert rep11.ok is False
    rep12 = asyncio.run(orchestrator.handle("LCRO Interview checklist.docx", session=session_id))
    assert rep12.ok is True
    assert "LCRO Interview checklist.docx" in rep12.text
    assert len(opened) == 8
    assert opened[-1] == "LCRO Interview checklist.docx"

    # 9. Level 1 blocks selection turn
    clearance.set_level(session_id, LEVEL_3)
    clearance.set_level("l1_sess", LEVEL_1)
    rep_amb = asyncio.run(orchestrator.handle("open interview checklist", session=session_id))
    assert rep_amb.ok is False
    assert orchestrator._pending_file_choices is not None

    # Selection turn attempted from Level 1 session must be blocked
    rep_l1 = asyncio.run(orchestrator.handle("the first one", session="l1_sess"))
    assert rep_l1.ok is False
    assert "Level 3" in rep_l1.text

    # 10. Expiry drops choices
    clearance.set_level(session_id, LEVEL_3)
    asyncio.run(orchestrator.handle("open interview checklist", session=session_id))
    assert orchestrator._pending_file_choices is not None
    orchestrator._pending_file_choices.expires_at = time.monotonic() - 1.0
    rep_exp = asyncio.run(orchestrator.handle("the first one", session=session_id))
    # Since choices are expired, choices are cleared and "the first one" falls back to chat
    assert orchestrator._pending_file_choices is None


def test_citizengraph_vs_nexenroll_file_matching_and_guard(tmp_path, monkeypatch):
    """Verifies that multi-token file queries match full token candidates and never auto-open partial matches."""
    import asyncio
    desktop = tmp_path / "Desktop"
    desktop.mkdir()

    f_cg = desktop / "CitizenGraph_Thesis_Timeline_2026_2027-v2.xlsx"
    f_nex = desktop / "NexEnroll_Development_Timeline.xlsx"
    f_cg.write_text("cg timeline")
    f_nex.write_text("nex timeline")

    db_path = tmp_path / "audit.db"
    audit = Audit(db_path)
    index_files(roots=[desktop], audit=audit)

    # 1. find_files with both files indexed: CitizenGraph matches both 'citizengraph' and 'timeline'
    matches = find_files("citizengraph timeline", ext_filter="excel", audit=audit, allowed_roots=[desktop])
    assert len(matches) >= 1
    top = matches[0]
    assert top.filename == "CitizenGraph_Thesis_Timeline_2026_2027-v2.xlsx"
    assert top.matched_tokens == 2

    # 2. If only NexEnroll is indexed and user asks for 'citizengraph timeline', orchestrator partial guard triggers
    db_path2 = tmp_path / "audit2.db"
    audit2 = Audit(db_path2)
    # Only index nexenroll
    audit2.upsert_indexed_files([("NexEnroll_Development_Timeline.xlsx", "nexenroll_development_timeline", ".xlsx", str(f_nex), 1000)])

    apps_file = tmp_path / "apps.json"
    apps_file.write_text(json.dumps({"apps": {}, "tasks": {}}))
    settings = Settings(desktop_root=desktop, api_token="t" * 32, db_path=db_path2, apps_file=apps_file)
    clearance = ClearanceManager()
    orch = Orchestrator(
        settings=settings,
        provider=NoLLMProvider(),
        registry=Registry(),
        audit=audit2,
        clearance=clearance,
    )
    clearance.set_level("test_sess", LEVEL_3)

    opened = []
    if hasattr(os, "startfile"):
        monkeypatch.setattr(os, "startfile", lambda p: opened.append(Path(p).name))
    else:
        monkeypatch.setattr(subprocess, "Popen", lambda cmd, **kw: opened.append(Path(cmd[-1]).name))

    rep = asyncio.run(orch.handle("find file related to citizengraph timeline and open in excel", session="test_sess"))
    # Guard triggered: does not open NexEnroll blindly, rejects or asks for confirmation
    assert rep.ok is False
    assert "partially matched" in rep.text or "couldn't find" in rep.text.lower()
    assert len(opened) == 0  # NexEnroll was NOT opened!

