# Project Nightmare: session handoff (handoff.md = newsession.md)

Last updated: 2026-10-24 (Asia/Manila). Keep both files identical after every milestone. **UNVERIFIED** = not yet tested live by the user.

## 0. Quick status (read by Nightmare's own `progress` command)

- **Done:** Phases 1, 1.5, 2, 3, 4, 6, plus small window/phone tabs, **Phase 7A**, **Phase 7C (memory)**, **Phase 7D (workspace awareness)**, **Semantic Intent Router (Solution A)**, **Enhancements 1-5 (Warmup, Voice Switching, Instant Memory, Project Count, Local RAG)**, **Phase 8A: 3-Tier Security Clearance Architecture (Level 1, Level 3, Level 5)**, **Phase 8B: Level 3 Smart File Navigator & GitHub Intelligence (Exact Bypass & Stateful Disambiguation Updated)**, **Phase 8C: Level 5 PowerPoint Exact-Slide Presenter & System Authority**, **Phase 8D: Level 5 Shared Drive Excel Timeline Sync, Team Quota Tracker, and 3-Day Stale Email Nudger**, and **Phase 8D-2: 4-Tab CitizenGraph Telemetry, GDrive Diff Engine & Level 5 Desktop Command Center**. Phone over Tailscale works live; the Android repeated-words fix is confirmed by the user.
- **Phase 8D-2: 4-Tab CitizenGraph Telemetry, GDrive Diff Engine & Level 5 Desktop Command Center done (2026-10-24, 341 backend tests [349 with browser], 5 frontend tests pass, UNVERIFIED live):**
  - **4-Tab CitizenGraph Workbook Parsing (`backend/tools/team_tracker.py`, Level 5 required):**
    - Zero-dependency OpenXML parsing (`zipfile` + `xml.etree.ElementTree`) for `CitizenGraph_Thesis_Timeline_2026_2027-v2.xlsx` (and backward compatible with 18-task `NexEnroll_Development_Timeline.xlsx`).
    - Tab 1 `General 8-Month Roadmap`: parses STG-01..STG-09, timeline stages, calendar spans, thesis phases, general titles, aligned activities, major milestones, and active month detection via symbols (`●`, `★`, `⭐`) and fills (`#0284C7` Phase 1, `#0D9488` Phase 2, `#4F46E5` Indigo, `#FFD966` Milestone).
    - Tab 2 `Detailed Weekly Gantt`: parses 21 tasks (1.1..1.12 Phase 1; 2.1..2.9 Phase 2), compressing 24 weekly indicators (S-W1..F-W4) into clean start/end week spans and active month tracks.
    - Tab 3 `Objectives & KPI Alignment`: parses SO-1..SO-7 specific objectives, architectural components, datasets/scopes, target benchmarks, scheduled windows, and status.
    - Tab 4 `Phase Summary & Dashboard`: calculates live rollup metrics directly in Python (Phase 1, Phase 2, Roadmap, Overall WBS) and Chapter 1 quantitative benchmark targets (SO-4 to SO-7: Return-Trip Prevention >= 90%, Exact-Match Accuracy >= 95%, Gap Analysis M = R \ H >= 90%, Topological Sequence >= 90%, Post-AST Execution >= 95%, Edge Latency <= 5.0s).
  - **GDrive Cross-Reference Diff Engine (`timeline_state` SQLite table in `Audit`):**
    - Stores `(item_key, sheet_name, title, phase, status, period, deliverable, updated_at, source_hash, is_baseline)` for every row across Roadmap, WBS, and Objectives.
    - Automated cross-referencing compares current workbook state against stored baseline, categorizing status transitions, schedule shifts, deliverable edits, and completion deltas.
    - Public Google Drive reachability check via `urllib.request` with 8s timeout and graceful offline fallback (`NIGHTMARE_TEAM_GDRIVE_FOLDER_URL`).
    - REST endpoints: `GET /api/team-tracker/diff`, `POST /api/team-tracker/sync` (commits new baseline), and `POST /api/team-tracker/open-excel` (launches Excel on desktop via `safe_open_file`).
  - **Wired Voice Intents (`router.py`, `semantic_router.py`, `clearance.py`, `orchestrator.py`):**
    - `timeline_diff`: `"nightmare what change in the citizengraph timeline from the gdrive"`, `"what changed in the citizengraph timeline"`, `"compare citizengraph timeline with gdrive"`, `"check gdrive timeline updates"`, `"what did my team update in the timeline"`.
    - Deterministic plain-Python spoken reply (no LLM latency) e.g. *"Cross-referencing the CitizenGraph timeline against the baseline. 2 items changed: 1.5 Review of Related Literature moved from In Progress to Completed, and SO-2 status updated. Phase 1 is now at 58% completion. Opening the Timeline Diff tab."* Returns `ui="team_progress:diff"`.
    - Strictly enforced Level 5 clearance (`INTENT_CLEARANCE_MAP`), blocked on remote sessions and Level 1/3 sessions.
  - **Remodeled Desktop Command Center (`TeamProgressPanel.jsx`):**
    - High-density desktop viewport (1440p / 1080p) matching Nightmare's Level 5 Crimson, Obsidian & Gold theme with GSAP transitions.
    - Top telemetry bar with local file status, GDrive folder link, [CHECK GDRIVE / DIFF], [OPEN IN EXCEL], and [SYNC BASELINE] action controls.
    - Single-active-tab 5-tab layout: 1. Executive Summary, 2. 8-Month Roadmap, 3. Phase 1 & 2 Weekly WBS, 4. Objectives & KPIs, 5. GDrive Diff & Team Sync.
    - Strict status color badges: Emerald Green (Completed), Warm Amber (In Progress), Crimson Red (Pending).
