# Project Nightmare

A local, security-hardened voice and text command assistant for Windows. Ask it, by voice or text, about the projects on your Desktop, workspace priorities, your reminders, the weather, to search project documentation, or to manage allowlisted apps, presentations, and team timelines.

Summaries and chat use your signed-in **Antigravity CLI (`agy`)** on the Google AI Pro subscription with zero API key and no separate billing. Safe local tools handle file navigation, PowerPoint automation, OpenXML spreadsheet parsing, and Git intelligence deterministically in Python without cloud LLM latency. Your Android phone can access it securely and strictly read-only over Tailscale.

```
[Voice / Text Input]
       │
       ▼
[FastAPI Server @ 127.0.0.1:<port>]
       │
       ├──► [3-Tier Security Clearance Guard]
       │      ├── Level 1: Observer (Default / Remote, Read-Only)
       │      ├── Level 3: Operator (PIN, 30m decay, Apps / Dev Tasks / Safe Files / Git)
       │      └── Level 5: Architect (Password, 10m decay, PPT / Timeline / Diff / System Authority)
       │
       ▼
[Multi-Tier Intent Router]
       ├── Tier 1: Deterministic Regex Router (<1 ms)
       ├── Tier 2: FastEmbed Semantic Vector Router (RAM-cached ONNX embeddings, instant warmup)
       └── Tier 3: Closed-Set Read-Only LLM Classifier (Fallback for conversational phrasing)
       │
       ├─────────────────────────────────┬─────────────────────────────────┐
       ▼                                 ▼                                 ▼
[Deterministic Python Tools]     [Confirmation Gated Actions]      [Antigravity CLI (`agy`)]
 • Smart File Navigator (L3+)     • App & Dev Task Launch (L3+)    • Gemini 3.8 Flash Low/High
 • GitHub Intelligence (L3+)      • PC Reboot & Shutdown (L5)      • Document / Handoff Summaries
 • PPT Exact-Slide Presenter (L5) • Nightmare Background Reboot(L5)• Conversational Chat
 • 4-Tab CitizenGraph Tracker(L5) • Team Stale Email Nudger (L5)   (Never touches shell or paths;
 • GDrive Diff Engine (L5)                                         never chooses actions)
 • Workspace Awareness & RAG
```

The full voice and text command list is in `nightmare_helper.txt` (or type `/help`). Complete phase logs, design notes, and security boundaries are documented in `handoff.md` and `newsession.md`.

---

## 3-Tier Security Clearance Architecture

Project Nightmare implements a defense-in-depth, 3-tier clearance model. Startup defaults to Level 1 Observer for all sessions, ensuring no actions or mutations can run without explicit elevation.

| Clearance Tier | Name | Authentication & TTL | Capabilities & Boundaries |
|---|---|---|---|
| **Level 1** | **Observer** *(Default)* | Default on startup; remote sessions hard-capped at L1 | Strictly read-only. Access project progress, daily briefings, READMEs, weather, reminders, local RAG search, conversation recall, and chat. Blocks app launching, file opening, memory writes, and system commands. |
| **Level 3** | **Operator** | 6-digit PIN (`NIGHTMARE_L3_PIN`); 30-minute inactivity decay | Unlocks allowlisted app launches, dev task execution, persistent memory writes ("remember that X"), Safe File Navigator, and GitHub repository intelligence. |
| **Level 5** | **Architect** | Master password (`NIGHTMARE_L5_PASSWORD`); 10-minute inactivity decay | Full system authority. Unlocks Settings, PowerPoint exact-slide automation, CitizenGraph 4-tab telemetry & GDrive diff engine, team email nudging, PC restart/shutdown, and Nightmare background rebuilding. |

