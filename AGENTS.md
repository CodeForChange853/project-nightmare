# AGENTS.md — AI Coding Agent Instructions for Project Nightmare

Welcome to **Project Nightmare**, a local, security-hardened voice and text desktop command assistant for Windows. Follow the rules and architectural invariants in this file before making any code or documentation changes.

---

## 1. Mandatory First Steps (Start of Every Session)

1. **Read [`handoff.md`](handoff.md) first:** It contains the current project status, active constraints, recent milestones, request flow, and verification state.
2. **Keep [`handoff.md`](handoff.md) and [`newsession.md`](newsession.md) 100% identical:**
   - Nightmare's own `progress` voice/text command reads `handoff.md`.
   - Whenever you update `handoff.md` at the end of a milestone, copy its exact contents to `newsession.md` so the two files never drift.
3. **Never claim a feature or fix works without running tests:**
   - Run the backend and frontend test suites before concluding a task.
   - If a feature cannot be tested live in the user's desktop speech/hardware environment during the session, mark it **`**UNVERIFIED live**`** in `handoff.md`.

---

## 2. Core Architectural & Security Invariants (Never Violate)

1. **Single-Tier Level 5 (Architect) Clearance:**
   - Project Nightmare is a single-operator desktop system. All sessions run at **Level 5 (Architect)** (`LEVEL_5 = 5` in `backend/core/clearance.py`).
   - Do **not** reintroduce Level 1 or Level 3 clearance tiers, PIN/password elevation modals, or inactivity clearance decay timers.
2. **Mandatory Click Confirmation Gate (`needs_confirm=True`):**
   - High-impact and destructive actions (PC restart/shutdown, Nightmare background rebuild, dev tasks with `confirm=True`, and outbound SMTP email notifications) **must** enqueue into `PendingStore` (`backend/core/actions.py`) with `needs_confirm=True` and require an explicit UI click approval (`POST /api/confirm`).
3. **Remote Tailscale Read-Only Enforcement (`readonly=True`):**
   - Requests arriving over Tailscale (`PinAccess.role == "readonly"`) are strictly read-only. They must be blocked from launching apps, running tasks, mutating settings/memories/notes, starting defense sessions, or approving confirmations.
4. **Strict LLM Isolation (`backend/core/llm.py`):**
   - The LLM (`agy` headless CLI) **never** chooses actions, **never** executes shell commands, and **never** receives filesystem paths.
   - All action routing is decided deterministically by `backend/core/router.py`, `backend/core/context_buffer.py`, and `backend/core/semantic_router.py`.
   - External file contents passed to `agy` must be sanitized, stripped of secrets, wrapped in `<handoff>` tags, and executed from an isolated empty scratch directory with API key env vars scrubbed.
5. **No `shell=True` & Strict Filesystem Boundaries:**
   - Never use `shell=True` in `subprocess` calls. Always pass discrete argument lists.
   - All file readers and navigators (`fs_reader.py`, `file_navigator.py`, `ppt_controller.py`, `team_tracker.py`) must resolve symlinks, prune heavy directories (`node_modules`, `.venv`, `.git`, `dist`, `build`, `__pycache__`), block secret file patterns (`.env`, keys, credentials), and verify paths stay inside allowed roots (`Desktop`, `Documents`, `Downloads`).