- **Phase 8D: Level 5 Shared Drive Excel Timeline Sync, Team Quota Tracker, and 3-Day Stale Email Nudger done (2026-10-23, 344 backend tests, 5 frontend tests pass, UNVERIFIED live):**
  - **Shared Drive Excel Timeline Sync (`backend/tools/team_tracker.py`, Level 5 required):**
    - Configurable `NIGHTMARE_TEAM_EXCEL_PATH` in `backend/.env` (pointing to local Google Drive / OneDrive synced folder or Desktop timeline `.xlsx`) with auto-discovery via `file_navigator` for `*Timeline*.xlsx` or `*Progress*.xlsx`.
    - Zero-dependency OpenXML parsing (`zipfile` + `xml.etree.ElementTree`) extracting `#`, `Phase / Task`, `Deliverable`, and `Month 1`..`Month 7` across 18 timeline tasks.
    - Active month detection via ARGB fill colors (`#9DC3E6` Core Work, `#C6E0B4` Buffer/Polish, `#FFD966` Milestone) and `⭐` milestone cell text.
  - **Team Quota Tracker & 3-Day Stale Detection (`team_task_state` SQLite table in `Audit`):**
    - Parses `Team_Tasks` sheet (`Task_ID`, `Assigned_Team`, `Owner_Email`, `Task_Name`, `Current_Count`, `Target_Count`, `Last_Updated`).
    - Automatically compares `current_count` against stored values in SQLite and flags tasks as `STALE` if `current_count < target_count` and `(now - last_change_ts) >= 3 days` (or Excel date >= 3 days old).
  - **Approve / Decline Email Notification Workflow (`backend/tools/email_notifier.py`, Level 5 only, `needs_confirm=True`):**
    - Built using Python's built-in `smtplib` + `email.message.EmailMessage` (`SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_APP_PASSWORD`).
    - Nightmare NEVER sends emails automatically. Stale tasks generate pending actions (`plan_send_team_nudge`) with recipient, task progress, and email draft.
    - Emails sent ONLY on explicit click confirmation (`POST /api/actions/confirm`) or voice `"approve email"` in Level 5. Clicking Decline cancels and snoozes the alert for 24 hours in SQLite.
