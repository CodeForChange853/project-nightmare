"""Settings for Project Nightmare, read from backend/.env (see .env.example)."""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

BACKEND_DIR = Path(__file__).resolve().parent
DEFAULT_ORIGINS = ("http://localhost:5173", "http://127.0.0.1:5173")


def _flag(value: str | None, default: bool = False) -> bool:
    if value is None or value.strip() == "":
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def default_desktop() -> Path:
    """Desktop folder, including the OneDrive-redirected location on Windows."""
    home = Path.home()
    for candidate in (home / "Desktop", home / "OneDrive" / "Desktop"):
        if candidate.is_dir():
            return candidate
    return home / "Desktop"


def _hostnames(value: str | None) -> tuple:
    """NIGHTMARE_ALLOWED_HOSTS: comma-separated names like laptop.tail1234.ts.net.
    Tolerates a pasted URL (scheme, port, path, trailing dot) and lowercases it."""
    names = []
    for raw in (value or "").split(","):
        name = raw.strip().lower()
        if "://" in name:
            name = name.split("://", 1)[1]
        name = name.split("/", 1)[0].rsplit(":", 1)[0].rstrip(".")
        if name:
            names.append(name)
    return tuple(dict.fromkeys(names))


@dataclass(frozen=True)
class Settings:
    desktop_root: Path
    api_token: str
    allowed_origins: tuple = DEFAULT_ORIGINS
    port: int = 8000
    pin: str = ""
    phone_pin: str = ""
    session_ttl: int = 86400 * 7  # 7 days
    agy_command: str = "agy"
    agy_timeout: int = 90
    agy_format: str = "auto"  # auto | json | text
    agy_fast_model: str = "gemini-3.8-flash-low"
    agy_smart_model: str = "gemini-3.8-flash-high"
    handoff_filename: str = "handoff.md"
    handoff_max_chars: int = 12000
    db_path: Path = BACKEND_DIR / "nightmare.db"
    apps_file: Path = BACKEND_DIR / "apps.json"
    confirm_ttl: int = 60
    allow_raw_commands: bool = False
    llm_enabled: bool = True
    weather_city: str = "Calbayog"
    weather_api_key: str = ""
    log_retention_days: int = 90  # activity-log rows older than this are pruned at startup; 0 keeps all
    remote_hosts: tuple = ()  # tailscale serve names; requests under them are remote and read-only

    @classmethod
    def from_env(cls) -> "Settings":
        load_dotenv(BACKEND_DIR / ".env")
        env = os.environ

        token = env.get("NIGHTMARE_TOKEN", "").strip()
        if len(token) < 16:
            raise RuntimeError(
                "NIGHTMARE_TOKEN is missing or too short. Generate one with:\n"
                '  python -c "import secrets; print(secrets.token_urlsafe(32))"\n'
                "and put it in backend/.env as NIGHTMARE_TOKEN=..."
            )

        port = int(env.get("NIGHTMARE_PORT", "8000"))
        local_port_origins = (f"http://127.0.0.1:{port}", f"http://localhost:{port}")
        configured_origins = tuple(
            o.strip() for o in env.get("NIGHTMARE_ORIGINS", "").split(",") if o.strip()
        ) or DEFAULT_ORIGINS
        origins = tuple(dict.fromkeys((*configured_origins, *local_port_origins)))

        fmt = (env.get("AGY_FORMAT") or "auto").strip().lower()
        if fmt not in {"auto", "json", "text"}:
            raise RuntimeError("AGY_FORMAT must be auto, json or text")

        return cls(
            desktop_root=Path(env.get("DESKTOP_ROOT") or default_desktop()).expanduser(),
            api_token=token,
            allowed_origins=origins,
            port=port,
            pin=env.get("NIGHTMARE_PIN", "").strip(),
            phone_pin=env.get("NIGHTMARE_PHONE_PIN", "").strip(),
            session_ttl=int(env.get("SESSION_TTL", str(86400 * 7))),
            agy_command=env.get("AGY_COMMAND", "agy").strip() or "agy",
            agy_timeout=int(env.get("AGY_TIMEOUT", "90")),
            agy_format=fmt,
            agy_fast_model=env.get("AGY_FAST_MODEL", "gemini-3.8-flash-low").strip(),
            agy_smart_model=env.get("AGY_SMART_MODEL", "gemini-3.8-flash-high").strip(),
            handoff_filename=env.get("HANDOFF_FILENAME", "handoff.md").strip() or "handoff.md",
            handoff_max_chars=int(env.get("HANDOFF_MAX_CHARS", "12000")),
            db_path=Path(env.get("NIGHTMARE_DB") or BACKEND_DIR / "nightmare.db"),
            apps_file=Path(env.get("NIGHTMARE_APPS_FILE") or BACKEND_DIR / "apps.json"),
            confirm_ttl=int(env.get("CONFIRM_TTL", "60")),
            allow_raw_commands=_flag(env.get("ALLOW_RAW_COMMANDS"), False),
            llm_enabled=_flag(env.get("LLM_ENABLED"), True),
            weather_city=env.get("WEATHER_CITY", "Calbayog").strip() or "Calbayog",
            weather_api_key=env.get("OPENWEATHER_API_KEY", "").strip(),
            log_retention_days=int(env.get("LOG_RETENTION_DAYS", "90")),
            remote_hosts=_hostnames(env.get("NIGHTMARE_ALLOWED_HOSTS")),
        )
