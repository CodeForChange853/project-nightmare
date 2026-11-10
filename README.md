# Project Nightmare

### Free voices and Mandarin meeting captions

Open **Voice** on the desktop HUD (or type `/voice`) to choose and preview the voices your browser exposes. Automatic selection prefers available natural/online and Google English voices within the selected gender; playback uses natural pitch. Voice and speed choices persist in this browser. No paid speech API or model download was added. Voice quality depends on the actual browser voice inventory, and online voices require internet.

Open **Meeting** (or type `/meeting` or `/transcribe`) for Mandarin Chinese captions with English translations. Choose microphone, PC/tab audio, or both, then click **Start captions**. For online calls, desktop Chrome 135+ can pass shared audio to recognition; select the meeting tab or screen and enable **Share audio**. Native meeting applications require sharing a screen with system audio where the picker supports it. Missing shared audio produces an error rather than switching to the microphone. Headphones help avoid duplicate audio in mixed mode.

Chinese interim captions come from the browser speech service. Finalized text is translated sequentially through the existing signed-in `agy` provider, so English can lag behind speech, particularly during long meetings or other model calls. Translation can be paused and failed rows retried. Export the timestamped Chinese/English transcript before closing; it is not saved to conversation memory. Export/clear at the 2,000-row session limit.

Meeting captions never enter the command router, and desktop command listening, spoken notifications, and idle sleep are suspended while the panel is open. The translation endpoint requires a local full-access session, rejects remote read-only requests, sanitizes text before wrapping it in `<handoff>` tags, and uses the existing isolated CLI provider. Browser speech services may send audio online; translation sends finalized text to your existing provider. Let meeting participants know you are transcribing.

**UNVERIFIED live:** actual Mandarin accuracy, microphone/system audio on this desktop, available voice quality, and real `agy` translation latency. Automated tests use simulated speech and translation; test with a short Mandarin clip before your meeting.

**Project Nightmare** is a local, security-hardened voice and text command assistant for Windows. Designed as a single-tier **Level 5 Architect** desktop command center, it lets you inspect and manage Desktop projects, run allowlisted apps and dev tasks, navigate local files, control PowerPoint slide shows by voice, track thesis timelines & Google Drive diffs, rehearse academic thesis defenses offline, and monitor real-time hardware telemetry.

Summaries and conversational chat use your signed-in **Antigravity CLI (`agy`)** on a Google AI Pro subscription with zero API keys and no separate billing. Deterministic Python and native Windows tools execute fast-path commands in `<50 ms` without cloud latency, while your Android phone can connect strictly read-only over Tailscale.

```
[Voice (Web Speech PTT) / Text Input]
       │
       ▼
[FastAPI Server @ 127.0.0.1:<port> (Modular Routers: backend/routers/*)]
       │
       ├──► [Security & Authority Boundary]
       │      ├── Desktop Session: Permanent Level 5 (Architect) Authority
       │      ├── Remote Tailscale Session: Strictly Read-Only Enforced
       │      └── High-Impact Actions: Mandatory Click Confirmation Gate (needs_confirm=True)
       │
       ▼
[4-Layer Deterministic & Semantic Intent Router]
       ├── Layer 1: Pre-Router Normalizer & Deterministic Regex Router (<1 ms)
       ├── Layer 2: Stateful ConversationContext Buffer (120s TTL, <5 ms ordinal/pronoun resolution)
       ├── Layer 3: FastEmbed ONNX Semantic Router + Margin-Gated Clarification
       └── Layer 4: Closed-Set Read-Only LLM Classifier + FastEmbed Semantic Cache (<25 ms)
       │
       ├──────────────────────────────────┬──────────────────────────────────┐
       ▼                                  ▼                                  ▼
[Deterministic Local Tools]       [Confirmation-Gated Actions]       [Antigravity CLI (`agy`)]
 • Smart File Navigator            • Allowlisted App & Task Launch    • Gemini 3.8 Flash Low/High
 • GitHub & Workspace Intelligence • PC Reboot & Shutdown             • Document / Handoff Summaries
 • Persistent PPT COM Presenter    • Nightmare Background Rebuild     • Concise Voice Chat (~50-60w)
 • 4-Tab CitizenGraph Tracker      • Team Stale Email Nudger (SMTP)   (Runs in empty scratch sandbox;
 • SQLite GDrive Diff Engine                                           never touches shell or paths;
 • Offline Thesis Defense Co-Pilot                                     never chooses actions)
 • Native Win32 Hardware Telemetry
```