- **Elevation:** Say `"nightmare open level 3"` or `"nightmare open level 5"` (or click the clearance badge) to trigger the authentication modal. Elevated credentials use constant-time `hmac.compare_digest` with strict rate-limiting (5 attempts per 60 seconds).
- **Instant Lockdown:** Say `"nightmare lock down"`, `"drop to level 1"`, or enter sleep mode (`/sleep`) to immediately revoke elevated privileges and drop back to Level 1.
- **Inactivity Decay:** Clearance automatically drops to Level 1 after 30 minutes of idle time for Level 3, and 10 minutes for Level 5.
- **Remote Hard Cap:** Tailscale remote sessions are strictly hard-capped at Level 1 Observer and cannot elevate, even with valid credentials.

---

## Key Features

### 1. Voice & Speech Synthesis
- **Orb & Spacebar Control:** Hold down the Orb eye button or the Spacebar to speak, release to send.
- **Dual Voice Synthesis:** High-quality speech synthesis with male and female voice switching (`"switch voice to female"`, `"switch voice to male"`) and speed control (`0.9x` to `1.5x`).
- **Accent Toggles:** Instant status-bar switching between `mic: en-PH` and `mic: en-US`.
- **Session Memory:** Natural conversation recall (`"what did we discuss earlier"`) and persistent facts (`"remember that X"`, `"forget X"`).

### 2. Workspace Awareness & Local RAG
- **Zero-Latency Briefings:** Plain Python background scanners evaluate Git branches, uncommitted files, commits ahead/behind, TODO counts, and project priorities (`"workspace briefing"`, `"what changed since yesterday"`, `"what should I work on"`).
- **Local Project RAG:** Semantic vector search across Desktop project documentation using RAM-cached FastEmbed ONNX embeddings (`"search projects for authentication"`). Responds in ~15-30 ms without cloud API overhead.

### 3. Smart File Navigator & GitHub Intelligence (Level 3+)
- **Safe File Indexing:** Fast indexing across `Desktop`, `Documents`, and `Downloads` for safe document formats (`.pptx`, `.ppt`, `.docx`, `.doc`, `.xlsx`, `.pdf`, `.txt`, `.md`).
- **Boundary Defense:** Traversal protections strictly skip `.git`, `node_modules`, `.venv`, `AppData`, and secret patterns (`.env`, passwords, credentials, keys).
- **Safe Opening:** Voice commands like `"find file related to timeline and open it in word or powerpoint"` safely launch files with automated disambiguation.
- **GitHub Intelligence:** Checks remote commit status, open PRs, and merge conflicts across Desktop repos (`"check my github repositories"`, `"github status"`).

### 4. PowerPoint Exact-Slide Presenter (Level 5)
- **Zero-Dependency XML Parsing:** Parses `.pptx` archives directly using standard library `zipfile` + `xml.etree.ElementTree` to index slide titles, bodies, and numbers.
- **COM Automation with PowerShell Fallback:** Controls presentation slide shows via Windows COM interop (falling back seamlessly to PowerShell COM if `pywin32` is absent).
- **Direct Voice Navigation:**
  - Jump directly to a slide: `"find and open citizengraph ppt and show slide 5"`, `"go to slide 7"`.
  - Topic matching: `"show the slide about dataset preprocessing"`.
  - Presentation controls: `"next slide"`, `"previous slide"`.

### 5. CitizenGraph 4-Tab Telemetry, Shared Drive Excel Sync & GDrive Diff Engine (Level 5)
- **4-Tab Master Workbook Telemetry:** Parses the 4-sheet master workbook (`CitizenGraph_Thesis_Timeline_2026_2027-v2.xlsx`) and backwards-compatible timelines:
  1. **General 8-Month Roadmap:** STG-01..STG-09 stages, active month indicators, and milestones.
  2. **Detailed Weekly Gantt:** 21 WBS tasks (1.1..1.12 Phase 1, 2.1..2.9 Phase 2) compressed across 24 weekly spans.
  3. **Objectives & KPI Alignment:** SO-1..SO-7 objectives, architectural components, datasets, and benchmark targets.
  4. **Phase Summary & Dashboard:** Live Python rollups (Phase 1, Phase 2, Overall WBS) and 6 quantitative Chapter 1 benchmark targets (Return-Trip Prevention >= 90%, Exact-Match Accuracy >= 95%, Gap Analysis M = R \ H >= 90%, Topological Sequence >= 90%, Post-AST Execution >= 95%, Edge Latency <= 5.0s).