6. **Zero Extra Heavy Dependencies / No Local LLM:**
   - Do **not** install Ollama or local SLMs/LLMs (Phase 7B was permanently dropped to protect the laptop's 16 GB RAM).
   - Use Python standard library (`zipfile` + `xml.etree.ElementTree`) for `.pptx` and `.xlsx` OpenXML parsing, and `ctypes.windll.kernel32` for Windows hardware telemetry.

---

## 3. Codebase Map

### Backend (`backend/`)
- **`backend/main.py`**: Slim FastAPI application factory (`create_app`), lifespan background workers (weather prefetcher, Gmail priority inbox sync), security headers & Host/Origin middleware, and static SPA mounting.
- **`backend/config.py`**: Loads configuration from `backend/.env` (`Settings` dataclass).
- **`backend/routers/`**: Modular FastAPI `APIRouter` package:
  - `deps.py` — `AppContext`, `SessionStore`, `PinAccess`, Pydantic request bodies, and `require_auth` / `require_full` guards.
  - `auth.py` — `/api/login`, `/api/logout`.
  - `chat.py` — `/api/chat`, `/api/session/reset`, `/api/help`, `/api/confirm`, `/api/audit`, `/api/events` (SSE), `/api/emails/*`, `/api/calendar/*`, `/api/tasks/measurable`.
  - `system.py` — `/api/status`, `/api/clearance/status`, `/api/weather`, `/api/window/mode`.
  - `telemetry.py` — `/api/system/telemetry`.
  - `defense.py` — `/api/defense/*` (Thesis Defense Co-Pilot).
  - `team_tracker.py` — `/api/team-tracker/*` (CitizenGraph 4-tab workbook, GDrive diff, SMTP notify).
  - `router_review.py` — `/api/router/review`, `/api/router/approve`.
  - `database.py` — `/api/db/*` (SQLite table viewer & item deletion).
  - `settings.py` — `/api/settings/*` (Allowlisted `apps.json` management).
- **`backend/core/`**:
  - `router.py` — Layer 1 pre-normalizer and deterministic regex router (`<1 ms`).
  - `context_buffer.py` — Layer 2 stateful 120s TTL buffer for ordinal (`"the first one"`) and pronoun (`"open it"`) resolution (`<5 ms`).
  - `semantic_router.py` — Layer 3 FastEmbed ONNX (`BAAI/bge-small-en-v1.5`) semantic classifier and margin-gated clarification.
  - `orchestrator.py` — Central command dispatcher, FastEmbed semantic response cache, SSE working status emitter, and turn telemetry logger.
  - `clearance.py` — Single-tier Level 5 Architect `ClearanceManager` and intent registry.
  - `actions.py` — Allowlisted app/task execution, `PendingStore`, and confirmation-gated system commands.
  - `apps_config.py` — Atomic `apps.json` persistence and rotating backups (`backend/backups/`).
  - `memory.py` — Conversation turn logging, condensation, and relevance recall.
  - `llm.py` — Sandboxed `AgyProvider` (`agy -p`) with voice conciseness injection (`~50–60 words`).
- **`backend/tools/`**:
  - `audit.py` — SQLite manager (`backend/nightmare.db`).
  - `file_navigator.py` — Hybrid trigram/phonetic file indexer and safe launcher.
  - `ppt_controller.py` & `ppt_worker.ps1` — Zero-dependency `.pptx` XML parser and persistent PowerShell COM worker (`<15 ms`).
  - `team_tracker.py` — 4-tab CitizenGraph `.xlsx` OpenXML parser and SQLite baseline diff engine.
  - `email_notifier.py` — IMAP priority email poller and confirmation-gated SMTP reminder sender.
  - `defense_copilot.py` & `defense_qa_data.py` — Slide-aware 12m defense stopwatch and 54-item pre-computed offline Q&A bank.
  - `system_telemetry.py` — Native Win32 `kernel32` CPU/RAM/Battery telemetry (`<0.2 ms`) and daemon `tasklist` worker.
  - `workspace.py`, `rag.py`, `fs_reader.py`, `weather.py` — Git scanner, local ONNX RAG retriever, safe markdown reader, and cached weather fetcher.

### Frontend (`frontend/src/`)
- **`App.jsx`**: Root state coordinator, SSE listener (`/api/events`), speech loop, and modal manager. Renders `Level5View.jsx` as the unified desktop HUD (`MiniView.jsx` for `Ctrl+Alt+N` mini mode; `PhoneView.jsx` for mobile viewports).
- **`api.js`**: REST API client wrapper.
- **`slashCommands.js`**: Slash command definitions (`/help`, `/timeline`, `/defense`, `/cockpit`, `/telemetry`, `/review`, `/reminders`, `/db`, `/settings`, `/clear`, `/new`, `/sleep`).
- **`components/`**: `Level5View.jsx`, `Orb.jsx`, `NodeGraph.jsx`, `TeamProgressPanel.jsx`, `DefensePanel.jsx`, `DatabasePanel.jsx`, `SettingsPanel.jsx`, `StatusBar.jsx`, `Terminal.jsx`, `Composer.jsx`, `Dossier.jsx`, `ConfirmDialog.jsx`, `MiniView.jsx`, `PhoneView.jsx`.
- **`utils/useSpeech.js`**: Web Speech API push-to-talk recognizer and `ProgressiveSentenceChunker` streaming TTS speaker.

---

## 4. How to Add a New Voice / Text Intent

1. **Define the Regex / Exemplars:**
   - Add deterministic regex matching in `backend/core/router.py` (`route()`), and/or semantic exemplars in `backend/core/semantic_router.py` (`INTENT_EXEMPLARS`).
2. **Register the Intent:**
   - Add the intent name to `INTENT_CLEARANCE` in `backend/core/clearance.py`.
   - If the intent mutates state or launches processes, ensure it is blocked when `readonly=True` in `Orchestrator.handle()` (`backend/core/orchestrator.py`).
3. **Implement the Handler:**
   - Add a deterministic tool in `backend/tools/` and wire it into `Orchestrator.handle()` in `backend/core/orchestrator.py`.
   - If the action is destructive or high-impact, wrap it in `PendingStore` with `needs_confirm=True`.
4. **Document & Test:**
   - Add example phrases to `nightmare_helper.txt`.
   - Add unit tests in `backend/tests/`.

---

## 5. Verification & Test Suite Commands

Always run these commands from the repository root (`C:\Users\Acer\Desktop\project-nightmare`) before finishing any task:

```powershell
# 1. Fast backend unit & integration tests (must pass 100%)
.\.venv\Scripts\python.exe -m pytest backend -q -m "not browser"

# 2. Offline router replay benchmark (verify fast-path match rate & <5ms average latency)
.\.venv\Scripts\python.exe scripts\replay_router.py

# 3. Frontend unit tests & production Vite build (must pass with zero errors)
cd frontend; npm test
cd frontend; npm run build
```