- **Phase 8C: Level 5 PowerPoint Exact-Slide Presenter & System Authority done (2026-10-23, 330 backend tests, 5 frontend tests pass, UNVERIFIED live):**
  - **PowerPoint Exact-Slide Presenter (`backend/tools/ppt_controller.py`, Level 5 required):**
    - `open_ppt_at_slide(file_path, slide_number=1)`: resolves `file_path` via `file_navigator.py` (restricted to `.pptx` / `.ppt`), validates path traversal boundaries against allowed roots. On Windows, uses COM automation (`win32com.client` if installed, or PowerShell COM fallback via `[Runtime.InteropServices.Marshal]::GetActiveObject` / `New-Object -ComObject PowerPoint.Application`) to open the presentation, launch the slide show (`SlideShowSettings.Run()`), and jump directly to `slide_number` (`SlideShowWindow.View.GotoSlide`).
    - Active presentation slide navigation: `goto_slide(slide_number)`, `next_slide()`, and `previous_slide()` for already-active slide shows.
    - Zero-dependency XML slide parser (`parse_ppt_slides`): parses `.pptx` ZIP archives using Python standard library `zipfile` + `xml.etree.ElementTree` with zero pip dependencies. Extracts slide number, title, body, and full text.
    - Deterministic slide topic search (`find_slide_by_topic`): extracts keywords and matches topic across titles and bodies so `"show the slide about <topic>"` resolves to exact slide number and jumps to it.
  - **Level 5 System Authority Commands (`backend/core/actions.py`, `backend/core/orchestrator.py`):**
    - `"rerun yourself"` / `"restart nightmare"`: requires Level 5 Architect access AND click confirmation (`needs_confirm=True`), spawning a detached background process running `scripts/start_nightmare.ps1 -Rebuild -Background`.
    - `"restart my pc"` / `"shut down my pc"`: requires Level 5 Architect access AND click confirmation (`needs_confirm=True`), executing `shutdown /r /t 10` or `shutdown /s /t 10`.
    - `"cancel shutdown"` / `"abort shutdown"`: executes `shutdown /a` immediately to abort pending system shutdowns without waiting for confirmation.
- **Phase 8B: Level 3 Smart File Navigator & GitHub Intelligence done (2026-10-23, 326 backend tests, 5 frontend tests pass, UNVERIFIED live):**
  - **Smart File Navigator (`backend/tools/file_navigator.py`, plain Python, zero LLM):**
    - Scans and indexes safe files (`.pptx`, `.ppt`, `.docx`, `.doc`, `.xlsx`, `.pdf`, `.txt`, `.md`) across `Desktop`, `Documents`, `Downloads`, and safe top-level user directories in `Path.home()`.
    - Strictly skips `.git`, `node_modules`, `.venv`, `AppData`, `__pycache__`, temporary office lock files (`~$*`), and sensitive files (`.env`, `*password*`, `*credential*`, `.pem`, `.key`).
    - Caches index in SQLite `indexed_files` table in `Audit` with `(id, filename, stem_lower, ext, full_path, mtime_ns)` and indexed stem/ext lookups.
    - Safe file opening (`safe_open_file`) validates path traversal boundaries against allowed roots, enforces Level 3+ clearance, blocks execution on remote sessions, and asks the user to disambiguate if multiple files match closely.
  - **GitHub Repository Checks (`backend/tools/workspace.py`, Level 3+):**
    - Plain Python helpers wrapping `git` and `gh` CLI with 8-second timeouts across tracked Desktop repos.
- **Phase 8A: 3-Tier Security Clearance Architecture done (2026-10-23, 315 tests pass, UNVERIFIED live):**
  - **Level 1 (Observer - Default):** Default startup for both localhost and remote Tailscale sessions. Strictly read-only; blocks all `ACTION_INTENTS`, `MEMORY_WRITE_INTENTS`, file opening, and system mutations.
  - **Level 3 (Operator):** Activated via `"nightmare open level 3"` or `"elevate to level 3"`. Verified via `POST /api/clearance/elevate` using 6-digit PIN. Decays to Level 1 after 30 min of inactivity.
  - **Level 5 (Architect):** Activated via `"nightmare open level 5"`. Verified via `POST /api/clearance/elevate` against `NIGHTMARE_L5_PASSWORD` using constant-time `hmac.compare_digest`. Decays to Level 1 after 10 min of inactivity or immediately on `"nightmare lock down"`, `"drop to level 1"`, or standby sleep.