The complete voice and text command reference is in [`nightmare_helper.txt`](nightmare_helper.txt) (or type `/help` in the UI). Session context, architectural invariants, and phase history are maintained in [`handoff.md`](handoff.md) and [`AGENTS.md`](AGENTS.md).

---

## Security & Authority Model (Single-Tier Level 5 Architect)

Project Nightmare operates under a permanent **Level 5 (Architect)** single-tier clearance model for the local desktop operator, paired with defense-in-depth execution guards:

| Boundary | Mechanism | Protection Provided |
|---|---|---|
| **Single-Tier Authority** | **Level 5 (Architect)** | Full desktop access to workspace tools, file navigation, PowerPoint COM control, CitizenGraph timeline telemetry, Thesis Defense Co-Pilot, and Settings without recurring PIN/password prompts or inactivity lockouts. |
| **Mandatory Click Confirmation** | `needs_confirm=True` (`PendingStore`) | High-impact mutations—PC restart/shutdown, Nightmare background rebuild, dev tasks, and outbound SMTP emails—always require an explicit UI click approval (`ConfirmDialog`) before execution. |
| **Remote Read-Only Guard** | `readonly=True` (Tailscale) | Phone sessions connecting via Tailscale are strictly read-only. They can query progress, briefings, docs, reminders, weather, and chat, but cannot launch apps, run tasks, mutate settings, or approve confirmations. |
| **LLM Sandbox Isolation** | `AgyProvider` (`backend/core/llm.py`) | The LLM **never** chooses actions, **never** receives filesystem paths or shell access, and runs inside an isolated empty scratch folder with sensitive environment variables scrubbed. |
| **Filesystem Boundary Defense** | `fs_reader.py` & `file_navigator.py` | Path resolution strictly enforces allowed user roots (`Desktop`, `Documents`, `Downloads`), resolves symlinks, prunes heavy directories (`node_modules`, `.git`, `.venv`), and blocks sensitive files (`.env`, keys, credentials). |
| **No `shell=True`** | `actions.py` | All subprocesses execute from discrete argument arrays; `.cmd`/`.bat` wrappers reject shell metacharacters. |

---

## Key Features

### 1. Level 5 Infernal Command Center & Voice Interface
- **Unified Desktop HUD (`Level5View.jsx`):** Features the interactive **Crimson Cosmic Eye Sigil** (`Orb.jsx`), branching GSAP project graph (`NodeGraph.jsx`), collapsible left navigation sidebar, live hardware/weather status bar, and recent activity launcher strip.
- **Push-to-Talk & First-Sentence Streaming TTS:** Hold the **Spacebar** or the **Eye button** to speak. Progressive sentence chunking (`useSpeech.js`) begins speaking the first sentence immediately while subsequent text streams in, with dual voice selection (`male` / `female`), speed cycling (`0.9x`–`1.5x`), and mic locale toggling (`en-PH` / `en-US`).
- **Global Hotkey Mini-Window:** Press **Ctrl+Alt+N** from any Windows application to summon an always-on-top compact floating window (`MiniView.jsx`).

### 2. Workspace Awareness, Smart File Navigator & Local RAG
- **Zero-Latency Workspace Briefings:** Background Python scanners inspect Desktop Git repositories for branch state, uncommitted changes, ahead/behind counts, TODOs, and project priorities (`"workspace briefing"`, `"what changed since yesterday"`).
- **Hybrid Trigram & Phonetic File Search:** Indexes safe documents (`.pptx`, `.docx`, `.xlsx`, `.pdf`, `.txt`, `.md`) across `Desktop`, `Documents`, and `Downloads`, resolving phonetic Web Speech distortions and ordinal follow-ups (`"the first one"`, `"open it"`) in `<5 ms`.
- **Local Project RAG:** In-memory FastEmbed ONNX (`BAAI/bge-small-en-v1.5`) vector search across Desktop documentation (`"search projects for authentication"`) with a hard `3.0s` timeout guard.

### 3. Persistent PowerPoint Exact-Slide Presenter
- **Zero-Dependency OpenXML Indexing:** Parses `.pptx` files directly via Python `zipfile` + `xml.etree.ElementTree` to index slide titles, body text, and slide numbers.
- **Sub-15ms Persistent COM Worker (`ppt_worker.ps1`):** Maintains a persistent background PowerShell/COM bridge so slide jumps (`"go to slide 5"`), topic searches (`"show the slide about dataset preprocessing"`), and transitions (`"next slide"`, `"previous slide"`) execute in `~4–15 ms` and auto-launch the slideshow if inactive.