- **SQLite GDrive Diff Engine:** Categorizes status transitions, schedule shifts, deliverable edits, and completion deltas against a stored baseline (`"nightmare what change in the citizengraph timeline from the gdrive"`).
- **Desktop Command Center (`/timeline`):** High-density single-active-tab desktop UI (`TeamProgressPanel.jsx`) with Obsidian/Crimson styling, GSAP tab transitions, [CHECK GDRIVE / DIFF], [OPEN IN EXCEL], and [SYNC BASELINE] controls.
- **Team Quota Tracker & Stale Nudger:** Tracks quotas and flags tasks un-updated for >= 3 days. Generates draft email reminders via `smtplib`, requiring Level 5 click/voice confirmation to send (`"approve email"`).

### 6. System Authority Commands (Level 5)
- **Controlled System Management:** Rebuild and restart Nightmare in the background (`"rerun yourself"`, `"restart nightmare"`) or restart/shut down your PC (`"restart my pc"`, `"shut down my pc"`).
- **Mandatory Confirmation Gate:** High-authority system commands and email notifications always enforce `needs_confirm=True` (click confirmation or voice `"approve"` in Level 5).
- **Emergency Abort:** Immediate abort via `"cancel shutdown"` executes `shutdown /a` without waiting for confirmation.

### 7. Global Hotkey Mini-Window & Phone Companion
- **Always-on-Top Mini Window:** Press **Ctrl+Alt+N** from any application to summon a lightweight, compact Nightmare window. Hold Space to speak. Say `"home"` to expand or `"mini"` to shrink.
- **Phone Companion (Tailscale):** Mobile-optimized UI featuring a 4-tab bar (Talk / Projects / Reminders / Chat). Strictly read-only over Tailscale.

---

## Slash Commands

Type `/` into the command input box to access quick shortcuts:
- `/help` — Opens the interactive Developer Helper overlay (`nightmare_helper.txt`).
- `/timeline` — Opens the Level 5 CitizenGraph Telemetry & GDrive Diff Command Center.
- `/clear` or `/new` — Resets conversation history and starts a fresh session.
- `/reminders` — Lists active notes and reminders.
- `/db` — Opens the SQLite database viewer (Activity log, reminders, memories).
- `/settings` — Opens allowlisted app configuration and task manager.
- `/sleep` — Enters standby sleep mode and locks clearance down to Level 1.

---

## Phone Access (Tailscale, Read-Only)

1. Install Tailscale on your laptop and phone under the same account; enable MagicDNS and HTTPS Certificates in the Tailscale admin console.
2. Set `NIGHTMARE_PHONE_PIN` in `backend\.env` (6+ digits).
3. Run `.\scripts\setup_tailscale.ps1 -Restart`, then open the printed `https://<laptop>.<tailnet>.ts.net/` in Chrome on your phone.

Everything arriving through Tailscale is enforced read-only and hard-capped at **Level 1 Observer**. The phone can query project progress, Git status, briefings, documents, weather, reminders, and chat, but cannot launch apps, run dev tasks, open files, approve actions, open Settings, access the raw database, or elevate clearance.

---

## Safety & Security Model