- **In progress: Phase 7 & Phase 8**.
- **User decisions for Phase 7 & 8:** do the recommended options. Do **not** install Ollama; the user has a fine-tuned **Llama 3 8B Instruct** (from the CitizenGraph project) to consider for offline use in 7B; propose how to use it before installing anything. Phone may read (not change) saved memory. Keep raw conversations 90 days, remembered facts until "forget". Dev tasks found automatically always need a click. Default startup is Level 1 (Observer).
- **Blockers:** none.

## 1. Start of a session

Read this file; follow section 9 rules; update this file and `newsession.md` after each milestone.

## 2. User constraints

- Localhost only, one user (graduating CS student, Calbayog). Windows 11, Python 3.11.9, PowerShell, venv `.venv`. Laptop: Ryzen 5 7520U, 4 cores, 16 GB RAM, no NVIDIA, ~145 GB free.
- Voice is the main interface (Chrome Web Speech today). Phone is Android Chrome.
- No separate API billing: use Google AI Pro through the Antigravity CLI `agy` (no API key).
- Wants safe system access that acts: open apps/folders, run predefined tasks.
- **Phone/remote = always read-only:** allowed: progress, cross-project, list projects, read_doc, git status, weather, reminders, chat, status, usage, workspace briefing/changes/priorities, search_projects, conversation_history, clearance status. Blocked: opening apps/folders, running tasks/commands/dev tasks, confirmations, database viewer, Settings, clearance elevation past Level 1.

## 3. Decisions vs the original doc

Claude API fallback dropped (no cost). No MCP at runtime (plain Python tools). Regex router decides actions; the LLM never does (latency + prompt-injection safety). Gemini CLI replaced by `agy` (Gemini CLI stopped serving AI Pro 2026-06-18). GSAP core + DrawSVG/ScrambleText only. Clearance state managed in memory with inactivity decay and constant-time authentication. Zero external pip dependencies used for Office parsing (standard library `zipfile` + `xml.etree.ElementTree` for .pptx slide parsing and .xlsx OpenXML timeline parsing, PowerShell COM automation fallback).

## 4. agy facts

- Headless: `agy -p "<prompt>" --model <id> --disable-slash-commands --output-format json|text`. Print mode auto-approves every tool call, so: run from an empty scratch folder, tell it to use no tools, scrub API-key env vars, give it only text (never paths or shell).
- Models: fast `gemini-3.8-flash-low` (summaries/chat), smart `gemini-3.8-flash-high` (cross-project, "think deeply"). `agy models` lists IDs; effort is part of the ID. Gemini 4 Argon unused.

## 5. Request flow

```
Browser/Phone -> FastAPI 127.0.0.1:<port> (serves frontend/dist + /api/*)
  guard: token or session cookie + local Host + allowed Origin (remote via tailscale serve = readonly)
  clearance check:
    session clearance (Level 1 Observer, Level 3 Operator, Level 5 Architect)
    if intent requires clearance > session level -> blocked ("That action requires Level X access")
  Orchestrator.handle -> router.route (regex -> fastembed semantic -> LLM classifier) -> handler
    quick_reply (time, greet, help, thanks, name, sleep, unknown_app) instant
    clearance_elevate ("nightmare open level 3 / 5")             instant (UI modal prompt)
    clearance_lockdown ("lock down", "drop to level 1")          instant (reset to L1)
    clearance_status ("what is my clearance level")              instant
    voice_settings (female / male toggle)                        instant (UI dispatch)
    conversation_history ("earlier what we discussed")           instant (SQLite turns)
    search_projects ("search projects for...")                   instant (FastEmbed RAG)
    workspace (briefing, changes, priorities)                    instant (plain Python)
    github_check ("check my github repositories...")             instant (git / gh CLI Level 3+)
    open_file ("find file related to X and open it...")          instant (file_navigator Level 3+)
    ppt_open_slide ("find and open X ppt ... show slide N")      instant (ppt_controller Level 5)
    ppt_control ("go to slide N", "next/previous slide")         instant (ppt_controller Level 5)
    system_authority ("restart pc", "rerun yourself")            instant (needs_confirm=True Level 5)
    team_progress ("show team progress", "open timeline tracker") instant (team_tracker Level 5)
    timeline_diff ("what changed in the citizengraph timeline")  instant (team_tracker diff Level 5)
    approve_email ("approve email", "send reminder email")       instant (email_notifier Level 5 confirm)
    progress / about / read_doc: handoff/README/doc -> cached summary (memory + SQLite, by mtime) or agy fast
    cross_project: all handoffs -> agy smart;  git_status, weather (Open-Meteo, wttr.in, 10 min cache),
    notes/reminders (SQLite), open_url (fixed https templates, frontend window.open), db/settings panels (PIN)
    open app/folder/task/command/dev_task: blocked if readonly or L1; allowlist apps.json; confirm click if needed
    chat fallback: agy answers or emits a closed read-only INTENT:<kind> tag validated in Python
  -> audit log (SQLite) incl. timing row -> reply (+focus node/item, understood tag) -> UI + TTS
```

