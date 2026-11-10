# Project Nightmare: session handoff (handoff.md = newsession.md)

Last updated: 2026-11-10 (Asia/Manila). Keep both files identical after every milestone. **UNVERIFIED** = not yet tested live by the user.

## 0. Quick status (read by Nightmare's own `progress` command)

- **Done:**
  - **Centered eye, contextual connections, and lyric captions:** Home shows the full-size eye centered in the workspace, with the permanent category strip and adjacent list removed. Relevant replies reveal only the requested category with curved connections directly from the eye to visible project/app/reminder/task items; the eye slides sideways without changing size. Unrelated replies, Home, Hide connections, and standby clear the web; navigation can explicitly browse a category. Filters, scroll-aware endpoints, selections, and existing item actions remain. Caption text has no background and replaces one short phrase/sentence at a time, showing the current line ahead of its audio. Speech boundaries and sentence offsets drive captions; missing boundaries use a capped word-paced fallback, and muted/failed speech uses a reading timer. Stop holds the current line; timestamps prevent an older identical reply from controlling a new muted reply. History opens the entire conversation immediately in a separate native dialog with scrolling, focus containment/restoration, Escape/backdrop/close controls, and read-aloud actions. Eye movement, connection drawing, captions, and window entrances/exits animate smoothly and respect reduced motion. The existing list_projects regex now also recognizes the requested singular phrase "how many project i have". **UNVERIFIED live**: physical voice timing and audio on the user's selected browser voice; checks used simulated speech.
  - **Main desktop dashboard redesign:** Bottom-docked multiline composer with Enter/Shift+Enter, slash suggestions, microphone pointer capture/cancellation, preserved drafts while busy, and adjacent Meeting/Voice controls. The current centered-eye layout, contextual item connections, lyric captions, and separate History window are described above. Quieter header with labeled Tools menu, recent allowlisted apps, and scrollable Today rail (drawer on smaller windows). Removed the four gold cardinal blades, starbursts, and axial strokes from canvas and shared SVG eye variants; retained pupil, iris, rings, runes, orbits, moons, and background artwork. Notes display creation dates; upcoming events sort chronologically; priority badges require actual data and fabricated project completion bars were removed. Permanent L5, click confirmations, and remote read-only restrictions remain. No dependencies added. **UNVERIFIED live**: physical microphone/audio, real agy responses, and the user's running desktop window after refresh; Chrome checks used an isolated fake backend.
  - **Free browser voice selection and Mandarin meeting captions:** Desktop HUD Voice/Meeting buttons and `/voice`, `/meeting`, `/transcribe`. Persisted voice URI, natural pitch, preference for available natural/online or Google voices, preview and speed controls. Separate Mandarin interim/final captions support microphone, PC/tab audio (desktop Chrome 135+ with Share audio), or mixed PC+mic through Web Audio; cleanup on stop, sharing end, permission errors, close, and pending-picker cancellation. English translations queue through a dedicated authenticated text-only `/api/meeting/translate` endpoint and the shared agy lock, bypassing action routing and conversation memory. Remote read-only calls are rejected; transcript credentials/paths are scrubbed and tags escaped inside `<handoff>`. Export timestamped Chinese/English text before closing; stop/export/clear at 2,000 rows. Meeting mode suspends command recognition, spoken notifications, and idle sleep. No dependencies or paid speech API added. **UNVERIFIED live**: actual Mandarin recognition quality, microphone/PC audio, voice quality, and real agy translation latency; English can lag behind speech.
  - **Single-Tier Level 5 (Architect) Clearance Cleanup:** Eliminated the legacy 3-tier clearance hierarchy (Level 1 Observer, Level 3 Operator, Level 5 Architect), PIN/password elevation prompts, and inactivity decay timers. Local desktop sessions run permanently at **Level 5 (Architect)** (`LEVEL_5 = 5`). High-impact system commands (reboot, shutdown, rebuild, SMTP email) remain gated by mandatory physical UI click confirmations (`needs_confirm=True`), and remote Tailscale access remains strictly read-only (`readonly=True`).
  - **Backend Router Modularization (`backend/routers/`):** Decomposed monolithic `backend/main.py` (1,085 lines down to 210 lines) into modular APIRouter packages: `deps.py` (shared context, Pydantic models, auth guards), `auth.py`, `chat.py`, `system.py`, `telemetry.py`, `defense.py`, `team_tracker.py`, `router_review.py`, `database.py`, and `settings.py`.
  - **Frontend UI Clearance Cleanup:** Deleted `ClearanceModal.jsx` and `ClearanceTransition.jsx`. Cleaned `App.jsx`, `StatusBar.jsx`, `Orb.jsx`, `Background.jsx`, `MiniView.jsx`, `PhoneView.jsx`, and `slashCommands.js` of all L1/L3 badges, decay timers, and elevation modals. Unified desktop layout directly around `Level5View.jsx` with permanent `data-clearance="5"`.
  - **Documentation & Agent Guidelines Overhaul:** Recreated `README.md` with complete single-tier architecture diagrams, feature breakdowns, and developer instructions. Created `AGENTS.md` at root specifying mandatory agent rules, invariants, and directory mappings.
  - **Previous Milestones:** Phases 1–6, 7A (speed), 7C (memory), 7D (workspace awareness), 8B (file navigator/git), 8C (PowerPoint/system authority), 8D & 8D-2 (timeline sync/diff/4-tab CitizenGraph telemetry), Developer Persona, 8F (Thesis Defense Co-Pilot), 9A (Hardware Telemetry), Crimson Cosmic Eye Sigil Redesign (`Orb.jsx`), Level 5 Architect Infernal Command Center UI (`Level5View.jsx`), Neon Nightmare Thesis Timeline Dashboard (`TeamProgressPanel.jsx`), Unified Engineering Plan Phases 1–4 (Stopwatch bug fix, strict directory pruning, dedicated `turns` SQLite telemetry schema, persistent PowerPoint COM worker `<15 ms`, native Win32 `kernel32` hardware telemetry `<0.2 ms`, Stale-while-revalidate GitHub check & weather prefetcher, 4-layer router with context buffer & phonetic search, Instant `<100 ms` working indicator, voice conciseness cap ~50–60 words, FastEmbed semantic response cache `<25 ms`, First-Sentence progressive streaming TTS, 54-item offline thesis defense bank).
