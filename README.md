# Project Nightmare

A local voice assistant for one Windows laptop. Ask it, by voice or text, about the projects on your Desktop, your reminders, the weather, or to open allowlisted apps and run predefined tasks. Summaries and chat use your signed-in **Antigravity CLI (`agy`)** on the Google AI Pro subscription, with no API key and no separate billing. Your Android phone can use it read-only over Tailscale.

```
voice / text -> router (regex, no LLM) -> read-only tool or allowlisted action (click to confirm)
                                     \-> agy only summarizes text or chats; it never chooses an action
```

The full command list is in `nightmare_helper.txt` (or type `/help`). Design notes and the phase log are in `handoff.md`.

## Install (Windows PowerShell)

Needs Python 3.11+, Node 20.19+ or 22.12+, Google Chrome, and `agy` signed in.

```powershell
cd project-nightmare
.\scripts\install.ps1                 # venv, packages, frontend build, backend\.env (asks for PINs), apps.json
.\scripts\start_nightmare.ps1 -Background
```

Open **http://127.0.0.1:<NIGHTMARE_PORT>** in Chrome and type your laptop PIN.

`install.ps1` options: `-Autostart` (start at Windows log on), `-Shortcut` (a Desktop icon that opens Nightmare in its own Chrome window), `-Dev` (test tools). It is safe to run again: it only fills in what is missing and never overwrites `backend\.env` values or `apps.json`.

## Everyday use

- **Talk:** hold the eye or Space, speak, release. Replies are read aloud (male/female voice, 0.9x to 1.5x).
- **Type:** the command box; `/` lists slash commands (`/help`, `/clear`, `/reminders`, `/db`, `/settings`, `/sleep`).
- **Apps and tasks:** "open settings" (or the sliders button) and type your PIN to add, change or remove what Nightmare may open or run. Changes work at once, without a restart.
- **Database:** "database access open" + PIN shows reminders, the activity log (filter by logins, actions, reminders or questions; problems only; search) and model calls.
- **Phone:** see "Phone access" below.

## Phone access (Tailscale, read-only)

1. Install Tailscale on the laptop and the phone with the same account; turn on MagicDNS and HTTPS Certificates in the admin console.
2. Set `NIGHTMARE_PHONE_PIN` in `backend\.env` (6+ digits).
3. `.\scripts\setup_tailscale.ps1 -Restart`, then open the printed `https://<laptop>.<tailnet>.ts.net/` in Chrome on the phone.

Everything that arrives through Tailscale is read-only, whichever PIN is typed: it can ask about projects, git status, documents, weather, reminders and chat, but cannot open, run, approve, open Settings or the database. `-Status` shows what is shared, `-Off` stops it.

## Safety model

- **The LLM never decides what to do.** Routing is regex plus the `apps.json` allowlist. `agy` only summarizes text or chats, and project files reach it as quoted data, so a prompt injection in a `handoff.md` cannot become a command.
- **The LLM never gets a path or a shell.** Python resolves folders, opens only `handoff.md`, READMEs and safe `.md`/`.txt` files (no secrets, keys or `.env`), resolves symlinks and stays inside `DESKTOP_ROOT`. `agy` runs from an empty scratch folder with API-key variables removed.
- **Bound to `127.0.0.1`.** Every request needs a session cookie (PIN login) or the token, a local `Host` (stops DNS rebinding) and, if sent, an allowed `Origin` (stops other web pages).
- **Phone access only through Tailscale, read-only.** `tailscale serve` (tailnet only, never Funnel) proxies HTTPS to `127.0.0.1`. The tailnet name must be in `NIGHTMARE_ALLOWED_HOSTS`, and any request that comes through the proxy gets a read-only session whichever PIN or token it uses.
- **Click to confirm.** Tasks ask before running unless set otherwise by hand; voice cannot approve. Tasks added or changed in Settings, and apps that start a shell or script host (`cmd`, `powershell`, `python`, ...), always ask.
- **Settings and the database need the typed PIN** and lock again after 10 minutes. Voice can open the panels but not change anything. Saves are validated, atomic, backed up (last 5 in `backend\backups\`) and refuse to overwrite a hand edit.
- **No `shell=True`.** Programs start from an argument list; `.cmd`/`.bat` launchers reject special characters.
- Everything is logged to `backend\nightmare.db` (activity rows older than `LOG_RETENTION_DAYS` are pruned at startup).

## Development

```powershell
.\scripts\install.ps1 -Dev
.\.venv\Scripts\python.exe -m pytest backend -q                     # backend + browser tests (Chrome, ~1 min)
.\.venv\Scripts\python.exe -m pytest backend -q -m "not browser"    # fast run, ~20 s
cd frontend; npm test                                               # frontend unit tests
npm run dev                                                         # Vite on :5173 (needs frontend\.env.local)
```

Browser tests drive the built UI (`npm run build` first) in your installed Chrome through Playwright, against a backend running inside the test with a fake model and temporary files, so nothing real is opened or changed.

| Path | What |
|---|---|
| `backend/main.py` | FastAPI app, auth, host/origin checks, Settings and database endpoints |
| `backend/core/router.py` | regex intent router |
| `backend/core/orchestrator.py` | handlers, model tiers, caches, read-only guard |
| `backend/core/actions.py` | allowlist registry, action plans, execution, pending confirmations |
| `backend/core/apps_config.py` | Settings: validation, change list, atomic save, dry-run check |
| `backend/core/llm.py` | `agy` wrapper |
| `backend/tools/` | file reader, weather, SQLite audit and reminders |
| `frontend/src/` | React UI (eye and graph, panels, speech) |
| `scripts/` | install, start, autostart, Tailscale |