## 6. Feature notes (all built, tests green)

- **3-Tier Clearance:** Default is Level 1 (Observer, read-only). Level 3 (Operator) unlocked via PIN modal for 30m; unlocks memory writes, dev tasks, apps, file navigator, and github checks. Level 5 (Architect) unlocked via password modal for 10m; unlocks settings, system mutations, full control. Instant lockdown via voice `"nightmare lock down"`, `"drop to level 1"`, or sleep mode. Visual badge in status bar/phone/mini view, dynamic theme pulsing (crimson/gold for Level 5, amber for Level 3).
- **CitizenGraph 4-Tab Telemetry & GDrive Diff Engine (Level 5):** Parses 4-sheet master workbook (`CitizenGraph_Thesis_Timeline_2026_2027-v2.xlsx`) via zero-dependency OpenXML parsing. Computes live Python rollups for Phase 1 (12 tasks, deadline Dec W2 2026), Phase 2 (9 tasks, deadline Feb 2027), 8-month roadmap (9 stages), overall WBS (21 tasks), and 6 quantitative Chapter 1 benchmark targets. Cross-references changes against stored SQLite baseline and shared Google Drive folder (`https://drive.google.com/drive/folders/1P4CWnBnYfLkkGKnrAswe9lwX5HcCQYDg?usp=sharing`). Auto-detects status transitions, schedule shifts, and completion deltas. Remodeled `TeamProgressPanel.jsx` delivers a single-active-tab desktop command-center experience with GSAP transitions and direct "Open in Excel", "Sync Baseline", and SMTP nudges.
- **PowerPoint Exact-Slide Presenter (Level 5):** Opens `.pptx` / `.ppt` presentations directly at specific slide numbers or resolves slides by topic using zero-dependency OpenXML parsing. Controls active slide shows (next, previous, jump to slide) via COM automation with PowerShell fallback.
- **System Authority (Level 5):** Background Nightmare restart (`scripts/start_nightmare.ps1 -Rebuild -Background`) and PC restart/shutdown with mandatory click confirmation (`needs_confirm=True`) and emergency abort via `cancel shutdown`.
- **Commands:** `nightmare_helper.txt` lists every voice/text command; Section 19 documents 3-Tier Security Clearance commands; Section 20 documents Level 3 Smart File Navigator & GitHub Intelligence; Section 21 documents Level 5 PowerPoint Presenter & System Authority; Section 22 documents Level 5 Shared Drive Excel Timeline Sync, 4-Tab CitizenGraph Telemetry & Diff Engine; `/help`, `/clear`, `/new`, `/reminders`, `/db`, `/settings`, `/sleep`, `/timeline`.

## 7. Code map

