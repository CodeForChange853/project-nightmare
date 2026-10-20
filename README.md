# Project Nightmare (backend v0)

Local-only voice assistant backend. FastAPI on `127.0.0.1`, uses your signed-in
**Antigravity CLI (`agy`)** / Google AI Pro account for summaries, no API key.

```
transcript -> router (regex, no LLM) -> tool -> agy summarizes text -> reply
                                          \-> allowlisted action (confirm if needed)
```

## Setup (Windows PowerShell)

```powershell
cd project-nightmare
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r backend\requirements.txt

# 1. FIRST: check agy works from Python. Paste the output back into the chat.
python scripts\agy_smoke_test.py

# 2. Configure
copy backend\.env.example backend\.env          # set NIGHTMARE_TOKEN (see comment inside)
copy backend\apps.example.json backend\apps.json  # edit apps and tasks to match your machine

# 3. Test and run
python -m pytest backend -q
python -m backend
```

Try it (PowerShell):

```powershell
$h = @{ "X-Nightmare-Token" = "<your token>" }
Invoke-RestMethod http://127.0.0.1:8000/status -Headers $h
Invoke-RestMethod -Method Post http://127.0.0.1:8000/chat -Headers $h -ContentType "application/json" `
  -Body '{"text":"go to my desktop directory, look for the project name bims and tell me the progress of it"}'
```

If your Desktop is not at `C:\Users\<you>\Desktop` (OneDrive redirects it), set `DESKTOP_ROOT` in `.env`.

## Frontend (second terminal)

Needs Node 20.19+ or 22.12+ (Vite 8).

```powershell
cd frontend
copy .env.local.example .env.local   # same NIGHTMARE_TOKEN as backend\.env
npm install
npm run dev
```

Open **http://127.0.0.1:5173** in Chrome or Edge (voice input does not work in Firefox).

- **Hold Space** (or the button) to talk, release to send. Typing in the box also works, and Space only talks when the box is not focused.
- `agy` takes roughly 10 to 15 seconds per call, so the waveform switches to a scanning animation with a seconds counter while it thinks.
- Actions that need confirmation open a dialog showing the exact command. **Only a click can approve** (voice cannot), Deny is focused by default, Esc denies, and it expires after 60 seconds.
- The token lives only in `frontend/.env.local` (no `VITE_` prefix). The Vite dev server's proxy adds it to `/api/*` requests, so it is never sent to the browser.
- Chrome and Edge do speech recognition in the vendor's cloud, so what you say is sent to Google/Microsoft. Typing avoids that.

## What it can do now

| Say | What happens |
|---|---|
| "progress of bims" / "status of citizen graph" | finds the folder, finds `handoff.md` (up to 2 levels deep), `agy` summarizes it |
| "list my projects" | lists folders on the Desktop |
| "open notepad" / "launch vs code" | opens an app from the `apps.json` allowlist |
| "open the bims folder" | opens it in Explorer |
| "open bims in vs code" | opens the project in an editor that has `"project_arg": true` |
| "start the bims dev server" | runs a task from `apps.json`; asks for confirmation unless `"confirm": false` |
| "run command ..." | off by default (`ALLOW_RAW_COMMANDS=1`); always asks for confirmation |
| "how many calls today" | counts Nightmare's own `agy` calls (it cannot read your Pro quota) |
| anything else | plain chat answer from `agy`, no actions possible |

Actions that need confirmation return `needs_confirm: true` and a `pending_id`.
The UI must show `action_label` (the exact command) and then `POST /confirm {"id", "approve"}`.
Pending actions live on the server for 60 seconds, work once, and cannot be swapped for a different command.

## Safety model

- **The LLM never decides what to do.** Routing is regex plus the `apps.json` allowlist. `agy` only summarizes text or chats, so a prompt injection inside a `handoff.md` cannot become a command.
- **The LLM never gets a path or a shell.** Python resolves the folder, reads only a file named `handoff.md`, resolves symlinks and checks it is still under `DESKTOP_ROOT`.
- **`agy` print mode auto-approves its own tools.** So `agy` runs from an empty scratch folder, the prompts forbid tools, and API-key env vars are scrubbed so it uses your subscription login.
- **Local only.** `python -m backend` binds `127.0.0.1`. Every request needs the token header, a local `Host` (anti DNS-rebinding) and, if present, an allowed `Origin` (so other web pages in your browser cannot call it).
- **Phone access only through Tailscale, read-only.** `tailscale serve` (tailnet only, never Funnel) proxies HTTPS to `127.0.0.1`. The tailnet name must be listed in `NIGHTMARE_ALLOWED_HOSTS`, and any request that arrives through the proxy gets a read-only session whichever PIN or token it uses. See `scripts/setup_tailscale.ps1`.
- **No `shell=True`.** Programs start from an argv list. `.cmd`/`.bat` launchers reject special characters in arguments.
- Every action and `agy` call is logged to `backend/nightmare.db` (`GET /audit`).

## Verified vs not verified

Verified:
- **Your machine:** `agy` 1.4.2 returns output through plain subprocess capture (JSON and text, including a multi-line prompt with quotes and `& | %`).
- **Linux, 61 tests:** routing, folder matching, path and symlink safety, token/origin/host checks, confirmation flow, audit log, and the `agy` wrapper against a fake `agy`.
- **Linux, live servers:** the frontend builds; through the Vite proxy the token is injected, a foreign `Origin` and a foreign `Host` both get 403, and the token does not appear in the served code.

**Not verified, needs your machine:**
- How the UI looks and behaves in a browser (no browser was available to me): waveform, mic access, Space-to-talk, confirm dialog.
- Web Speech recognition and text-to-speech.
- `os.startfile` launching `chrome.exe`, `code.cmd` and `npm.cmd` resolution, and Windows Terminal flags.
- Opening the mic for the waveform while speech recognition also uses it. If recognition errors, tell me and I'll make the waveform simulated instead.

## Next

1. Run it and tell me what breaks.
2. Weather and Google Calendar (read-only) as extra tools.
3. Optional: wake word, local speech models.