- **Verification:**
  - Backend pytest (2026-11-10): **407 passed, 1 skipped, 4 failed** (`pytest backend -q -m "not browser"`). Same four existing failures: weather telemetry reaches an unavailable service; warm-snapshot and process-cache latency thresholds fail; tasklist returns no processes. Singular/plural project-count regression cases pass. The only backend runtime change for this UI milestone is the narrow singular project-count matcher.
  - Offline router replay benchmark (2026-11-10, contextual-eye milestone): **405 turns tested, 358 fast-path matches (88.4%), 47 fallbacks (11.6%), 4.67 ms average, 0.30 ms median, 16.58 ms p95** (`scripts/replay_router.py`). This run meets the <5 ms average target; historical slower runs remain environment-dependent.
  - Frontend unit tests: **19 passed, 0 failed** (`npm.cmd test --prefix frontend`), including phrase segmentation with exact speech offsets, word boundaries, punctuation/Unicode, and missing-boundary helpers.
  - Frontend production build: **Vite production bundle built successfully**, existing >500 kB chunk-size warning (`npm.cmd run build --prefix frontend`). Use npm.cmd because PowerShell blocks npm.ps1 here.
  - Targeted Chrome browser checks (2026-11-10): **10 passed**, 8 deselected (`pytest backend/tests/test_dashboard_browser.py backend/tests/test_browser.py -q -m browser -k "dashboard or remote_session or free_voice_panel"`). Covers 1920x1080 / 1366x768 / 1024x720, centered idle eye, no permanent category panel, contextual project/app connections, stable eye diameter and workspace height with captions, filtering/selection, full History dialog, focus containment and Escape restoration, per-sentence replacement, stale callbacks, cancelled speech, unavailable/muted voices (including repeated identical replies), reduced motion, multiline/slash input, simulated mic cancellation, drafts while busy, click-only approvals, read-only restrictions, long lists, Today data, and Voice/Meeting isolation. Current previews: `scratch/ui-redesign/eye-home-1366.png`, `dashboard-1366.png`, `lyric-response-1366.png`, and `conversation-window.png`. Real audio/providers were not exercised.