```
scripts/  install.ps1 nightmare_env.ps1 start_nightmare.ps1 setup_tailscale.ps1 install_autostart.ps1 uninstall_autostart.ps1 agy_smoke_test.py coldstart.py
backend/  __main__.py main.py(FastAPI, lifespan starts summary refresher & semantic warmup, /api/clearance/*, /api/team-tracker/*) config.py(.env, l3_pin, l5_password, team_excel_path, team_gdrive_*, smtp_*, repo_root) hotkey.py
  core/ router.py(regex intents, QUICK_*, CLEARANCE_*, FIND_OPEN_FILE_*, PPT_OPEN_SLIDE_*, PPT_CONTROL_*, SYSTEM_COMMAND_*, GITHUB_CHECK_*, TEAM_PROGRESS_*, TIMELINE_DIFF_*, APPROVE_EMAIL_*) semantic_router.py(FastEmbed ONNX & warmup, clearance/file/github/ppt/system/team exemplars)
        clearance.py(ClearanceManager, INTENT_CLEARANCE_MAP, tiers 1/3/5, inactivity decay, remote guard)
        orchestrator.py(handlers, _SummaryCache, refresher, timing, clearance checks, _do_open_file, _do_github_check, _do_ppt_open_slide, _do_ppt_control, _do_system_authority, _do_team_progress, _do_timeline_diff, _do_approve_email) memory.py(relevance recall)
        actions.py(Registry, plans, execute, PendingStore, plan_run_dev_task, plan_restart_nightmare, plan_restart_pc, plan_shutdown_pc, plan_cancel_shutdown, plan_send_team_nudge) apps_config.py llm.py(AgyProvider, NoLLMProvider)
  tools/ fs_reader.py file_navigator.py(safe indexing, fuzzy resolution, path traversal defense, safe_open_file) ppt_controller.py(XML slide parsing, COM automation, PowerShell fallback, exact-slide jump, topic resolution) team_tracker.py(zero-dependency OpenXML 4-tab parser, live rollups, GDrive diff engine, SQLite baseline) email_notifier.py(smtplib EmailMessage draft & delivery with Level 5 confirmation) weather.py audit.py(SQLite: actions, llm_calls, notes, summaries, facts, conversations, day_summaries, workspace_state, indexed_files, team_task_state, timeline_state) workspace.py(scans, dev tasks, briefings, priorities, git/gh checks) rag.py(ProjectRAG FastEmbed in-memory search)
  tests/ test_team_tracker.py(10 gates: 4-tab parsing, live rollups, GDrive diff detection, spoken summaries, Level 5 clearance & REST APIs) test_ppt_and_l5_system.py test_file_navigator.py 341 passed, 1 skipped (non-browser) + 8 browser tests
frontend/ src/App.jsx api.js components/*(ClearanceModal.jsx, TeamProgressPanel.jsx, StatusBar.jsx, EyeButton.jsx, NodeGraph.jsx, PhoneView.jsx, MiniView.jsx) utils/(useSpeech.js transcript.js useMic.js) tests/transcript.test.mjs
```

## 8. Security (keep)

- 3-Tier Security Clearance architecture: default Level 1 (Observer) blocks all mutations, dev tasks, and memory writes even on localhost. Elevation to Level 3 / Level 5 verified via constant-time `hmac.compare_digest` with rate-limiting (5 failed attempts per 60s window). Inactivity decay auto-drops privileges (30m for L3, 10m for L5). Remote sessions hard-capped at Level 1.
- Level 5 System Authority, Timeline & Email Nudging: raw command execution, PowerPoint exact-slide jumping, system mutations, timeline tracking, diff inspection, and email sending require Level 5 clearance. System restart, Nightmare reboot, and team email sending require explicit click confirmation (`needs_confirm=True`). Nightmare NEVER sends emails automatically; declining snoozes alerts for 24 hours in SQLite.
- LLM never chooses actions or sees paths/shell; documents go in `<handoff>`/`<document>` data tags with closing tags neutralized.
- `fs_reader` opens only handoff/safe `.md`/`.txt` (blocks `.env`, secret/password/credential/token names, `.pem`, `.key`, `id_rsa*`), resolves symlinks, stays inside the Desktop root.
- `file_navigator`, `ppt_controller` & `team_tracker` strictly verify path traversal boundaries against allowed user directories (`Desktop`, `Documents`, `Downloads`), block secret files, and require Level 3+ (file navigation) or Level 5 (PowerPoint automation, timeline tracking & diff engine).
- Closed-set LLM classifier can reach only read-only tools. Token/PINs only in `backend/.env`. Login rate-limited (5/60 s), HttpOnly SameSite=Strict cookies.
- Backend bound to 127.0.0.1; remote only via Tailscale serve + login. Settings/database need a typed PIN on laptop sessions. Everything logged to `backend/nightmare.db` and `backend/logs/nightmare.log`.

## 9. Roadmap and rules

