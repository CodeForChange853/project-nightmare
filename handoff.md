# Project Nightmare: session handoff (handoff.md = newsession.md)

Last updated: 2026-10-20 (Asia/Manila). Keep both files identical after every milestone. **UNVERIFIED** = not yet tested live by the user.

## 0. Quick status (read by Nightmare's own `progress` command)

- **Done:** Phases 1, 1.5, 2, 3, 4, 6, plus small window/phone tabs, **Phase 7A** and **Phase 7C (memory)**. Phone over Tailscale works live; the Android repeated-words fix is confirmed by the user.
- **In progress: Phase 7** (speed, memory, workspace awareness, offline). Order: **A -> C -> D -> B**.
  - **7A done (2026-10-20, committed, UNVERIFIED live: needs `start_nightmare.ps1 -Rebuild`):**
    - Instant replies (no model): "what's your name (again)", "who are you"; opening a well-known program that is not in apps.json (Word, PowerPoint, Excel, Outlook, Teams, Discord, Zoom, Steam, ...) answers "X isn't in your allowed apps, add it in Settings" instead of a ~12 s model call.
    - Fuzzy browser-side commands (`App.jsx`): "mayor/major/to/go/2 sleep" -> sleep; "oo/ou/u/you/to mini" -> mini.
    - Timing: every answer logs a `timing` row (`intent | router ms | model ms | total ms`, never the user's words); own group `timing` in the activity filters.
    - Summaries persist in SQLite (`summaries` table, valid only for the file's mtime), so restarts no longer cost a model call. A background refresher (`SUMMARY_REFRESH_SEC`, default 180, 0 = off; `Orchestrator.refresh_summaries_once`, started from FastAPI `lifespan`) pre-summarizes one stale handoff/README per round, skips files edited < 60 s ago and rounds where the model is busy, logs `summary_prewarm`.
  - **A3 skipped (measured):** agy's stream (`--output-format stream-json`, events `step_update` with `step_type: agent_response` + `text_delta`) delivers a whole 120-word answer within ~1.2 s of the first text (first text at 9.7 s, end 10.9 s), so speaking while streaming saves ~1 s only; the wait is startup + thinking.
  - **7C Memory done (2026-10-20, 228 tests incl. browser pass, UNVERIFIED live with real agy):**
    - "remember that X" / "keep in mind that X" saves a **fact** (`facts` table; no model; "remember to X" is still a reminder). "what do you remember" / "what have I told you" lists them; "forget that X" / "forget memory N" removes one at a time (refuses "all", asks if several match). Phone sessions can list but not add/forget (`MEMORY_WRITE_INTENTS`). Max 200 facts. Database panel has a **Memory** tab with Delete (`POST /db/facts/{id}/delete`).
    - Conversations are saved (`conversations` table; not PIN/db/settings/shell/reminder/fact turns), raw rows pruned after `LOG_RETENTION_DAYS` (90) at startup; facts and `day_summaries` stay. The background refresher condenses one past day per round into a <=60-word summary (`_condense_one_day`, logs `day_condense`).
    - Recall (`backend/core/memory.py`, plain Python): chat prompts get a `<memory>` data block with only relevant facts (word overlap; recent facts if the question is personal), older turns (>30 min old) and day summaries; `understood` shows "N memories". Closing tag neutralized.
  - **Next:** D workspace awareness, then B offline.
- **User decisions for Phase 7:** do the recommended options. Do **not** install Ollama; the user has a fine-tuned **Llama 3 8B Instruct** (from the CitizenGraph project) to consider for offline use in B; propose how to use it before installing anything. Phone may read (not change) saved memory. Keep raw conversations 90 days, remembered facts until "forget". Dev tasks found automatically always need a click.
- **Still to confirm on the phone:** the new tab layout and that the keyboard keeps the chat box visible. Change both PINs to 6+ digits.
- **Blockers:** none.

## 1. Start of a session

Read this file; follow section 9 rules; update this file and `newsession.md` after each milestone.

## 2. User constraints

- Localhost only, one user (graduating CS student, Calbayog). Windows 11, Python 3.11.9, PowerShell, venv `.venv`. Laptop: Ryzen 5 7520U, 4 cores, 16 GB RAM, no NVIDIA, ~145 GB free.
- Voice is the main interface (Chrome Web Speech today). Phone is Android Chrome.
- No separate API billing: use Google AI Pro through the Antigravity CLI `agy` (no API key).
- Wants safe system access that acts: open apps/folders, run predefined tasks.
- **Phone/remote = always read-only:** allowed: progress, cross-project, list projects, read_doc, git status, weather, reminders, chat, status, usage. Blocked: opening apps/folders, running tasks/commands, confirmations, database viewer, Settings.

## 3. Decisions vs the original doc

Claude API fallback dropped (no cost). No MCP at runtime (plain Python tools). Regex router decides actions; the LLM never does (latency + prompt-injection safety). Gemini CLI replaced by `agy` (Gemini CLI stopped serving AI Pro 2026-06-18). GSAP core + DrawSVG/ScrambleText only.

## 4. agy facts

- Headless: `agy -p "<prompt>" --model <id> --disable-slash-commands --output-format json|text`. Print mode auto-approves every tool call, so: run from an empty scratch folder, tell it to use no tools, scrub API-key env vars, give it only text (never paths or shell).
- Models: fast `gemini-3.8-flash-low` (summaries/chat), smart `gemini-3.8-flash-high` (cross-project, "think deeply"). `agy models` lists IDs; effort is part of the ID. Gemini 4 Argon unused.
- **Latency findings (Phase 7):** a call is ~9.8 s, of which ~6.5 s is process startup and ~3 s model inference. History: 112 answers, avg 11.9 s, slowest 36.5 s. Everything without the model is < 1 s. agy supports streaming output (first event ~3.7 s, total 7.4 s vs 9.4 s plain) and persistent input mode; input messages need an `"event"` field mirroring output events, exact shape not yet found. Pre-warming a process per request is possible (it starts and idles ready). Decide on A3 after reading real `timing` rows.

## 5. Request flow

```
Browser/Phone -> FastAPI 127.0.0.1:<port> (serves frontend/dist + /api/*)
  guard: token or session cookie + local Host + allowed Origin (remote via tailscale serve = readonly)
  Orchestrator.handle -> router.route (regex, no LLM) -> handler
    quick_reply (time, greet, help, thanks, name, unknown_app)   instant
    progress / about / read_doc: handoff/README/doc -> cached summary (memory + SQLite, by mtime) or agy fast
    cross_project: all handoffs -> agy smart;  git_status, weather (Open-Meteo, wttr.in, 10 min cache),
    notes/reminders (SQLite), open_url (fixed https templates, frontend window.open), db/settings panels (PIN)
    open app/folder/task/command: blocked if readonly; allowlist apps.json; confirm click if needed
    chat fallback: agy answers or emits a closed read-only INTENT:<kind> tag validated in Python
  -> audit log (SQLite) incl. timing row -> reply (+focus node/item, understood tag) -> UI + TTS
```

Tiers: instant Python < 10 ms; fast model ~8-12 s; smart model ~12-15 s. Chat sees the last 6 exchanges of the login (memory only, 400 chars each, dropped after 30 idle min / restart / "new session" / `/clear` / `/new`).

## 6. Feature notes (all built, tests green)

- **Commands:** `nightmare_helper.txt` lists every voice/text command; `/help`, `/clear`, `/new`, `/reminders`, `/db`, `/settings`, `/sleep`. Websites ("open youtube and search lofi", "google x", "open github.com") are tabs, never programs. Reminders: casual phrasing, list, "delete the class reminder"/"delete reminder 3" (asks if several, refuses "delete all").
- **UI:** crimson node-graph dashboard (Orb eye = hold-to-talk, nodes Projects/Reminders/Apps/Tasks/Quick asks, arc scroll, Details + Conversation tabs, response-time chart); `focus` highlight after each reply; sleep after 5 idle min / "go to sleep", "Nightmare, wake up"; male/female voice, speed presets, full read-aloud; `/chat` replies carry `focus {node,item}`.
- **Small window:** `backend/hotkey.py` (`pythonw -m backend.hotkey`), `NIGHTMARE_HOTKEY` default ctrl+alt+n, 400x560 top-most Chrome `--app ?mini`; "home"/"mini" are browser-side. Autostart not registered on this laptop.
- **Phone:** `PhoneView` bottom tabs Talk/Projects/Reminders/Chat; `interactive-widget=resizes-content`; manifest + icon for Add to Home screen. `transcript.js` merges Android's growing speech results (`npm test`).
- **Phase 4 (Tailscale):** `scripts/setup_tailscale.ps1` (serve --bg --https=443 -> 127.0.0.1:8010, never Funnel; writes `NIGHTMARE_ALLOWED_HOSTS`; `-Restart -Status -Off`). Host `garcia2024.tail39da4a.ts.net`. Remote requests (Host in allowed list or X-Forwarded-*/Tailscale-User-Login) are read-only whatever credential they carry; remote cookies are Secure; rate limits per phone.
- **Phase 6:** git repo (`main`, `.env`/`*.db`/`apps.json`/logs/backups ignored); `scripts/install.ps1` (re-runnable; `-Dev -Autostart -Shortcut -NoPrompt`); Settings editor for apps.json (typed PIN, 10-min token, validation in `apps_config.py`, tasks and shell-host apps always confirm, atomic save + 5 backups, 409 on external edits); Activity viewer (`/db/actions` filters group/outcome/search/paging, "Phone" tag); Playwright browser tests.
- **Activity log:** pruned at startup after `LOG_RETENTION_DAYS` (90); reminders, model-call counts and summaries are kept.

## 7. Code map

```
scripts/  install.ps1 nightmare_env.ps1 start_nightmare.ps1 setup_tailscale.ps1 install_autostart.ps1 uninstall_autostart.ps1 agy_smoke_test.py
backend/  __main__.py main.py(FastAPI, lifespan starts summary refresher) config.py(.env) hotkey.py
  core/ router.py(regex intents, QUICK_*, UNLISTED_APP_NAMES) orchestrator.py(handlers, _SummaryCache, refresher, timing) memory.py(relevance recall)
        actions.py(Registry, plans, execute, PendingStore) apps_config.py llm.py(AgyProvider, NoLLMProvider)
  tools/ fs_reader.py weather.py audit.py(SQLite: actions, llm_calls, notes, summaries, facts, conversations, day_summaries)
  tests/ 200 passed, 1 skipped (non-browser) + 8 browser tests
frontend/ src/App.jsx api.js components/* utils/(useSpeech.js transcript.js useMic.js) tests/transcript.test.mjs
```

## 8. Security (keep)

- LLM never chooses actions or sees paths/shell; documents go in `<handoff>`/`<document>` data tags with closing tags neutralized.
- `fs_reader` opens only handoff/safe `.md`/`.txt` (blocks `.env`, secret/password/credential/token names, `.pem`, `.key`, `id_rsa*`), resolves symlinks, stays inside the Desktop root.
- Closed-set LLM classifier can reach only read-only tools. Token/PINs only in `backend/.env`. Login rate-limited (5/60 s), HttpOnly SameSite=Strict cookies.
- Backend bound to 127.0.0.1; remote only via Tailscale serve + login. Settings/database need a typed PIN on laptop sessions. Everything logged to `backend/nightmare.db` and `backend/logs/nightmare.log`.

## 9. Roadmap and rules

- Phases 1, 1.5, 2, 3, 4, 6: **done**. Phase 5 (voice upgrade) is folded into Phase 7B.
- **Phase 7 plan:**
  - **A Speed:** done: more instant replies/fuzzy matching, persistent + background summaries, timing log. Left: A3 speak the first sentence while agy still streams (check feasibility first).
  - **C Memory (DONE):** conversations stored in SQLite, older turns condensed to a summary; "remember that X"/"forget X" facts, viewable/deletable in the database panel, phone read-only; recall only memories relevant to the question; raw conversations 90 days.
  - **D Workspace awareness:** background scan (no model) of git branch, uncommitted files, ahead/behind, last commit, handoff changes, TODO counts; briefings ("what changed since yesterday", "what should I work on", nudges); dev tasks found from package.json scripts/pytest/git ("run bims tests", "run it again") that always ask for a click; detection is plain code.
  - **B Offline:** measure first, switch only where faster than agy. Candidate local model: the user's fine-tuned Llama 3 8B Instruct (CPU-only is likely slow; propose before installing anything). faster-whisper (~150-500 MB) and Piper (~60 MB) need approval before download. Offline status bar; weather keeps its last reading.
- **Rules:** update both handoff files after work; keep the LLM out of the action path (new actions via apps.json allowlist or validated read-only tools); backend stays on 127.0.0.1; never claim something works unless run on this machine; label UNVERIFIED.

## 10. Commands (PowerShell, project root)

```powershell
.\scripts\start_nightmare.ps1 -Rebuild      # rebuild UI + restart  (-Background for pythonw)
.\scripts\setup_tailscale.ps1 -Restart      # phone access (-Status, -Off)
.\scripts\install.ps1 -Dev                  # setup/repair, safe to re-run
.\scripts\install_autostart.ps1             # start at log on (backend + hotkey helper)
.\.venv\Scripts\python.exe -m pytest backend -q -m "not browser"   # expect 228 passed, 1 skipped (with browser tests)
cd frontend; npm test
```
