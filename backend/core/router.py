"""Deterministic intent router. No LLM is involved in deciding what to *do*.

The model only summarizes text and chats (and in Phase 2 can classify a missed sentence
into a closed list of read-only intents validated by Python); actions come strictly from
these patterns plus the allowlist in apps.json.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re
from urllib.parse import quote_plus

from ..config import Settings
from ..tools.fs_reader import EXPLICIT_DOC_RE, Resolution, normalize, resolve_project
from .actions import Registry

RAW_CMD = re.compile(
    r"^\s*(?:nightmare[, ]+)?(?:run|execute)\s+(?:the\s+)?(?:shell\s+)?command[: ]+(?P<cmd>.+?)\s*$",
    re.I,
)
# polite / wake-word lead-in allowed before a command: "hey nightmare, can you please ..."
LEAD = r"^\s*(?:(?:hey|ok|hi)\s+)?(?:nightmare[, ]+)?(?:please\s+)?(?:(?:can|could|would)\s+you\s+)?(?:please\s+)?"
ADD_NOTE_RE = re.compile(
    LEAD
    + r"(?:remind\s+me(?:\s+(?:later|again|tomorrow|today|tonight|soon))?(?:\s+(?:to|that|about|of|for|on))?"
    r"|(?:add|set|create|make|save)\s+(?:a\s+|an\s+)?(?:new\s+)?(?:reminder|note)(?:\s+(?:to|that|about|for|on))?"
    r"|note\s+(?:to\s+self|that|down)"
    r"|remember\s+(?:to|that))"
    r"[:,\s]+(?P<note>.+?)\s*[.!]*$",
    re.I,
)
DELETE_NOTE_RE = re.compile(
    LEAD + r"(?:delete|remove|erase|cancel|drop|clear|forget(?:\s+about)?)\s+(?P<rest>.*?\b(?:reminders?|notes?)\b.*?)\s*[.!?]*$",
    re.I,
)
COMPLETE_NOTE_RE = re.compile(
    LEAD
    + r"(?:i\s*(?:'m|am)\s+)?(?:complete|finish(?:ed)?|check\s+off|tick\s+off|mark|done\s+with)\s+"
    r"(?P<rest>.*?\b(?:reminders?|notes?)\b.*?)\s*[.!?]*$",
    re.I,
)
NOTE_ID_RE = re.compile(
    r"#\s*(?P<a>\d{1,6})\b|\b(?:reminders?|notes?)\s+(?:number\s+|no\s+|num\s+)?(?P<b>\d{1,6})\b|^\s*(?P<c>\d{1,6})\s*$",
    re.I,
)
NUMBER_WORDS = {
    w: i
    for i, w in enumerate(
        "zero one two three four five six seven eight nine ten eleven twelve thirteen fourteen fifteen "
        "sixteen seventeen eighteen nineteen twenty".split()
    )
}
# runs on normalized text, so "what's" arrives as "what s"
LIST_NOTES_RE = re.compile(
    r"\b(?:(?:what\s+are|what\s+s|whats|list|show|read|check|tell\s+me|give\s+me|any|do\s+i\s+have(?:\s+any)?"
    r"|have\s+i\s+got(?:\s+any)?|how\s+many)\s+(?:of\s+)?(?:(?:my|the|active|pending|open)\s+)*(?:reminders?|notes?)"
    r"|my\s+(?:reminders?|notes?))\b"
)
DB_OPEN_RE = re.compile(
    LEAD
    + r"(?:database\s+(?:access\s+)?open|open\s+(?:the\s+)?database(?:\s+access)?|access\s+(?:the\s+)?database"
    r"|show\s+(?:me\s+)?(?:the\s+)?database|unlock\s+(?:the\s+)?database)\s*[.!?]*$",
    re.I,
)
RESET_RE = re.compile(
    LEAD
    + r"(?:(?:clear|reset|wipe)\s+(?:the\s+|this\s+|our\s+|my\s+)?(?:conversation|chat|screen|session|history)"
    r"|(?:start\s+)?(?:a\s+)?new\s+(?:session|conversation|chat)"
    r"|start\s+(?:over|fresh)"
    r"|forget\s+(?:our|this|the)\s+(?:conversation|chat))\s*[.!?]*$",
    re.I,
)
DB_CLOSE_RE = re.compile(
    LEAD
    + r"(?:database\s+(?:access\s+)?close|close\s+(?:the\s+)?database(?:\s+access)?|lock\s+(?:the\s+)?database"
    r"|exit\s+(?:the\s+)?database|hide\s+(?:the\s+)?database)\s*[.!?]*$",
    re.I,
)
WEATHER_RE = re.compile(
    r"\b(?:weather|temperature|forecast|is\s+it\s+(?:going\s+to\s+)?rain(?:ing)?|how\s+(?:hot|cold)\s+is\s+it)"
    r"(?:.*?\b(?:in|at|for)\s+(?P<city>[a-zA-Z][a-zA-Z\s]{1,30}))?",
    re.I,
)
CITY_WEATHER_RE = re.compile(
    r"^\s*(?:check\s+|what(?:'s|\s+is)\s+(?:the\s+)?)?(?P<city>[a-zA-Z]{3,20})\s+(?:city\s+)?(?:weather|forecast|temperature)\s*[?.!]*$",
    re.I,
)
QUICK_TIME_RE = re.compile(
    r"\b(?:what\s+time\s+is\s+it|what(?:'s|\s+is)\s+the\s+(?:current\s+)?time|current\s+time|"
    r"what\s+(?:day|date)\s+is\s+(?:it|today)|today(?:'s|\s+is)\s+date)\b",
    re.I,
)
QUICK_HELP_RE = re.compile(
    r"^\s*(?:(?:hey|ok|hi)\s+)?(?:nightmare[, ]+)?(?:help|what\s+can\s+you\s+do|what\s+are\s+your\s+commands|list\s+commands|capabilities)\s*[?.!]*$",
    re.I,
)
QUICK_GREET_RE = re.compile(
    r"^\s*(?:hello|hi|hey|yo|good\s+(?:morning|afternoon|evening)|are\s+you\s+there|mic\s+check|testing)"
    r"(?:\s+nightmare)?\s*[?.!]*$",
    re.I,
)
QUICK_THANKS_RE = re.compile(
    r"^\s*(?:thank\s+you|thanks)(?:\s+so\s+much|\s+a\s+lot)?(?:\s+nightmare)?\s*[?.!]*$",
    re.I,
)
GIT_STATUS_RE = re.compile(
    r"\b(?:git\s+(?:status|branch)|what\s+branch\s+is|uncommitted\s+changes)\b",
    re.I,
)
RUN_VERB = re.compile(r"\b(start|run|launch|execute|kick off|fire up|spin up)\b")
OPEN_VERB = re.compile(r"\b(open|launch|start|run|fire up)\b")
FOLDER_WORD = re.compile(r"\b(folder|directory|explorer|file explorer)\b")
IN_WITH = re.compile(r"\b(in|with|using)\b")
LIST_PROJECTS = re.compile(
    r"\b(list|show|which|what)\b.*\bprojects\b|\bprojects\s+on\s+(?:my\s+)?desktop\b"
)
CROSS_PROJECT = re.compile(
    r"\b("
    r"(?:which|what)\s+projects?\s+needs?\s+attention|"
    r"(?:progress|status|summary|overview)\s+of\s+(?:all|every)\s+(?:my\s+)?projects|"
    r"all\s+projects\s+(?:progress|status|summary)|"
    r"catch\s+me\s+up\s+on\s+(?:all|every)\s+(?:my\s+)?projects|"
    r"compare\s+(?:my\s+)?projects"
    r")\b"
)
DOC_LOOKUP = re.compile(
    r"\b("
    r"what(?:'s|\s+is)\s+written\s+in|"
    r"(?:find|read|summarize|summarise|show|open)\b.*\b(?:file|doc|document|readme|notes)\b|"
    r"(?:find|read|tell\s+me\s+what(?:'s|\s+is)\s+written)\b.*\.(?:md|txt|env|pem|key|json)\b"
    r")",
    re.I,
)
ANY_FILENAME_RE = re.compile(r"\b[a-z0-9_.-]+\.(?:md|txt|env|pem|key|json|yaml|yml|py|js)\b", re.I)
PROGRESS = re.compile(
    r"\b("
    r"progress|status|handoff|hand off|left off|leave off|where am i|update on|catch me up|"
    r"summary|summarize|summarise|check on|check project|read handoff|what did i do on|"
    r"latest (?:on|of|for)|how (?:is|s) .+ going|what(?: is| s) going on with|"
    r"what(?: is| s) next|next (?:tasks?|steps?)|(?:to )?do next"
    r")\b"
)
# "what is citizengraph all about" -> the project's README, not its progress log
ABOUT = re.compile(
    r"\b("
    r"what(?: is| s| was)\b.*\babout|tell me (?:all )?about|what does .+ do|"
    r"describe|explain (?:the |my )?(?:project )?\w+|what kind of (?:project|app|system) is|"
    r"what(?: is| s) (?:the |my )?(?:project )?\S+ (?:project|app|system)$"
    r")\b"
)
USAGE = re.compile(r"\b(usage|quota|how many (calls|requests|prompts))\b")
FOLLOWUP_REF = re.compile(r"\b(it|its|that|this|there|the project|that project|this project|that folder|the folder)\b")

# Websites open as a new tab in the browser showing Nightmare (the frontend does window.open),
# never by launching a program. URLs come only from these fixed templates; the spoken search
# text is URL-encoded into {q}.
WEB_SITES = {
    "youtube": ("YouTube", "https://www.youtube.com", "https://www.youtube.com/results?search_query={q}", ("you tube", "yt")),
    "google": ("Google", "https://www.google.com", "https://www.google.com/search?q={q}", ()),
    "gmail": ("Gmail", "https://mail.google.com", None, ("g mail", "my email", "my inbox")),
    "maps": ("Google Maps", "https://www.google.com/maps", "https://www.google.com/maps/search/{q}", ("google maps",)),
    # spelled out on purpose: a bare "docs" or "drive" would steal "open bims/docs ..." style requests
    "google drive": ("Google Drive", "https://drive.google.com", None, ()),
    "google docs": ("Google Docs", "https://docs.google.com", None, ()),
    "classroom": ("Google Classroom", "https://classroom.google.com", None, ("google classroom",)),
    "calendar": ("Google Calendar", "https://calendar.google.com", None, ("google calendar",)),
    "gemini": ("Gemini", "https://gemini.google.com", None, ()),
    "chatgpt": ("ChatGPT", "https://chatgpt.com", None, ("chat gpt",)),
    "github": ("GitHub", "https://github.com", "https://github.com/search?q={q}", ("git hub",)),
    "stackoverflow": ("Stack Overflow", "https://stackoverflow.com", "https://stackoverflow.com/search?q={q}", ("stack overflow",)),
    "wikipedia": ("Wikipedia", "https://en.wikipedia.org", "https://en.wikipedia.org/w/index.php?search={q}", ("wiki",)),
    "facebook": ("Facebook", "https://www.facebook.com", "https://www.facebook.com/search/top?q={q}", ("fb",)),
    "messenger": ("Messenger", "https://www.messenger.com", None, ()),
    "instagram": ("Instagram", "https://www.instagram.com", None, ("ig",)),
    "tiktok": ("TikTok", "https://www.tiktok.com", "https://www.tiktok.com/search?q={q}", ("tik tok",)),
    "reddit": ("Reddit", "https://www.reddit.com", "https://www.reddit.com/search/?q={q}", ()),
    "linkedin": ("LinkedIn", "https://www.linkedin.com", None, ("linked in",)),
    "netflix": ("Netflix", "https://www.netflix.com", "https://www.netflix.com/search?q={q}", ()),
    "spotify": ("Spotify", "https://open.spotify.com", "https://open.spotify.com/search/{q}", ()),
    "canva": ("Canva", "https://www.canva.com", None, ()),
    "figma": ("Figma", "https://www.figma.com", None, ()),
    "shopee": ("Shopee", "https://shopee.ph", "https://shopee.ph/search?keyword={q}", ()),
    "lazada": ("Lazada", "https://www.lazada.com.ph", "https://www.lazada.com.ph/catalog/?q={q}", ()),
}
WEB_ALIASES = sorted(
    ((alias, key) for key, (_, _, _, extra) in WEB_SITES.items() for alias in (key, *extra)),
    key=lambda pair: -len(pair[0]),
)
WEB_VERB = re.compile(r"\b(open|launch|go\s+to|visit|browse|search|look\s+up|play|watch|pull\s+up|bring\s+up)\b")
BROWSER_HINT = re.compile(r"\b(browser|tab|website|site|web|online)\b")
BROWSER_APPS = {"chrome", "edge", "msedge", "firefox", "brave", "opera", "browser"}
SEARCH_VERB = r"(?:search|look\s+up|find|play|watch)(?:\s+(?:for|about))?"
WEB_TAIL_RE = re.compile(
    r"\s+(?:in|on|using|with)\s+(?:this|the|my|a)?\s*(?:new\s+)?(?:browser|tab|chrome|edge|window)\b.*$|\s+please$",
    re.I,
)
DOMAIN_RE = re.compile(r"\b(?:open|go\s+to|visit|browse)\s+(?:to\s+)?(?P<domain>(?:[a-z0-9-]+\.)+(?:com|org|net|io|dev|app|ph|edu|gov|ai|co)(?:\.[a-z]{2})?)\b", re.I)
GENERIC_SEARCH_RE = re.compile(
    LEAD + r"(?:search|google|look\s+up)\s+(?:the\s+web\s+|online\s+|on\s+google\s+|google\s+)?(?:for\s+)?(?P<q>.+?)\s*[.!?]*$",
    re.I,
)


@dataclass
class Intent:
    kind: str  # run_command | run_task | open_folder | open_project_in | open_app |
    # list_projects | cross_project | read_doc | about | progress | git_status |
    # weather | add_note | list_notes | complete_note | usage | chat
    text: str
    app_id: str | None = None
    task_id: str | None = None
    command: str | None = None
    resolution: Resolution | None = None
    note_text: str | None = None
    note_id: int | None = None
    city: str | None = None
    url: str | None = None
    site: str | None = None
    query: str | None = None
    history: tuple = ()  # recent (user, reply) turns, filled in by the orchestrator for chat


def describe_intent(intent: Intent) -> str:
    proj = None
    if intent.resolution and intent.resolution.matches:
        proj = intent.resolution.matches[0][0].name
    if intent.kind == "progress":
        return f"progress → {proj or 'unknown project'}"
    if intent.kind == "read_doc":
        return f"read_doc → {proj or 'unknown project'}"
    if intent.kind == "about":
        return f"about → {proj or 'unknown project'}"
    if intent.kind == "git_status":
        return f"git_status → {proj or 'unknown project'}"
    if intent.kind == "cross_project":
        return "cross_project → all projects"
    if intent.kind == "open_folder":
        return f"open_folder → {proj or 'unknown folder'}"
    if intent.kind == "open_project_in":
        return f"open_project_in → {proj or '?'} in {intent.app_id}"
    if intent.kind == "open_app":
        return f"open_app → {intent.app_id}"
    if intent.kind == "run_task":
        return f"run_task → {intent.task_id}"
    if intent.kind == "run_command":
        return f"run_command → {intent.command}"
    if intent.kind == "list_projects":
        return "list_projects"
    if intent.kind == "weather":
        return f"weather → {intent.city or 'default city'}"
    if intent.kind == "add_note":
        return "add_note"
    if intent.kind == "list_notes":
        return "list_notes"
    if intent.kind in {"complete_note", "delete_note"}:
        target = f"#{intent.note_id}" if intent.note_id is not None else f"“{intent.note_text or '?'}”"
        return f"{intent.kind} → {target}"
    if intent.kind in {"db_open", "db_close", "reset_session"}:
        return intent.kind
    if intent.kind == "open_url":
        return f"open_url → {intent.site}" + (f" search “{intent.query}”" if intent.query else "")
    if intent.kind == "quick_reply":
        return f"quick_reply → {intent.note_text or 'instant'}"
    if intent.kind == "usage":
        return "usage"
    return "chat (no command matched)"


def _resolve_with_followup(text: str, n: str, root: Path, last_project: Path | None) -> Resolution:
    res = resolve_project(text, root)
    if res.status == "none" and last_project is not None and FOLLOWUP_REF.search(n):
        if last_project.is_dir():
            return Resolution("found", [(last_project, 1.0)])
    return res


def _is_doc_query(text: str, n: str) -> bool:
    m = EXPLICIT_DOC_RE.search(text)
    if m and m.group("fname").lower() != "handoff.md":
        return True
    if ANY_FILENAME_RE.search(text) and not re.search(r"\bhandoff\.md\b", text, re.I):
        if re.search(r"\b(read|find|written|show|what|inside|summarize|summarise)\b", n):
            return True
    if DOC_LOOKUP.search(text) and not re.search(r"\bhandoff\b", n):
        return True
    return False


def _note_target(rest: str) -> tuple[int | None, str]:
    """From "the class reminder" / "reminder 3" / "reminder number three", get (id, description)."""
    m = NOTE_ID_RE.search(rest)
    if m:
        return int(m.group("a") or m.group("b") or m.group("c")), ""
    nr = normalize(rest)
    m_word = re.search(r"\b(?:reminders?|notes?)\s+(?:number\s+)?(" + "|".join(NUMBER_WORDS) + r")\b", nr)
    if m_word:
        return NUMBER_WORDS[m_word.group(1)], ""
    return None, rest.strip()


def _web_target(text: str, n: str, registry: Registry) -> Intent | None:
    """A request to open a website or search it, opened as a browser tab (never a program)."""
    if FOLDER_WORD.search(n) or re.search(r"\bprojects?\b", n):
        return None
    padded = f" {n} "
    site_key = alias = None
    for a, key in WEB_ALIASES:
        if f" {a} " in padded:
            site_key, alias = key, a
            break

    def google_search() -> Intent | None:
        """'google how to center a div' / 'search the web for x' / 'look up x'."""
        m_gen = GENERIC_SEARCH_RE.match(text)
        if not m_gen or re.search(r"\b(reminders?|notes?|handoff|files?|folders?|docs?)\b", n):
            return None
        if PROGRESS.search(n) or GIT_STATUS_RE.search(n) or WEATHER_RE.search(text):
            return None  # those have their own tools
        q = WEB_TAIL_RE.sub("", m_gen.group("q")).strip(" .,?!")
        if not q:
            return None
        return Intent("open_url", text, url=WEB_SITES["google"][2].format(q=quote_plus(q)), site="Google", query=q)

    if site_key is None:
        m_dom = DOMAIN_RE.search(text)
        if m_dom:
            domain = m_dom.group("domain").lower()
            return Intent("open_url", text, url=f"https://{domain}", site=domain)
        return google_search()

    if not WEB_VERB.search(n):
        return google_search() if site_key == "google" else None
    # a desktop app registered under the same name wins, unless the browser was asked for
    app_id = registry.find_app(n)
    if app_id and app_id not in BROWSER_APPS and not BROWSER_HINT.search(n):
        return None

    label, home, search_tpl, _ = WEB_SITES[site_key]
    alias_re = re.escape(alias).replace(r"\ ", r"\s+")
    query = None
    for pattern in (
        rf"\b{SEARCH_VERB}\s+(?P<q>.+?)\s+(?:on|in|at|from|using)\s+(?:the\s+)?{alias_re}\b",  # play lofi on youtube
        rf"\b(?:search|look\s+up)\s+(?:on\s+|in\s+)?(?:the\s+)?{alias_re}\s+(?:for\s+|about\s+)?(?P<q>.+)$",  # search youtube for x
        rf"\b{alias_re}\b.*?\b(?:and\s+|then\s+)?{SEARCH_VERB}\s+(?P<q>.+)$",  # open youtube and search x
    ):
        m_q = re.search(pattern, text, re.I)
        if m_q:
            query = WEB_TAIL_RE.sub("", m_q.group("q")).strip(" .,?!") or None
            break
    if query and search_tpl:
        return Intent("open_url", text, url=search_tpl.format(q=quote_plus(query)), site=label, query=query)
    return Intent("open_url", text, url=home, site=label)


def route(
    text: str,
    settings: Settings,
    registry: Registry,
    last_project: Path | None = None,
) -> Intent:
    n = normalize(text)

    m = RAW_CMD.match(text)
    if m:
        return Intent("run_command", text, command=m.group("cmd"))

    if RESET_RE.match(text):
        return Intent("reset_session", text)
    if DB_OPEN_RE.match(text):
        return Intent("db_open", text)
    if DB_CLOSE_RE.match(text):
        return Intent("db_close", text)

    m_note = ADD_NOTE_RE.match(text)
    if m_note:
        return Intent("add_note", text, note_text=m_note.group("note").strip())

    if not ANY_FILENAME_RE.search(text):
        for regex, kind in ((DELETE_NOTE_RE, "delete_note"), (COMPLETE_NOTE_RE, "complete_note")):
            m_target = regex.match(text)
            if m_target:
                note_id, description = _note_target(m_target.group("rest"))
                return Intent(kind, text, note_id=note_id, note_text=description)

    if LIST_NOTES_RE.search(n) and not _is_doc_query(text, n):
        return Intent("list_notes", text)

    web = _web_target(text, n, registry)
    if web is not None:
        return web

    if RUN_VERB.search(n):
        task_id = registry.find_task(n)
        if task_id:
            return Intent("run_task", text, task_id=task_id)

    if QUICK_TIME_RE.search(text):
        return Intent("quick_reply", text, note_text="time")
    if QUICK_HELP_RE.match(text):
        return Intent("quick_reply", text, note_text="help")
    if QUICK_GREET_RE.match(text):
        return Intent("quick_reply", text, note_text="greet")
    if QUICK_THANKS_RE.match(text):
        return Intent("quick_reply", text, note_text="thanks")

    m_city_wx = CITY_WEATHER_RE.match(text)
    if m_city_wx and m_city_wx.group("city").lower() not in {"the", "what", "how", "today", "current", "check"}:
        return Intent("weather", text, city=m_city_wx.group("city").strip())

    m_weather = WEATHER_RE.search(text)
    if m_weather:
        raw_city = (m_weather.group("city") or "").strip(" .,?!")
        for suffix in (" today", " right now", " now", " tomorrow", " city"):
            if raw_city.lower().endswith(suffix):
                raw_city = raw_city[: -len(suffix)].strip()
        return Intent("weather", text, city=raw_city or settings.weather_city)

    if CROSS_PROJECT.search(n):
        return Intent("cross_project", text)

    is_doc = _is_doc_query(text, n)
    if is_doc:
        res = _resolve_with_followup(text, n, settings.desktop_root, last_project)
        if res.status != "none" or "project" in n or "desktop" in n:
            return Intent("read_doc", text, resolution=res)

    if GIT_STATUS_RE.search(n):
        res = _resolve_with_followup(text, n, settings.desktop_root, last_project)
        if res.status != "none" or "project" in n:
            return Intent("git_status", text, resolution=res)

    if OPEN_VERB.search(n):
        app_id = registry.find_app(n)
        wants_folder = bool(FOLDER_WORD.search(n))
        is_progress = bool(PROGRESS.search(n))
        res = _resolve_with_followup(text, n, settings.desktop_root, last_project)
        has_project = res is not None and res.status in {"found", "ambiguous"}
        if app_id and has_project and IN_WITH.search(n):
            return Intent("open_project_in", text, app_id=app_id, resolution=res)
        if wants_folder and has_project and not is_progress:
            return Intent("open_folder", text, resolution=res)
        if app_id:
            return Intent("open_app", text, app_id=app_id)
        if has_project and not is_progress:
            return Intent("open_folder", text, resolution=res)

    if ABOUT.search(n) and not PROGRESS.search(n):
        res = _resolve_with_followup(text, n, settings.desktop_root, last_project)
        # "what are my projects about" is a list question, not one project's README
        if res.status in {"found", "ambiguous"} or (res.status == "none" and re.search(r"\bproject\b", n)):
            return Intent("about", text, resolution=res)

    if LIST_PROJECTS.search(n):
        return Intent("list_projects", text)

    if PROGRESS.search(n):
        res = _resolve_with_followup(text, n, settings.desktop_root, last_project)
        if res.status != "none" or "project" in n or "desktop" in n:
            return Intent("progress", text, resolution=res)

    if USAGE.search(n):
        return Intent("usage", text)

    return Intent("chat", text)