- **The LLM Never Decides Actions:** All intent routing is governed deterministically by Regex, local FastEmbed ONNX vectors, and allowlist configurations. `agy` only summarizes text or engages in conversational chat; it never selects actions or executes system calls.
- **The LLM Never Gets a Shell or Filesystem Path:** Project files reach `agy` strictly as sanitized, quoted text. Sensitive variables, tokens, and API keys are scrubbed before invocation, and `agy` executes inside an isolated scratch directory.
- **Strict Boundary Traversal Defense:** Python file readers, `file_navigator`, `ppt_controller`, and `team_tracker` strictly validate path boundaries against allowed user roots (`Desktop`, `Documents`, `Downloads`). They reject `.env`, credentials, secrets, private keys, `.git`, `node_modules`, and Windows system folders.
- **No `shell=True`:** All system subprocesses launch from discrete argument lists; `.cmd`/`.bat` launchers reject special characters.
- **Mandatory Click Confirmations:** Tasks added or edited in Settings, dev tasks, PowerPoint launches, PC reboot/shutdown, and email notifications enforce mandatory confirmations (`needs_confirm=True`). Voice commands cannot bypass confirmation without Level 5 authorization.
- **Localhost Binding & Origin Checks:** The backend binds strictly to `127.0.0.1`. Requests require local `Host` headers (preventing DNS rebinding) and verified `Origin` headers.
- **Protected Settings & Database:** Settings changes and database inspection require explicit authentication. Saves are validated, atomic, backed up (retaining the last 5 in `backend\backups\`), and refuse to overwrite manual edits.
- **Audit Logging:** Every activity, confirmation, model call, and timeline state is logged to `backend\nightmare.db` (auto-pruned after `LOG_RETENTION_DAYS`).

---

## Install & Setup (Windows PowerShell)

### Prerequisites
- Windows 11 / 10
- Python 3.11+ (in PATH or venv)
- Node.js 20.19+ or 22.12+
- Google Chrome
- Antigravity CLI (`agy`) signed in to your Google AI Pro account

### Installation
```powershell
cd project-nightmare
.\scripts\install.ps1                 # Initializes venv, installs dependencies, builds frontend, configures backend\.env
.\scripts\start_nightmare.ps1 -Background
```

Open **http://127.0.0.1:8000** (or your configured `NIGHTMARE_PORT`) in Google Chrome and enter your laptop PIN.

`install.ps1` options:
- `-Autostart`: Registers Nightmare in Windows startup (backend + hotkey helper).
- `-Shortcut`: Creates a Desktop shortcut that launches Nightmare in an app-mode Chrome window.
- `-Dev`: Installs developer and testing tools (`pytest`, `playwright`).

---

## Configuration (`backend/.env`)

| Variable | Description |
|---|---|
| `NIGHTMARE_TOKEN` | Required. Secret session API token. |
| `DESKTOP_ROOT` | Allowed root directory (defaults to user's `Desktop` or `OneDrive\Desktop`). |
| `NIGHTMARE_PIN` | 6-digit PIN for laptop browser session authentication. |
| `NIGHTMARE_PHONE_PIN` | 6-digit PIN for read-only phone sessions over Tailscale. |
| `NIGHTMARE_L3_PIN` | Level 3 Operator clearance PIN (defaults to `NIGHTMARE_PIN`). |
| `NIGHTMARE_L5_PASSWORD` | Level 5 Architect clearance secret password. |
| `NIGHTMARE_ALLOWED_HOSTS` | Comma-separated Tailscale hostnames for phone access. |
| `NIGHTMARE_HOTKEY` | Global hotkey for mini-window toggle (default: `ctrl+alt+n`). |
| `NIGHTMARE_TEAM_EXCEL_PATH` | Path to local Google Drive / OneDrive synced timeline `.xlsx`. |
| `NIGHTMARE_TEAM_GDRIVE_FOLDER_URL` | Shared Google Drive folder URL for team timeline cross-referencing. |
| `SMTP_HOST`, `SMTP_PORT` | SMTP server settings for team quota email reminders (default: `smtp.gmail.com:587`). |
| `SMTP_USER`, `SMTP_APP_PASSWORD` | Credentials for sending approved email reminders. |
| `LOG_RETENTION_DAYS` | Number of days to retain activity audit logs (default: `90`). |

---

## Development & Testing

```powershell
# Set up development tools and test environment
.\scripts\install.ps1 -Dev

# Run fast backend unit & integration tests (~20s, 341 tests pass, 1 skipped)
.\.venv\Scripts\python.exe -m pytest backend -q -m "not browser"

# Run all backend tests including Playwright Chrome browser tests (~1 min, 349 tests pass)
.\.venv\Scripts\python.exe -m pytest backend -q

# Run frontend unit tests (5 tests pass)
cd frontend; npm test

# Run coldstart benchmark & warmup checks
.\.venv\Scripts\python.exe scripts\coldstart.py

# Rebuild frontend and restart Nightmare
.\scripts\start_nightmare.ps1 -Rebuild
```

---

## Codebase Map

| Path | Description |
|---|---|
| `backend/main.py` | FastAPI application, authentication middleware, clearance endpoints, team tracker REST APIs. |
| `backend/config.py` | Configuration settings parsed from `backend/.env`. |
| `backend/hotkey.py` | Windows global hotkey hook (`Ctrl+Alt+N`) for summon, resize, and hide via `ctypes`. |
| `backend/core/clearance.py` | 3-Tier Security Clearance manager (`ClearanceManager`), intent maps, and inactivity decay. |
| `backend/core/router.py` | Deterministic regex intent router matching voice and text commands. |
| `backend/core/semantic_router.py` | FastEmbed ONNX semantic vector router with RAM-cached embeddings and instant warmup. |
| `backend/core/orchestrator.py` | Central dispatch, summary caches, clearance validation, and tool execution. |
| `backend/core/actions.py` | Action registry, confirmation store (`PendingStore`), and system authority executors. |
| `backend/core/apps_config.py` | Allowlist settings validator, atomic configuration file persistence, and automatic backups. |
| `backend/core/memory.py` | Conversation turn logging, session memory condensation, and relevance recall. |
| `backend/core/llm.py` | Antigravity CLI (`agy`) headless subprocess wrapper with scratch folder isolation. |
| `backend/tools/file_navigator.py` | Safe multi-directory file indexing, path traversal defense, and deterministic file opening. |
| `backend/tools/ppt_controller.py` | Zero-dependency OpenXML PowerPoint slide parser, COM automation, and slide-show controller. |
| `backend/tools/team_tracker.py` | Zero-dependency OpenXML 4-tab workbook parser, live metric rollups, and GDrive diff engine. |
| `backend/tools/email_notifier.py` | `smtplib` notification builder with Level 5 confirmation workflow for stale team tasks. |
| `backend/tools/workspace.py` | Workspace git branch/dirty scanning, TODO analysis, daily briefings, and GitHub CLI checks. |
| `backend/tools/rag.py` | Local document RAG retriever using RAM-cached FastEmbed embeddings. |
| `backend/tools/audit.py` | SQLite audit store for actions, LLM calls, memories, indexed files, team tasks, and timeline states. |
| `backend/tools/fs_reader.py` | Safe document and handoff reader with symlink resolution and sensitive file protection. |
| `backend/tools/weather.py` | Weather information fetcher with 10-minute caching. |
| `frontend/src/App.jsx` | Main React entry point, status indicators, panel routing, and layout coordinator. |
| `frontend/src/components/ClearanceModal.jsx` | Authentication modal for Level 3 PIN and Level 5 password elevation. |
| `frontend/src/components/TeamProgressPanel.jsx` | Desktop command center for 4-tab CitizenGraph telemetry, GDrive diffs, and email controls. |
| `frontend/src/components/NodeGraph.jsx` | Interactive project graph visualization rendered with GSAP. |
| `frontend/src/components/MiniView.jsx` | Always-on-top compact floating window for Ctrl+Alt+N hotkey access. |
| `frontend/src/components/PhoneView.jsx` | Mobile-optimized 4-tab interface (Talk, Projects, Reminders, Chat) for Tailscale users. |
| `frontend/src/components/StatusBar.jsx` | Clearance level badge, speech recognition language toggle, and connection indicators. |
| `frontend/src/utils/useSpeech.js` | Chrome Web Speech API integration, dual voice selection, and speed regulation. |
| `scripts/` | PowerShell automation scripts: installation, startup, autostart, smoke tests, and Tailscale setup. |