- **Architectural Constraints (Active & Invariant):**
  - **Single-Tier Clearance:** Desktop operator always has Level 5 (Architect) clearance. No Level 1/3 tiers, no elevation PIN modals, no auto-decay timers.
  - **Mandatory Click Gate:** PC reboot, shutdown, rebuild, dev tasks with `confirm=True`, and outbound SMTP email notifications enforce `needs_confirm=True` requiring explicit UI click approval.
  - **Remote Tailscale Read-Only:** Requests over Tailscale (`PinAccess.role == "readonly"`) are strictly read-only.
  - **LLM Isolation:** `agy` headless CLI never chooses actions, never executes shell commands, and never receives filesystem paths.
  - **No `shell=True`:** Subprocesses use discrete argument lists; allowlisted apps strictly validated.
  - **Phase 7B Dropped:** Zero extra local LLM/SLM dependencies (protecting the 16 GB laptop RAM).
- **Verification gaps:** Four existing backend weather/telemetry failures remain. **UNVERIFIED live**: redesigned desktop with physical microphone/audio and real agy; meeting audio quality and provider latency still require a live desktop check. Refresh the running UI to load the built assets; the additional singular project-count phrase requires the running backend to reload the updated router.

## 1. Start of a session

- Read this file first; follow Section 8 (Security) and Section 9 (Roadmap/Rules).
- Update this file and `newsession.md` synchronously after completing any milestone. Keep both identical.
- Never claim something works without running it on this machine; label untested live features **UNVERIFIED**.

## 2. User constraints

- **Hardware & OS:** Windows 11, Python 3.12 (venv `.venv`), Node.js v22.12.0, PowerShell. Laptop: AMD Ryzen 5 7520U (4 cores, 8 threads), 16 GB RAM, integrated graphics (no NVIDIA GPU), ~145 GB free disk.
- **User:** Adrian, graduating CS student in Calbayog. Localhost only, single user.
- **Interface:** Desktop Chrome Web Speech; remote phone via Android Chrome over Tailscale serve (token/cookie auth, strictly read-only).
- **AI CLI:** Google AI Pro accessed via headless Antigravity CLI (`agy`), zero separate API billing.
- **Remote / Phone Guard (Read-Only):**
  - *Allowed:* progress, cross_project, list projects, read_doc, git status, weather, reminders/notes, chat, status, usage, workspace briefing/changes/priorities, search_projects, conversation_history, clearance status, developer_info/why/skills/projects, system_telemetry, system_battery, system_processes, defense_question, defense_status, defense_stop, priority email report, timeline diff check.
  - *Blocked:* opening apps/folders, running tasks/commands/dev tasks, approvals/confirmations, settings mutations, defense rehearsal start, sending emails.

## 3. Decisions vs the original doc

- Single-Tier Level 5 Architect clearance replaces legacy 3-tier hierarchy.
- Monolithic `main.py` decomposed into modular `backend/routers/` APIRouter modules.
- Claude API fallback dropped (no cost).
- No MCP at runtime (plain Python tools).
- Regex router + ONNX embeddings decide actions; LLM never does (latency + prompt-injection safety).
- Gemini CLI replaced by `agy` (Gemini CLI stopped serving AI Pro 2026-06-18).
- Phase 7B Local LLM/SLM dropped in favor of `agy` + FastEmbed ONNX to protect laptop RAM.
- Zero external pip dependencies used for Office parsing (`zipfile` + `xml.etree.ElementTree` for .pptx slide parsing and .xlsx OpenXML timeline parsing, PowerShell COM fallback) and hardware telemetry (`ctypes.windll.kernel32`).