- Phases 1, 1.5, 2, 3, 4, 6: **done**. Phase 5 (voice upgrade) is folded into Phase 7B.
- **Phase 7 plan:**
  - **A Speed:** done: more instant replies/fuzzy matching, persistent + background summaries, timing log. Left: A3 speak the first sentence while agy still streams (check feasibility first).
  - **C Memory (DONE):** conversations stored in SQLite, older turns condensed to a summary; "remember that X"/"forget X" facts, viewable/deletable in the database panel, phone read-only; recall only memories relevant to the question; raw conversations 90 days.
  - **D Workspace awareness (DONE):** background scan (no model) of git branch, uncommitted files, ahead/behind, last commit, handoff changes, TODO counts; briefings ("what changed since yesterday", "what should I work on", nudges); dev tasks found from package.json scripts/pytest/git ("run bims tests", "run it again") that always ask for a click; detection is plain code.
  - **B Offline:** measure first, switch only where faster than agy. Candidate local model: the user's fine-tuned Llama 3 8B Instruct (CPU-only is likely slow; propose before installing anything). faster-whisper (~150-500 MB) and Piper (~60 MB) need approval before download. Offline status bar; weather keeps its last reading.
- **Phase 8 plan (Defense & Clearance):**
  - **8A 3-Tier Security Clearance (DONE - UNVERIFIED live):** Level 1 (Observer), Level 3 (Operator), Level 5 (Architect). Inactivity decay, remote guard, constant-time elevation, rate-limiting, instant voice lockdown, GSAP masked modal and theme shifting.
  - **8B Level 3 Smart File Navigator & GitHub Intelligence (DONE - UNVERIFIED live):** safe file indexing and deterministic opening with path traversal defense; GitHub repo remote, PR, and conflict checks. Cache freshness and spoken query routing.
  - **8C Level 5 PowerPoint Exact-Slide Presenter & System Authority (DONE - UNVERIFIED live):** PowerPoint exact slide presenter with zero-dependency XML parsing and COM/PowerShell fallback; high authority system actions (PC restart, shutdown, Nightmare background reboot) requiring Level 5 and click confirmation.
  - **8D Level 5 Shared Drive Excel Timeline Sync, Team Quota Tracker & Email Nudger (DONE - UNVERIFIED live):** zero-dependency OpenXML parsing for 18-task timeline with fill colors (#9DC3E6 Core, #C6E0B4 Buffer, #FFD966 Milestone) and milestones; 3-day stale quota tracking in SQLite; mandatory Level 5 click/voice confirmation email reminders via SMTP.
  - **8D-2 Level 5 4-Tab CitizenGraph Telemetry, GDrive Diff Engine & Desktop Command Center (DONE - UNVERIFIED live):** zero-dependency OpenXML parsing for 4-tab `CitizenGraph_Thesis_Timeline_2026_2027-v2.xlsx`; live rollup metrics for Phase 1 (12 tasks), Phase 2 (9 tasks), Roadmap (9 stages), Overall WBS (21 tasks), and 6 quantitative Chapter 1 benchmark targets; SQLite `timeline_state` snapshot and GDrive diff engine; deterministic spoken summaries for `"nightmare what change in the citizengraph timeline from the gdrive"`; remodeled `TeamProgressPanel.jsx` 5-tab desktop command center with "Open in Excel", "Sync Baseline", and SMTP email controls.
  - **8E:** Hardened sandboxes & process boundary defense.
- **Rules:** update both handoff files after work; keep the LLM out of the action path (new actions via apps.json allowlist or validated read-only tools); backend stays on 127.0.0.1; never claim something works unless run on this machine; label UNVERIFIED.

## 10. Commands (PowerShell, project root)

```powershell
.\scripts\start_nightmare.ps1 -Rebuild      # rebuild UI + restart  (-Background for pythonw)
.\scripts\setup_tailscale.ps1 -Restart      # phone access (-Status, -Off)
.\scripts\install.ps1 -Dev                  # setup/repair, safe to re-run
.\scripts\install_autostart.ps1             # start at log on (backend + hotkey helper)
.\.venv\Scripts\python.exe scripts\coldstart.py                     # cold start & renew activity log benchmarks
.\.venv\Scripts\python.exe -m pytest backend -q -m "not browser"   # expect 341 passed, 1 skipped (349 passed with browser)
cd frontend; npm test
```