### 4. CitizenGraph 4-Tab Telemetry, GDrive Diff Engine & Priority Inbox
- **4-Tab Master Workbook Parser (`team_tracker.py`):** Parses `CitizenGraph_Thesis_Timeline_2026_2027-v2.xlsx` using zero-dependency OpenXML into:
  1. **General 8-Month Roadmap** (`STG-01`–`STG-09` milestones & dependencies)
  2. **Detailed Weekly Gantt** (21 WBS tasks across Phase 1 & Phase 2)
  3. **Objectives & KPI Alignment** (`SO-1`–`SO-7` & Chapter 1 quantitative targets)
  4. **Phase Summary & Dashboard** (Live completion rollups)
- **SQLite GDrive Diff Engine:** Compares live synced workbooks against stored SQLite baselines to report status transitions, schedule shifts, and completion deltas (`"what changed in the citizengraph timeline"`).
- **Priority Inbox & Stale Task Nudger:** Streams real-time priority email toast notifications via SSE and drafts SMTP reminder emails for stale tasks (requiring click confirmation to send).

### 5. Offline Academic Thesis Defense Co-Pilot
- **Slide-Aware 12-Minute Stopwatch (`defense_copilot.py`):** Tracks per-slide pacing budgets (`on_pace`, `nearing_limit`, `over_budget`) synchronized with active PowerPoint slides.
- **Pre-Computed 54-Q&A Offline Bank (`defense_qa_data.py`):** Stores 54 CitizenGraph defense questions and ground-truth rubrics (Methodology, System Architecture, Problem Statement/RRL, Benchmarks) with pre-computed 384-dim ONNX embeddings in SQLite for `<30 ms` 100% offline panelist Q&A rehearsal and answer evaluation.

### 6. Native Hardware Telemetry Cockpit
- **Sub-Millisecond Win32 Metrics (`system_telemetry.py`):** Queries `ctypes.windll.kernel32` directly for zero-sleep CPU load deltas, physical RAM usage, and battery status (`<0.2 ms`), paired with a daemon background thread polling top processes every 5 seconds.

---

## Slash Commands

Type `/` into the command composer for instant shortcuts:

| Command | Action |
|---|---|
| `/help` | Opens the interactive Developer Helper reference (`nightmare_helper.txt`). |
| `/timeline` | Opens the CitizenGraph 4-Tab Telemetry, GDrive Diff & Priority Inbox Command Center. |
| `/defense` | Opens the Academic Thesis Defense Co-Pilot HUD. |
| `/cockpit` or `/telemetry` | Queries live CPU, RAM, battery, and top process telemetry. |
| `/review` | Opens the Router Miss Review queue to promote unrecognized utterances into semantic exemplars. |
| `/reminders` | Lists active reminders and notes. |
| `/db` | Opens the SQLite Database Inspector (activity log, turns telemetry, reminders, memories). |
| `/settings` | Opens the allowlisted Apps & Tasks manager. |
| `/clear` or `/new` | Clears conversation history and resets the session cache. |
| `/sleep` | Puts Nightmare into Cosmic Idle Standby mode. |

---

## Project Architecture & Directory Structure

The codebase is modularized so co-developers can navigate backend API routers, core routing/orchestration logic, deterministic tools, and React UI components independently:

```text
project-nightmare/
├── AGENTS.md                        # AI Agent & Co-Developer onboarding instructions
├── README.md                        # Project overview, setup, and architecture guide
├── handoff.md / newsession.md       # Synchronized session state & engineering log (kept 100% identical)
├── nightmare_helper.txt             # Complete voice & text command reference
├── scripts/                         # PowerShell setup, launcher, Tailscale, & benchmark scripts
│   ├── install.ps1                  # One-step venv + npm + .env installer
│   ├── start_nightmare.ps1          # Launches/rebuilds backend + hotkey helper
│   ├── setup_tailscale.ps1          # Configures read-only Tailscale HTTPS access for phone
│   ├── coldstart.py                 # Cold-start & fast-path latency benchmark
│   └── replay_router.py             # Offline router accuracy & latency replay harness
├── backend/
│   ├── main.py                      # Slim FastAPI app factory, lifespan workers, middleware & static mount
│   ├── config.py                    # Environment configuration & path settings (backend/.env)
│   ├── hotkey.py                    # Windows global hotkey hook (Ctrl+Alt+N) via ctypes
│   ├── routers/                     # Modular FastAPI APIRouter package
│   │   ├── __init__.py              # Assembles /api router from domain modules
│   │   ├── deps.py                  # Shared AppContext, SessionStore, PinAccess, Pydantic schemas & guards
│   │   ├── auth.py                  # /api/login, /api/logout
│   │   ├── chat.py                  # /api/chat, /api/confirm, /api/events (SSE), /api/emails/*, /api/calendar/*
│   │   ├── system.py                # /api/status, /api/clearance/status, /api/weather, /api/window/mode
│   │   ├── telemetry.py             # /api/system/telemetry
│   │   ├── defense.py               # /api/defense/* (Thesis Defense Co-Pilot endpoints)
│   │   ├── team_tracker.py          # /api/team-tracker/* (CitizenGraph timeline, GDrive diff, SMTP notify)
│   │   ├── router_review.py         # /api/router/review, /api/router/approve
│   │   ├── database.py              # /api/db/* (SQLite table viewer & note/memory deletion)
│   │   └── settings.py              # /api/settings/* (Allowlisted apps.json editor & task detector)
│   ├── core/                        # Core routing, orchestration, memory & LLM isolation
│   │   ├── clearance.py             # Single-tier Level 5 Architect manager & intent registry
│   │   ├── router.py                # Layer 1 Pre-normalizer & deterministic regex intent router
│   │   ├── context_buffer.py        # Layer 2 Stateful 120s TTL ordinal & pronoun context buffer
│   │   ├── semantic_router.py       # Layer 3 FastEmbed ONNX vector router & margin-gated clarification
│   │   ├── orchestrator.py          # Central command dispatcher, semantic cache & turn telemetry
│   │   ├── actions.py               # Allowlisted app/task runner, PendingStore & system power commands
│   │   ├── apps_config.py           # Atomic apps.json validator & rotating backup manager
│   │   ├── memory.py                # Session memory condensation & relevance recall
│   │   └── llm.py                   # Sandboxed Antigravity CLI (agy) subprocess wrapper
│   ├── tools/                       # Deterministic local Python & Win32 tools
│   │   ├── audit.py                 # SQLite store (turns, actions, memories, caches, defense Q&A, timeline)
│   │   ├── file_navigator.py        # Hybrid trigram/phonetic file indexer & safe launcher
│   │   ├── ppt_controller.py        # Zero-dependency .pptx XML parser & persistent COM controller
│   │   ├── ppt_worker.ps1           # Persistent PowerShell COM worker for sub-15ms slide control
│   │   ├── team_tracker.py          # 4-tab OpenXML workbook parser & GDrive diff engine
│   │   ├── email_notifier.py        # Gmail/IMAP priority sync & confirmation-gated SMTP nudger
│   │   ├── defense_copilot.py       # Defense stopwatch, slide pacing & offline semantic answer scorer
│   │   ├── defense_qa_data.py       # 54 pre-computed CitizenGraph thesis defense Q&A pairs
│   │   ├── system_telemetry.py      # Win32 kernel32 CPU/RAM/Battery metrics & daemon process poller
│   │   ├── workspace.py             # Desktop Git scanner, briefings & concurrent GitHub CLI checker
│   │   ├── rag.py                   # Local FastEmbed document chunk retriever
│   │   ├── fs_reader.py             # Boundary-checked markdown/text reader
│   │   └── weather.py               # Cached weather fetcher with background prefetcher
│   └── tests/                       # Pytest unit, integration, security & Playwright browser test suite
└── frontend/
    └── src/
        ├── App.jsx                  # Root coordinator, SSE listener, speech loop & modal controller
        ├── api.js                   # Typed REST client & AuthError handler
        ├── slashCommands.js         # Slash command registry & autocomplete metadata
        ├── components/              # Modular React UI components
        │   ├── Level5View.jsx       # Primary desktop HUD (Infernal Command Center)
        │   ├── Orb.jsx              # Animated Crimson Cosmic Eye Sigil SVG
        │   ├── NodeGraph.jsx        # Interactive branching category & project graph
        │   ├── TeamProgressPanel.jsx# 4-Tab CitizenGraph Timeline, Diff & Priority Inbox modal
        │   ├── DefensePanel.jsx     # Thesis Defense Co-Pilot HUD
        │   ├── DatabasePanel.jsx    # SQLite inspector modal
        │   ├── SettingsPanel.jsx    # Allowlisted apps & tasks editor modal
        │   ├── MiniView.jsx         # Compact Ctrl+Alt+N floating window view
        │   ├── PhoneView.jsx        # Mobile 4-tab read-only Tailscale view
        │   └── ...                  # StatusBar, Terminal, Composer, Dossier, ConfirmDialog, etc.
        └── utils/
            └── useSpeech.js         # Web Speech API recognizer + progressive streaming TTS chunker
```