## 4. agy facts

- **Headless invocation:** `agy -p "<prompt>" --model <id> --disable-slash-commands --output-format json|text`.
- **Sandbox safety:** Print mode auto-approves tool calls -> run from empty scratch folder, tell it to use no tools, scrub API-key env vars, pass text only inside `<handoff>` tags (never paths or shell access).
- **Models:** Fast `gemini-3.8-flash-low` (summaries/chat), smart `gemini-3.8-flash-high` (cross-project, "think deeply"). `agy models` lists IDs; effort is part of the ID. Gemini 4 Argon unused.

## 5. Request flow

```
Browser / Phone (Android Chrome via Tailscale serve)
  │
  ▼
FastAPI 127.0.0.1:<port> (backend/main.py -> backend/routers/*)
  ├── Security Guard: Localhost/Tailscale token auth, Origin check, remote read-only enforcer
  ├── Single-Tier Clearance: Desktop sessions run at Level 5 (Architect); remote runs read-only
  │
  ▼
Orchestrator.handle -> router.route (Pre-Normalize -> Ordinal/Pronoun Context -> Regex -> FastEmbed Semantic -> Closed LLM Classifier)
  ├── Instant Fast-Path (<50ms, plain Python / native Windows C):
  │     Clearance (status reports Level 5 Architect)
  │     Developer Persona (who is developer, why developed, skills, projects, open portfolio link)
  │     Hardware Cockpit (<20ms, ctypes.windll.kernel32: CPU load %, RAM GB/%, battery, top processes)
  │     Thesis Defense (start rehearsal, stop rehearsal, ask mock question, check pacing)
  │     PowerPoint & System (exact slide jump, next/prev slide, restart PC / Nightmare [click confirm])
  │     Timeline & GDrive (CitizenGraph 4-tab rollup, SQLite baseline diff, SMTP nudge [click confirm])
  │     Workspace & Navigation (file navigator, git status, briefings, notes/reminders, weather)
  │     Project Knowledge (FastEmbed RAG search, 3.0s timeout guard, strict directory pruning)
  │     Context Buffer (<5ms ordinal follow-up resolution, pronoun dereferencing)
  │     FastEmbed Semantic Cache (<25ms SQLite cosine-matched general chat query hits)
  └── LLM Fallback (agy headless): Conversational chat & structured read-only tags
        Instant <100ms working status SSE emission to HUD
        Enforced voice conciseness cap (~50-60 words / 2-3 sentences)
  │
  ▼
Persistence & Delivery
  ├── Audit Logger: SQLite (turns [telemetry & repeat detection], actions, llm_calls, defense_sessions, timeline_state, memories, router_miss_queue, custom_exemplars, semantic_cache, defense_qa_bank)
  └── UI Event + Audio TTS: Spoken reply + dynamic badges + GSAP UI transitions + First-Sentence Streaming TTS
```

## 6. Previous feature notes (historical; see current verification above)

- **Single-Tier Clearance & Modular Backend Architecture:**
  - All desktop operations execute at Level 5 Architect clearance without PIN elevation hurdles or decay timers.
  - API routes cleanly segregated into `backend/routers/` (`deps.py`, `auth.py`, `chat.py`, `system.py`, `telemetry.py`, `defense.py`, `team_tracker.py`, `router_review.py`, `database.py`, `settings.py`).
  - Frontend cleaned of legacy L1/L3 components, modals, and split view, directly rendering `Level5View.jsx`.
  - Resolved UI runtime `ReferenceError: onLockdown is not defined` & `onOpenClearance` by binding window close control `✕` to `/sleep` standby and sidebar shield button to `/clearance` status.
- **Latency Reduction & Offline Defense Resilience:**
  - Instant `<100 ms` Working Indicator on HUD with live stopwatch timer.
  - Strict voice conciseness cap (`~50–60 words` / 2–3 sentences) in `AgyProvider`.
  - FastEmbed Semantic Response Cache in SQLite (`<25 ms` cosine-similarity $\ge 0.92$).
  - First-Sentence Streaming TTS progressive sentence chunker in `useSpeech.js`.
  - Pre-Computed Offline CitizenGraph Defense Bank in SQLite (54 items, `<30 ms` offline retrieval).
