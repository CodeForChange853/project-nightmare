# Project Nightmare: session handoff (handoff.md / newsession.md)

Last updated: 2026-10-20 (Asia/Manila).
Both `handoff.md` and `newsession.md` are kept in sync so that a new coding session—or Nightmare's own `"progress of project nightmare"` command—always has full context. Items marked **UNVERIFIED** have not yet been tested live by the user.

## 0. Quick Status Summary (for Nightmare's `progress` reader)

- **Done recently:** Completed **Phase 1**, **Phase 1.5**, **Phase 2**, **Phase 3 (More tools + 3-Tier Speed & Model Routing + Calbayog Weather + `nightmare_helper.txt`)**, **Phase 4 (Android phone over Tailscale, live on the user's phone)** and **Phase 6 (Polish)**. Phase 5 (local voice) is the only phase left.
  - **3-Tier Speed & Model Architecture:**
    - **Tier 0 (Instant Python, `<10ms`, 0 LLM calls):** Added `quick_reply` intent for greetings, time/date, and capabilities/help, alongside instant deterministic tools (weather, git status, reminders, project list, short `<=400` char `.md`/`.txt` files, cached handoff summaries).
    - **Tier 1 (Fast Model, `AGY_FAST_MODEL=gemini-3.8-flash-low`, ~8s):** Used with `--disable-slash-commands` for single-file summaries (`progress`, `read_doc`) and normal conversational questions.
    - **Tier 2 (Smart Model, `AGY_SMART_MODEL=gemini-4-argon-medium`, ~12–15s):** Used for cross-project comparisons (`"which project needs attention?"`) or when the user says `"think deeply"` / `"use smart model"`.
  - **Calbayog Live Weather Fix:**
    - Upgraded `backend/tools/weather.py` to use **Open-Meteo** (geocoding + forecast API, <300ms, no API key required) as primary with `wttr.in` fallback, and set the default `WEATHER_CITY` to **`Calbayog`**.
    - Widened weather router patterns (`"check a weather here in calbayog"`, `"Calbayog weather"`, `"how hot is it in ..."`).
    - Updated `scripts/start_nightmare.ps1` to automatically stop any stale background Python server on `NIGHTMARE_PORT` before starting the updated backend.
  - **Command Reference:** Created `nightmare_helper.txt` in the project root with all current voice/text commands and their purposes.
  - **Voice Gender (Male/Female), Speed Controls & Full Read-Aloud:**
    - Upgraded `frontend/src/utils/useSpeech.js` (`useSpeaker`) to support **Male / Female voice selection** (`voiceGender`: `'male'` | `'female'`), **reading speed presets** (`0.9x`, `1x`, `1.15x`, `1.3x`, `1.5x`), and **full-text sentence-by-sentence chunking** so Chrome's `speechSynthesis` reads the entire generated output aloud (e.g., `"can you tell me about the latest progress of bims?"`) without cutting off after 600 chars or 15 seconds.
    - Added controls in `Composer.jsx`, `StatusBar.jsx`, and `Terminal.jsx` (`Male`/`Female` button, speed cycle button, `Stop` button while speaking, per-message `Read aloud` button) plus voice commands (`"switch to male/female voice"`, `"speak faster/slower"`, `"normal speed"`).
  - **Crimson UI redesign (frontend only, 2026-10-20):** dashboard layout modelled on a node-graph reference: a canvas "blood moon" eye (`Orb.jsx`) whose waveform ring and slit pupil show the mode (idle / listening / thinking / speaking / confirm / offline) and doubles as the hold-to-talk button; curved SVG lines to category nodes (Projects, Reminders, Apps, Tasks, Quick asks) that fan out into a scrollable arc of items (`NodeGraph.jsx`); glass side panel with Details (selected item + actions, model response time with per-session dot chart, usage tiles) and Conversation tabs; boot loader tied to the first `/status` call; redesigned lock screen and confirm dialog (countdown ring). GSAP plugins used: DrawSVG, ScrambleText. Fonts: Big Shoulders Display + Hanken Grotesk (Geist Mono only for commands). Read-only sessions hide open/run actions. Phone width collapses to one column. **Arc scrolling fix:** the arc keeps its scroll position across status refreshes and resizes (it resets only when you switch category), and supports wheel, drag, a scroll rail with up/down buttons, and arrow/Page/Home/End keys, with even row spacing and a "1–17 of 24" counter.
  - **Reminders, database viewer, websites (2026-10-20):** casual reminder phrasing ("remind me later that ...", "remind me later for ...") is saved and counted; "do I have any reminder today" lists them with when they were added; "delete the class reminder" / "delete reminder 3" removes the SQLite row (fuzzy match on the description, asks which number if several match, refuses "delete all"); the add/delete audit entries no longer keep the reminder text. "database access open" opens a PIN-gated viewer (`DatabasePanel.jsx`, `/db/open` -> 10-minute token in React state only, `/db/records`, `/db/notes/{id}/delete`, `/db/close`; rate-limited; blocked for read-only sessions); "database close" or Esc closes it. Websites ("open youtube in this browser", "open youtube and search lofi", "google x", "open github.com") return a fixed-template https URL that the frontend opens as a new tab with `window.open` (falls back to a link if the popup blocker stops it); no program is launched. The chat prompt now forbids the model from claiming it saved a reminder.
  - **Models, memory, slash commands, log retention (2026-10-20):** models are now `AGY_FAST_MODEL=gemini-3.8-flash-low` (summaries, chat) and `AGY_SMART_MODEL=gemini-3.8-flash-high` (cross-project, "think deeply"); Gemini 4 Argon is not used (`agy models` lists the IDs; effort is part of the ID). Chat now sees the last 6 exchanges of the current login (in memory only, `<history>` data block, 400 chars per message), forgotten after 30 idle minutes, on backend restart, or on "new session" / `/clear` / `/new` (`POST /session/reset`). Typed slash commands with suggestions: `/help` (searchable `HelpPanel.jsx` parsed from `nightmare_helper.txt` via `GET /help`, click a quoted command to run it), `/clear`, `/new`, `/reminders`, `/db`. Activity-log rows older than `LOG_RETENTION_DAYS` (default 90) are pruned at startup; reminders and model-call counts are kept. Weather, reminders, websites and the database viewer make no model calls (tested).
  - **Graph highlights, sleep/wake, count fix (2026-10-20):** every `/chat` reply carries `focus: {node, item}` (`NODE_FOR_INTENT` in `orchestrator.py`; the project comes from a per-request `ContextVar`, so overlapping requests cannot mix it up). After the status refresh, the UI switches to that node, flashes its count, runs a spark (GSAP MotionPath) eye -> node -> item, scrolls the arc to the item and selects it. Sleep: 5 idle minutes (no clicks/keys/replies, not while busy/speaking/dialog open), "go to sleep" or `/sleep` folds the web away, centres the eye and closes its lids (`Orb` mode `sleep`); "Nightmare, wake up" answers with a fixed greeting and unfolds the graph, both handled in the browser with no model call; any other command also wakes it. Fixed stale node counts: the intro count-up wrote `textContent` over React-managed text, so later count changes did not show; now `CountUp.jsx` owns its text. Global `:focus-visible` moved into `@layer base` so utilities can override it.
  - **Project "about" from README (2026-10-20):** new `about` intent ("what is citizengraph all about", "tell me about bims", "what does X do", "describe X"); "tell me about X" now means about, not progress. `_do_about` reads the project's top-level README.md/readme.txt only (a nested frontend/README.md is usually framework boilerplate), falls back to handoff.md, and summarizes with the fast model inside `<document>` tags (`ABOUT_PROMPT`, cached by mtime under an `about:` key). Progress on a project with no handoff.md now answers from git (branch, uncommitted files, last commit) and points to the README. "what is next for X" / "next task" routes to progress. Project cards carry `has_readme`; the Details panel shows a "What it's about" button. LLM classifier gained `INTENT:about`. UNVERIFIED: real agy summaries of the README.
  - **Phase 4: Android phone over Tailscale (2026-10-20, code done; live phone test UNVERIFIED):**
    - Backend (`backend/main.py`, `config.py`): new `NIGHTMARE_ALLOWED_HOSTS` (the laptop's `*.ts.net` name; pasted URLs, ports and trailing dots are tolerated). A request is **remote** when its Host is one of those names or it carries `X-Forwarded-For/Host/Proto` or `Tailscale-User-Login` (tailscale serve adds them; browsers and the Vite proxy do not). Remote requests are refused (403 "Remote access is off") until the host is configured; an `X-Forwarded-Host` that is not allowed gets 403; the only remote Origin accepted is `https://<allowed host>` (plain `http://` same-host origin is now laptop-only). **Remote = always read-only**: the laptop PIN, the API token, or a full session cookie all become `readonly` through the proxy, so the database viewer, `/confirm` and actions are blocked. Login/db-PIN rate limit is keyed per phone (`remote:<last X-Forwarded-For entry>`, so a client-supplied prefix cannot dodge it, and phone failures do not lock out the laptop). The session cookie is `Secure` for remote logins. `/status` reports `remote`.
    - `scripts/setup_tailscale.ps1`: checks Tailscale is installed and connected, reads the MagicDNS name from `tailscale status --json`, refuses if `NIGHTMARE_PHONE_PIN` is empty (warns if < 6 digits), runs `tailscale serve --bg --https=443 http://127.0.0.1:<port>` (tailnet only, **never Funnel**), writes `NIGHTMARE_ALLOWED_HOSTS` into `backend/.env` (UTF-8 without BOM, replaces the line in place), prints the phone URL. `-Restart` restarts the backend in the background, `-Status` shows the serve config, `-Off` stops serving and clears the host.
    - Frontend: `frontend/public/manifest.webmanifest` + `icon.svg` (Add to Home screen, standalone, dark theme colour), served by FastAPI from an allowlist (`ROOT_FILES`; nothing else at the dist root is served). Read-only sessions get no Apps/Tasks nodes and no "Open the database" quick ask (`applyFocus` ignores nodes that are not shown). Touch devices (`pointer: coarse`) get "Hold the eye" hints instead of "Hold Space". Below the `lg` breakpoint the phone item list is capped at 45dvh and scrolls on its own; tapping an item scrolls the Details panel into view, and a reply switches to Conversation and scrolls there (focus highlights scroll only the list, never the page).
    - Verified here: 150 tests pass; against a live backend on a spare port, proxied requests (Host + X-Forwarded-*) logged in as read-only with the laptop PIN, got `Secure` cookies, weather answered, `open notepad`/`/confirm`/`/db/open` refused, foreign Origin / other ts.net host / Origin over http got 403; phone-width layout (412 px) checked in Chrome, including tap -> Details and Git status -> Conversation; desktop arc renders with 3 nodes. **UNVERIFIED:** Tailscale itself (not installed on the laptop yet), real Android Chrome speech/TTS over HTTPS, Add to Home screen, whether tailscale serve keeps the Host header (both cases are handled).
    - **Live (2026-10-20, ~17:26):** Tailscale 1.104.1 on the laptop (`garcia2024.tail39da4a.ts.net`, serve -> `127.0.0.1:8010`), phone "Ehhtooo" (Android) on the tailnet, phone logins recorded as `remote:100.88.18.84 (readonly)`. First "webpage not available" was the phone not being on the tailnet yet. Phone sessions show only Projects / Reminders / Quick asks (Apps and Tasks are hidden in read-only sessions on purpose).
  - **Android voice repetition fix (2026-10-20):** Android Chrome's continuous recognition returns every growing guess as its own result ("how", "how many", ...), and `useSpeech.js` joined them all, so the phone sent "how how many how many ... projects". New `frontend/src/utils/transcript.js` (`mergeTranscripts`) treats a result that repeats the previous piece (last word may be re-guessed) as a revision; desktop's consecutive pieces still join. Tested with the exact logged inputs (`npm test`). **UNVERIFIED on the phone after the fix.**
  - **Phase 6: Polish (2026-10-20):**
    - **Git:** the project is now a git repo (`main`), one commit per step. `.env`, `*.db`, `apps.json`, logs, backups are ignored. Stray `backend/app.json` (identical copy of apps.json, unused) deleted.
    - **Packaging:** `scripts/install.ps1` (venv, pinned packages, `npm ci` + build, `backend/.env` from the example with a generated token and PIN prompts, `apps.json` from the example, `frontend/.env.local`, optional `-Autostart`, `-Shortcut` Chrome `--app` window, `-Dev`, `-NoPrompt`; re-runnable, never overwrites). Tested on a fresh clone: 68 s, then 150 tests passed there. `requirements.txt` pins exact runtime versions (httpx moved to runtime, weather needs it); `requirements-dev.txt` has pytest + playwright. `.env` helpers shared in `scripts/nightmare_env.ps1`.
    - **Settings (apps.json editor):** "open settings" / "edit my apps and tasks" / `/settings` / sliders button -> typed PIN -> 10-minute token (`X-Settings-Token`, same `PinAccess` gate as the database). `GET/POST /settings/apps`, `POST /settings/apps/check` (dry run: `shutil.which`, command line, folder; never runs). `backend/core/apps_config.py` validates added/changed entries (ids `[a-z0-9-]`, argv list of plain strings without control chars, <= 20 parts, aliases, project must exist, timeout 1-600, flags bool, project_flag like `-d`), drops unknown keys, keeps untouched entries byte for byte. **Rules:** tasks added/changed in Settings always get `confirm: true`; apps whose program is a shell/script host (`SHELLS`: cmd, powershell, pwsh, python, node, wscript, mshta, rundll32, ...) always confirm. Save is atomic (temp + `os.replace`), last 5 backups in `backend/backups/`, 409 if the file changed on disk since loading, hot-reloads `Registry.replace()` and clears `PendingStore` (a waiting confirmation may describe the old entry). Read-only/phone sessions are refused. Voice can only open the panel. `SettingsPanel.jsx`: list + editor (program + one argument per line), Check, unsaved-change summary, Undo all, discard prompt on close.
    - **Activity log viewer:** `GET /db/actions?group=&outcome=&q=&before=` (groups: access / actions / reminders / questions; outcome problems = fail/error/block/limit/cancel; search escapes LIKE wildcards; 100 per page). Database panel Activity tab has the filter bar, a "Phone" tag on `remote:` logins and "Load older".
    - **Space key:** push-to-talk ignores Space inside any `role="dialog"`, so checkboxes and buttons in panels work with the keyboard.
    - **Tests:** `backend/tests/test_settings.py` (20), `backend/tests/test_browser.py` (7 Playwright tests in the installed Chrome against an in-process server: PIN lock/unlock, command reply, click-to-confirm deny/approve, read-only phone PIN, 412 px touch layout, database activity filters, adding an app in Settings then "open paint"). The 6 agy-wrapper tests now run on Windows with a real `.exe` stand-in built by pip's distlib launcher; the detached-launch test runs on Windows too. `frontend/tests/transcript.test.mjs` via `npm test`.
    - **Verified in Chrome** against throwaway servers using scratch copies of apps.json and the database: Settings add-task -> Check -> Save (file, backup, untouched entries kept, "run bims build" asks first without restart); Activity filters on a copy of the real log.
  - Test suite: **185 passed, 1 skipped** on Windows (the skip is the symlink test, which needs Developer Mode); `npm test` 5 passed.
- **What is next:** Reload Nightmare on the phone and check that voice no longer repeats words. Change both PINs to 6+ digits (both are short and easy to guess). Then **Phase 5 (Local voice upgrade)**: faster-whisper / Piper / wake word, or server-side speech-to-text if Android Web Speech is still unreliable.
- **Blockers:** None.

---

## 1. How the next session should start

1. Read this whole file (`handoff.md` / `newsession.md`).
2. Always keep `handoff.md` and `newsession.md` updated after completing each phase or milestone so context is never lost.
3. Follow the rules in section 10: propose changes clearly and keep the LLM out of the action execution path.

## 2. Constraints and decisions the user made

- Localhost only, for one user (graduating CS student in Calbayog), no public cloud hosting.
- **Voice is the primary way the user interacts with Nightmare** (using Google Chrome's Web Speech-to-Text).
- **Phone platform:** Android (Chrome supports Web Speech on HTTPS).
- **No separate API billing.** Use the existing 1-year **Google AI Pro** subscription through the Antigravity CLI (`agy`), not a Gemini API key.
- Wants "safe system-level access" and wants it to **act**: open apps, open folders, run predefined tasks.
- Windows 10/11 (`Windows-10-10.0.26200`), Python 3.11.9, PowerShell, venv at `.venv`.
- **Phone/remote access is read-only (decided 2026-10-20, backend enforcement built in Phase 1.5).** Allowed from the phone: progress of a project, cross-project overview, list projects, document lookup (`read_doc`), git status, weather, reminders/notes, chat, status, usage. Blocked from the phone: opening apps or folders, running tasks or commands, approving confirmations. Enforced in the backend via `NIGHTMARE_PHONE_PIN` creating a `readonly` session role.

## 3. What changed from the user's original doc, and why

| Original doc | What we did | Why |
|---|---|---|
| Claude Opus API fallback on 429 | Dropped | User does not want API costs |
| MCP servers (filesystem, memory, fetch) at runtime | Not used; plain Python tools | MCP is for Claude Desktop/Code; building it twice adds risk |
| LLM router agent outputs a TOOL call | Deterministic regex router + closed-set read-only fallback; LLM never decides actions | Latency (agy is slow) and prompt-injection safety |
| Single LLM model for everything | 3-Tier routing: Instant Python (`<10ms`) -> `gemini-3.8-flash-low` (`~8s`) -> `gemini-4-argon-medium` (`~14s`) | Fast responses for easy questions while keeping deep reasoning for multi-project synthesis |
| GSAP + Framer Motion + Lottie + ScrollSmoother | GSAP core + DrawSVG/ScrambleText plugins (free since 3.13) | Simpler; ScrollSmoother conflicts with an auto-scrolling chat log |
| Gemini CLI | `agy` (Antigravity CLI) | Gemini CLI stopped serving Google AI Pro on 2026-06-18 |

## 4. Research findings about the Google side

- Gemini CLI was retired for Google AI Pro/Ultra and free individual users on **2026-06-18**; **Antigravity CLI (`agy`, written in Go)** replaced it.
- Headless use: `agy -p "<prompt>" --model <model> --disable-slash-commands --output-format json|text`.
- **Verified models on user's machine (`agy models`):**
  - Fast tier: `gemini-3.8-flash-low` (~8s per call in print mode).
  - Smart tier: `gemini-4-argon-medium` (~12–15s per call in print mode).
  - Also listed in `agy models`: `gemini-4-argon-high`, `claude-sonnet-5-5-medium`, `claude-opus-5-5-medium`, etc.
- Print mode **auto-approves every tool call**. Mitigations in code: run `agy` from an empty scratch folder, pass `--disable-slash-commands`, tell it to use no tools, scrub API-key env vars (`GEMINI_API_KEY`, `GOOGLE_API_KEY`, `GOOGLE_CLOUD_PROJECT`, etc.), and give it only text, never paths or a shell.

## 5. Architecture and request flow

```
Single-Server Mode: Browser (Chrome) -> http://127.0.0.1:<port> (serves frontend/dist + /api/*)
Phone (Phase 4):    Android Chrome -> https://<laptop>.<tailnet>.ts.net (tailscale serve, tailnet only)
                    -> http://127.0.0.1:<port> with X-Forwarded-* -> always a read-only session
  Auth: HttpOnly cookie `nightmare_session` (from POST /api/login with NIGHTMARE_PIN or NIGHTMARE_PHONE_PIN)
Dev Mode:           Browser -> Vite dev proxy :5173/api (injects X-Nightmare-Token) -> FastAPI :8000/:8010

FastAPI on 127.0.0.1:<port> -> guard (token or session cookie + local Host + allowed Origin)
  -> Orchestrator.handle(text, readonly=...) -> router.route(last_project=...) (regex, no LLM)
       -> quick_reply:     instant Python (time/date, greetings, capabilities/help)
       -> progress:        fs_reader finds folder + handoff.md -> mtime cache or agy (fast model) summarizes
       -> cross_project:   reads all Desktop handoff.md files -> agy (smart model) summarizes priorities
       -> read_doc:        fs_reader finds safe .md/.txt in project -> verbatim (<=400 chars) or agy (fast model)
       -> git_status:      fast read-only `git status --porcelain --branch` on project
       -> weather:         httpx -> Open-Meteo / wttr.in (default Calbayog) with 10-min cache
       -> notes/reminders: SQLite `notes` table (add_note, list_notes, complete_note)
       -> open app/folder: blocked if readonly; else actions.plan_* -> (confirm if required) -> execute()
       -> run task/cmd:    blocked if readonly; else needs UI click confirmation -> execute()
       -> chat fallback:   logs unrecognized_chat -> agy (fast model, or smart if "think deeply") answers
                           OR emits closed read-only INTENT:... tag
  -> audit log (SQLite) -> reply (with `understood` tag) -> UI log + text-to-speech
```

## 6. Code map

```
project-nightmare/
  README.md  handoff.md  newsession.md  nightmare_helper.txt  .gitignore
  scripts/
    agy_smoke_test.py              # standalone check of agy from Python
    install.ps1                    # one-command setup (-Dev, -Autostart, -Shortcut, -NoPrompt), re-runnable
    nightmare_env.ps1              # shared Get-EnvValue / Set-EnvValue for backend/.env (no BOM)
    start_nightmare.ps1            # stops stale server on port, builds UI if needed & starts single server
    setup_tailscale.ps1            # tailscale serve HTTPS for the phone + NIGHTMARE_ALLOWED_HOSTS (-Status, -Off, -Restart)
    install_autostart.ps1          # registers Windows Task Scheduler "At log on" (pythonw)
    uninstall_autostart.ps1        # removes Task Scheduler task
  backend/
    __main__.py                    # `python -m backend`, binds 127.0.0.1, logs to backend/logs/nightmare.log
    main.py                        # FastAPI: /login /logout /status /chat /confirm /audit /db/* /settings/* + static dist
    config.py                      # Settings.from_env(), reads backend/.env (PORT, PIN, FAST/SMART_MODEL, WEATHER_CITY)
    .env.example  apps.example.json  requirements.txt  requirements-dev.txt
    backups/                       # last 5 apps.json versions saved by Settings (git-ignored)
    core/router.py                 # regex intent router (16 intents) + follow-up pronouns
    core/orchestrator.py           # handlers, 3-tier model dispatch, mtime cache, follow-up memory, readonly guard
    core/actions.py                # Registry (replace() hot-reload), plans, execute(), PendingStore (clear())
    core/apps_config.py            # Settings: validate, describe_changes, atomic save + backups, check_entry, SHELLS
    core/llm.py                    # LLMProvider, AgyProvider (fast_model + smart_model), NoLLMProvider
    tools/fs_reader.py             # project matching, handoff/doc reader, git_info, project_cards
    tools/weather.py               # async weather fetcher (Open-Meteo + wttr.in + OpenWeather) with 10m cache
    tools/audit.py                 # SQLite audit + LLM call counts/latency + notes/reminders + search_actions
    tests/                         # 185 passed, 1 skipped on Windows (test_browser.py needs Playwright + Chrome)
  frontend/
    vite.config.js                 # dev proxy injects X-Nightmare-Token
    public/                        # manifest.webmanifest + icon.svg (copied to dist root, served via ROOT_FILES)
    dist/                          # production bundle served directly by FastAPI
    src/App.jsx  api.js            # builds graph categories from /status, PIN unlock, push-to-talk, confirm flow
    src/components/  Orb NodeGraph Dossier Terminal Composer Boot LockScreen ConfirmDialog StatusBar Background Icon
                     DatabasePanel SettingsPanel HelpPanel CountUp
    src/utils/       useSpeech.js (Google Web Speech recognition + TTS)  transcript.js (Android merge)  useMic.js
    tests/           transcript.test.mjs (npm test, node:test)
```

## 7. Security model (keep these properties)

- The LLM never chooses actions and never gets a path or shell. Handoff and document text are passed as untrusted data inside `<handoff>` / `<document>` tags, with closing tags neutralized.
- `fs_reader` only opens `handoff.md` or safe `.md`/`.txt` documents (blocking `.env`, `*secret*`, `*password*`, `*credential*`, `*token*`, `*.pem`, `*.key`, `id_rsa*`), resolves symlinks, and requires the result to stay inside `DESKTOP_ROOT`.
- Closed-set LLM intent classifier fallback in `_do_chat()` can only dispatch to read-only tools (`progress`, `list_projects`, `cross_project`, `weather`, `read_doc`), validated by Python.
- Token and PINs live only in `backend/.env` (and `frontend/.env.local` for Vite dev); never bundled into browser JS.
- Login endpoint is rate-limited (5 failures per 60s -> HTTP 429) and issues `HttpOnly`, `SameSite=Strict` session cookies.
- Read-only sessions (`NIGHTMARE_PHONE_PIN`) are blocked in the backend from running any action intent or calling `/confirm`.
- Remote (Phase 4): only `tailscale serve` (never Funnel); remote requests need a `NIGHTMARE_ALLOWED_HOSTS` name and an `https://` Origin for it, and are capped to read-only whatever PIN/token/cookie they carry. Remote login cookies are `Secure`; rate limits are per phone.
- Settings (Phase 6): typed PIN + 10-minute token, laptop full sessions only, voice can only open the panel. Every added/changed entry is validated; new/changed tasks and shell/script-host apps always need a click; saves are atomic, backed up, refuse to overwrite a hand edit, and clear waiting confirmations.
- Everything logged to `backend/nightmare.db` and `backend/logs/nightmare.log`.

## 8. Roadmap & Phase Status

- **Phase 1: Make it dependable — COMPLETED (2026-10-20)**
- **Phase 1.5: Run automatically & single server — COMPLETED (2026-10-20)**
- **Phase 2: Smarter understanding & document lookup — COMPLETED (2026-10-20)**
- **Phase 3: More tools & 3-tier speed optimization — COMPLETED (2026-10-20)**
  - Weather (`Open-Meteo` + `wttr.in` zero-key default for `Calbayog`, 10-min cache).
  - 3-tier speed routing: Instant Python (`quick_reply`) + `gemini-3.8-flash-low` (fast) + `gemini-4-argon-medium` (smart).
  - Project cards with last-updated time, cached summary preview, and git branch + dirty count.
  - Reminders/notes in SQLite + UI reminders strip.
  - Usage panel with today/total calls and average LLM latency.
  - Full command reference in `nightmare_helper.txt`.
- **Phase 4: Remote and Android phone — COMPLETED (2026-10-20), live on the user's phone**
  - HTTPS via Tailscale (`tailscale serve`, `scripts/setup_tailscale.ps1`), `NIGHTMARE_ALLOWED_HOSTS` + remote = read-only in `main.py`, phone layout fixes, home-screen manifest. Not done: server-side speech-to-text (moved to Phase 5 if Android Web Speech turns out unreliable).
- **Phase 5: Voice upgrade**
  - Local speech-to-text (faster-whisper) and text-to-speech (Piper); wake word.
- **Phase 6: Polish — COMPLETED (2026-10-20)**
  - git repo, `install.ps1` + pinned requirements, Settings screen for `apps.json`, activity-log filters/search/paging, Playwright browser tests, Windows agy tests, Android transcript fix + `npm test`, README rewrite.

## 9. Commands cheat sheet (PowerShell, from `project-nightmare`)

```powershell
# Restart backend & rebuild UI on http://127.0.0.1:<NIGHTMARE_PORT>:
.\scripts\start_nightmare.ps1 -Rebuild

# Restart in background (kills stale process on port and starts pythonw.exe):
.\scripts\start_nightmare.ps1 -Background

# Register auto-start at Windows log on (Task Scheduler):
.\scripts\install_autostart.ps1

# Phone access over Tailscale (after installing Tailscale + setting NIGHTMARE_PHONE_PIN):
.\scripts\setup_tailscale.ps1 -Restart     # also: -Status, -Off

# Fresh setup or repair (safe to re-run):
.\scripts\install.ps1 -Dev

# Run all tests (expect 185 passed, 1 skipped; includes 7 browser tests in Chrome, ~1 min):
.\.venv\Scripts\python.exe -m pytest backend -q
.\.venv\Scripts\python.exe -m pytest backend -q -m "not browser"   # fast
cd frontend; npm test
```

## 10. Rules for every session

- Always update `handoff.md` and `newsession.md` after completing work so context is preserved for new sessions and for Nightmare's own progress reader.
- Keep the LLM out of the action path. Any new action goes through the `apps.json` allowlist or a validated, read-only tool.
- Keep backend bound to `127.0.0.1`; any remote exposure goes through Tailscale (or similar) plus login, never a bare open port.
- Do not claim anything works that has not been run on the user's machine; label UNVERIFIED items.