---

## Installation & Quick Start (Windows PowerShell)

### Prerequisites
- **OS:** Windows 10 / 11
- **Python:** 3.11+
- **Node.js:** 20.19+ or 22.12+
- **Browser:** Google Chrome or Microsoft Edge (for Web Speech API voice recognition)
- **AI CLI:** Antigravity CLI (`agy`) authenticated with your Google AI Pro account

### Setup & Launch
```powershell
cd project-nightmare
.\scripts\install.ps1                 # Creates .venv, installs Python & npm deps, builds frontend, initializes backend/.env
.\scripts\start_nightmare.ps1 -Background
```

Open **http://127.0.0.1:8000** in Chrome and enter your laptop PIN (`NIGHTMARE_PIN` in `backend/.env`).

Optional `install.ps1` flags:
- `-Dev`: Installs test dependencies (`pytest`, `playwright`).
- `-Autostart`: Registers Nightmare and the `Ctrl+Alt+N` hotkey helper to launch at Windows sign-in.
- `-Shortcut`: Adds a Desktop shortcut that opens Nightmare in a chromeless app window.

---

## Configuration (`backend/.env`)

Copy `backend/.env.example` to `backend/.env` (automatically handled by `install.ps1`):

| Variable | Description |
|---|---|
| `NIGHTMARE_TOKEN` | Required. Random 64-hex secret session token. |
| `DESKTOP_ROOT` | Root directory for project scanning (defaults to user `Desktop` or `OneDrive\Desktop`). |
| `NIGHTMARE_PIN` | 6-digit PIN for local desktop browser login (leave blank to disable local PIN lock). |
| `NIGHTMARE_PHONE_PIN` | 6-digit PIN for read-only remote phone sessions over Tailscale. |
| `NIGHTMARE_ALLOWED_HOSTS` | Comma-separated `<machine>.<tailnet>.ts.net` hostnames for Tailscale access. |
| `NIGHTMARE_HOTKEY` | Global hotkey for the mini-window toggle (default: `ctrl+alt+n`). |
| `NIGHTMARE_TEAM_EXCEL_PATH` | Local path to the synced CitizenGraph `.xlsx` timeline workbook. |
| `NIGHTMARE_TEAM_GDRIVE_FOLDER_URL` | Shared Google Drive folder URL for timeline sync. |
| `NIGHTMARE_DEVELOPER_PORTFOLIO_URL` | Portfolio URL opened by `"open adrian portfolio"`. |
| `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_APP_PASSWORD` | SMTP credentials for confirmation-gated team reminder emails. |
| `LOG_RETENTION_DAYS` | Days to retain SQLite audit logs and raw turns (default: `90`). |

---

## Phone Access (Tailscale, Strictly Read-Only)

1. Install Tailscale on both your Windows PC and Android phone under the same tailnet, and enable **MagicDNS** + **HTTPS Certificates**.
2. Set `NIGHTMARE_PHONE_PIN` (6+ digits) and `NIGHTMARE_ALLOWED_HOSTS` in `backend/.env`.
3. Run `.\scripts\setup_tailscale.ps1 -Restart` and open the printed `https://<laptop>.<tailnet>.ts.net/` URL on your phone.

All Tailscale requests are enforced read-only (`readonly=True`) at the router and orchestrator layers.

---

## Development & Verification Commands

```powershell
# 1. Run backend unit & integration test suite (fast, excludes Playwright browser launch)
.\.venv\Scripts\python.exe -m pytest backend -q -m "not browser"

# 2. Run full backend test suite including Playwright browser tests
.\.venv\Scripts\python.exe -m pytest backend -q

# 3. Run offline router accuracy & latency replay harness
.\.venv\Scripts\python.exe scripts\replay_router.py

# 4. Run frontend unit tests & production bundle build
cd frontend; npm test
cd frontend; npm run build

# 5. Rebuild frontend dist and restart Nightmare server
.\scripts\start_nightmare.ps1 -Rebuild
```