- **4-Layer Router Upgrade:**
  - Layer 1: Pre-Router Normalizer & Expanded Regex Rules (`router.py`).
  - Layer 2: Stateful `ConversationContext` Buffer (`context_buffer.py`).
  - Layer 3: Hybrid Trigram/Phonetic File Search (`file_navigator.py`).
  - Layer 4: Margin-Gated Semantic Clarification & `/review` Queue (`semantic_router.py`).
- **Fast-Path Tool Bottleneck Acceleration:**
  - Persistent PowerPoint COM worker (`<15 ms`, auto-slideshow launch).
  - Native hardware telemetry (`<0.2 ms`, Win32 `kernel32` CPU/RAM delta).
  - Stale-while-revalidate GitHub check (`<0.1 ms` cache hit) & weather prefetcher.
- **CitizenGraph 4-Tab Telemetry, GDrive Diff & Neon Nightmare Thesis Timeline Dashboard:**
  - 4-tab OpenXML parser (`CitizenGraph_Thesis_Timeline_2026_2027-v2.xlsx`), SQLite baseline diffs, GDrive sync.
  - Desktop Command Center (`TeamProgressPanel.jsx`), Priority Inbox SSE toast notifications, and confirmation-gated SMTP nudger.

## 7. Code map

- `scripts/`: `start_nightmare.ps1`, `setup_tailscale.ps1`, `install.ps1`, `install_autostart.ps1`, `coldstart.py`, `replay_router.py`.
- `backend/`:
  - `main.py`: Slim FastAPI factory (`create_app`), lifespan background workers, middleware & static mount.
  - `config.py`: Configuration settings parsed from `backend/.env`.
  - `hotkey.py`: Windows global hotkey hook (`Ctrl+Alt+N`) via `ctypes`.
  - `routers/`: Modular FastAPI route handlers (`deps.py`, `auth.py`, `chat.py`, `system.py`, `telemetry.py`, `defense.py`, `team_tracker.py`, `router_review.py`, `database.py`, `settings.py`).
  - `core/`:
    - `router.py`: Deterministic regex intent router and pre-router normalizer.
    - `context_buffer.py`: Stateful 120s TTL context buffer for ordinal and pronoun resolution.
    - `semantic_router.py`: FastEmbed ONNX classifier and margin-gated clarification.
    - `clearance.py`: Single-tier Level 5 Architect `ClearanceManager` and intent registry.
    - `orchestrator.py`: Central dispatch, semantic cache, SSE status emitter, and turn telemetry logger.
    - `actions.py`: Action registry, pending execution store (`PendingStore`), and click-confirmed power commands.
    - `apps_config.py`: Atomic `apps.json` persistence and rotating backups.
    - `memory.py`: Conversation turn logging, memory condensation, and relevance recall.
    - `llm.py`: Sandboxed `AgyProvider` (`agy -p`) with voice conciseness constraint.
  - `tools/`:
    - `system_telemetry.py`: Native `ctypes.windll.kernel32` hardware metrics and daemon process worker.
    - `defense_copilot.py` & `defense_qa_data.py`: Defense stopwatch, slide pacing, and 54-item offline Q&A bank.
    - `ppt_controller.py` & `ppt_worker.ps1`: OpenXML slide parser and persistent PowerShell COM worker.
    - `team_tracker.py`: 4-tab CitizenGraph OpenXML parser and SQLite baseline diff engine.
    - `email_notifier.py`: IMAP priority email sync and confirmation-gated SMTP notifier.
    - `file_navigator.py`: Safe path-traversal defended filesystem indexer with hybrid trigram similarity.
    - `audit.py`: SQLite manager (`nightmare.db`).
    - `workspace.py`, `rag.py`, `fs_reader.py`, `weather.py`: Git scanner, local ONNX RAG retriever, safe markdown reader, and cached weather fetcher.
  - `tests/`: Latest non-browser run: 407 passed, 1 skipped, 4 known weather/telemetry failures. Dashboard Chrome checks are in `test_dashboard_browser.py`.
- `frontend/src/`:
  - Desktop dashboard components: `DashboardComposer.jsx` (bottom multiline input), `FloatingResponse.jsx` (one speech-synchronized phrase at a time), `WorkspaceStage.jsx` (centered eye and contextual curved connections), and `ConversationWindow.jsx` (native full-history dialog), composed by `Level5View.jsx`. `useSpeech.js` exposes timestamped speech progress and sentence bounds; `utils/speechProgress.js` supplies word/phrase offsets. Legacy `Composer.jsx` and `NodeGraph.jsx` remain available for other layouts.
  - `App.jsx`, `api.js`: Root state coordinator, SSE turn status listener, and API client.
  - `components/`: `Level5View.jsx` (unified desktop HUD), `Orb.jsx` (Crimson Cosmic Eye Sigil), `NodeGraph.jsx`, `TeamProgressPanel.jsx`, `DefensePanel.jsx`, `DatabasePanel.jsx`, `SettingsPanel.jsx`, `StatusBar.jsx`, `Terminal.jsx`, `Composer.jsx`, `Dossier.jsx`, `ConfirmDialog.jsx`, `MiniView.jsx`, `PhoneView.jsx`.
  - `utils/`: `useSpeech.js` (First-sentence progressive TTS chunking & queueing), `useMic.js`.

## 8. Security (keep)

- **Single-Tier Level 5 Clearance:** Project Nightmare is a single-user system running at Level 5 (Architect). No multi-tier elevation hurdles or decay timers.
- **Mandatory Click Confirmation Gate:** High-impact and destructive actions (PC reboot, shutdown, Nightmare restart, dev tasks, SMTP emails) strictly require `needs_confirm=True` and a physical UI click approval (`POST /api/confirm`).
- **Remote Tailscale Read-Only Enforcement:** Remote sessions over Tailscale (`PinAccess.role == "readonly"`) are strictly read-only and blocked from executing actions or mutating state.
- **LLM Isolation:** The LLM never selects actions, never executes shell commands, and never receives file paths. External data passed to the model is sanitized inside closed `<handoff>` tags and executed from an isolated scratch directory.
- **Filesystem Boundaries:** All file navigation and reading operations resolve symlinks, block sensitive patterns (`.env`, passwords, keys, tokens), and verify paths strictly reside within user roots (`Desktop`, `Documents`, `Downloads`).
- **No `shell=True`:** Subprocesses execute discrete argument arrays without shell expansion.
- **Network & Auth:** Localhost binding (`127.0.0.1`), verified `Host` and `Origin` headers, and token/PIN session management.

## 9. Roadmap and rules

- **Phase 1–9 Milestones:** Done (**UNVERIFIED live** where noted).
- **Codebase Clean-Up (Single-Tier Level 5, Modular Routers, Frontend HUD, Docs, AGENTS.md):** Done.
- **Desktop dashboard redesign:** Built and checked in Chrome at desktop and laptop sizes; remaining live checks and unrelated baseline failures are listed above.
- **Rules:** Keep LLM out of action path; update both handoff files synchronously after work; backend stays on 127.0.0.1; never claim something works unless run on this machine; label UNVERIFIED.

## 10. Commands (PowerShell, project root)

```powershell
# 1. Fast backend unit & integration tests (407 passed, 1 skipped, 4 known failures)
.\.venv\Scripts\python.exe -m pytest backend -q -m "not browser"

# 2. Offline router replay benchmark (405 turns, 88.4% fast-path; 4.67 ms average)
.\.venv\Scripts\python.exe scripts\replay_router.py

# 3. Frontend unit tests & production build (19 passed; build succeeds with bundle-size warning)
npm test --prefix frontend
npm run build --prefix frontend

# 4. Rebuild frontend dist and restart Nightmare server
.\scripts\start_nightmare.ps1 -Rebuild
```
