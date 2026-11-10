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
from .context_buffer import ConversationContext, get_context_buffer

# STT Leading Filler Stripper (Layer 1)
STT_FILLER_RE = re.compile(
    r"^(?:i\s+said|said|hey\s+nightmare|nightmare|please|can\s+you|could\s+you|would\s+you)\s+",
    re.I,
)


def strip_stt_fillers(text: str) -> str:
    """Iteratively strips conversational STT lead-in prefixes before regex evaluation."""
    s = text.strip()
    while True:
        m = STT_FILLER_RE.match(s)
        if not m:
            break
        s = s[m.end():].strip()
    return s


def normalize_concatenations_and_typos(text: str) -> str:
    """Splits joined command verbs and corrects speech-to-text typos."""
    s = re.sub(r"\bopenfile\b", "open file", text, flags=re.I)
    s = re.sub(r"\breadabout\b", "read about", s, flags=re.I)
    s = re.sub(r"\bwakeup\b", "wake up", s, flags=re.I)
    s = re.sub(r"\bprogres\b", "progress", s, flags=re.I)
    s = re.sub(r"\bpowwers\b", "powers", s, flags=re.I)
    s = re.sub(r"\b(?:open|visit|go\s+to|browse)\s+dribble\b", "open dribbble.com", s, flags=re.I)
    s = re.sub(r"\bdribble\b", "dribbble.com", s, flags=re.I)
    return s


def pre_normalize(text: str) -> str:
    """Runs STT leading filler stripping and concatenation/typo normalization."""
    s = text.strip()
    s = strip_stt_fillers(s)
    s = normalize_concatenations_and_typos(s)
    s = strip_stt_fillers(s)
    return s

RAW_CMD = re.compile(
    r"^\s*(?:nightmare[, ]+)?(?:run|execute)\s+(?:a\s+|the\s+)?(?:shell\s+)?command[: ]+(?P<cmd>.+?)(?:\s+(?:in|on)\s+(?:my\s+)?(?:terminal|shell|cmd))?\s*$",
    re.I,
)
# polite / wake-word lead-in allowed before a command: "hey nightmare, can you please ..."
LEAD = r"^\s*(?:(?:hey|ok|hi)\s+)?(?:nightmare[, ]+)?(?:please\s+)?(?:(?:can|could|would)\s+you\s+)?(?:please\s+)?"
ADD_NOTE_RE = re.compile(
    LEAD
    + r"(?:remind\s+me(?:\s+(?:later|again|tomorrow|today|tonight|soon))?(?:\s+(?:to|that|about|of|for|on))?"
    r"|(?:add|set|create|make|save)\s+(?:a\s+|an\s+)?(?:new\s+)?(?:reminder|note)(?:\s+(?:to|that|about|for|on))?"
    r"|note\s+(?:to\s+self|that|down)"
    r"|remember\s+to)"
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
# facts about the user or the world, kept until "forget ..." (reminders use "remind me to ...")
REMEMBER_RE = re.compile(
    LEAD + r"(?:remember\s+(?:that|this)|keep\s+in\s+mind(?:\s+that)?|(?:save|saved|store|keep)(?:\s+this)?\s+in\s+(?:your\s+)?memory|(?:if anyone (?:asks?|ask))|(?:next\s+time\s+i\s+ask\b.*?(?:you\s+(?:will\s+respond|must\s+reply)|respond)))[:,\s]+(?P<fact>.+?)(?:\s*[.,]?\s*got that\??)?\s*[.!]*$",
    re.I,
)
FORGET_RE = re.compile(
    LEAD + r"(?:forget|unremember)\s+(?:that\s+|about\s+)?(?P<fact>.+?)\s*[.!?]*$",
    re.I,
)
LIST_FACTS_RE = re.compile(
    r"\b(?:what\s+do\s+you\s+(?:remember|know)(?:\s+about\s+me)?|what\s+have\s+i\s+told\s+you"
    r"|(?:list|show|read|check)\s+(?:me\s+)?(?:all\s+)?(?:my\s+|your\s+)?(?:memories|facts)"
    r"|what\s+(?:are\s+)?(?:my\s+|your\s+)?memories)\b"
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
    + r"(?:database\s+(?:access\s+)?open|open\s+(?:the\s+)?database(?:\s+access)?|open\s+access\s+database|access\s+(?:the\s+)?database"
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
SETTINGS_OPEN_RE = re.compile(
    LEAD
    + r"(?:(?:open|show|unlock)\s+(?:me\s+)?(?:the\s+|my\s+)?(?:nightmare\s+)?settings(?:\s+(?:menu|dialog|panel|modal|page))?|settings\s+open"
    r"|(?:edit|change|manage)\s+(?:the\s+|my\s+)?(?:apps?|tasks?|allowlist|apps\.json)(?:\s+(?:and|&)\s+tasks?)?)\s*[.!?]*$",
    re.I,
)
SETTINGS_CLOSE_RE = re.compile(
    LEAD + r"(?:(?:close|exit|hide|lock)\s+(?:the\s+)?settings|settings\s+close)\s*[.!?]*$",
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
OPEN_HELPER_RE = re.compile(
    r"^\s*(?:(?:hey|ok|hi)\s+)?(?:nightmare[, ]+)?(?:please\s+)?(?:open|show|display|launch|view)\s+(?:the\s+)?(?:developer\s+)?helper(?:\s+function|\s+ui|\s+panel|\s+window)?\s*[.!?]*$|"
    r"^\s*(?:(?:hey|ok|hi)\s+)?(?:nightmare[, ]+)?developer\s+helper(?:\s+function|\s+ui|\s+panel|\s+window)?\s*[.!?]*$",
    re.I,
)
CLEARANCE_STATUS_RE = re.compile(
    LEAD
    + r"(?:what(?:'s|\s+is)\s+(?:my\s+)?(?:current\s+)?clearance(?:\s+level)?|"
    r"check\s+(?:my\s+)?clearance(?:\s+level)?|"
    r"current\s+clearance(?:\s+level)?|"
    r"what\s+clearance\s+level\s+am\s+i(?:\s+on)?|"
    r"what\s+level\s+am\s+i(?:\s+on)?)\s*[?.!]*$",
    re.I,
)
CLEAR_CACHE_RE = re.compile(
    r"^\s*(?:(?:hey|ok|hi)\s+)?(?:nightmare[, ]+)?(?:please\s+)?(?:clear|wipe|reset|refresh|flush)\s+(?:the\s+)?(?:summary\s+)?cache\s*[.!?]*$",
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
    r"^\s*(?:(?:hey|hi|hello|yo)\s+)?(?:nightmare[, ]+)?(?:hello|hi|hey|yo|good\s+(?:morning|afternoon|evening)|are\s+you\s+there|mic\s+check|testing|wake\s*up|wakeup)(?:\s+nightmare)?(?:\s+(?:wake\s*up|wakeup))*\s*[?.!]*$",
    re.I,
)
QUICK_THANKS_RE = re.compile(
    r"^\s*(?:thank\s+you|thanks)(?:\s+so\s+much|\s+a\s+lot)?(?:\s+nightmare)?\s*[?.!]*$",
    re.I,
)
QUICK_NAME_RE = re.compile(
    r"^\s*(?:(?:hey|ok|hi)\s+)?(?:nightmare[, ]+)?(?:what(?:'s|\s+is|\s+s)\s+your\s+name(?:\s+again)?"
    r"|who\s+are\s+you(?:\s+again)?|what\s+are\s+you|what\s+should\s+i\s+call\s+you)\s*[?.!]*$",
    re.I,
)
MODEL_IDENTITY_RE = re.compile(
    r"^\s*(?:(?:hey|ok|hi)\s+)?(?:nightmare[, ]+)?(?:(?:what|which)\s+(?:ai\s+|llm\s+)?models?\s+(?:powers?|runs?|trains?|is\s+powering|is\s+running)\s+(?:you|nightmare)|"
    r"what\s+(?:ai\s+|llm\s+)?model\s+are\s+you|"
    r"who\s+(?:powers?|trained?)\s+(?:you|nightmare))\s*[?.!]*$",
    re.I,
)
DEVELOPER_IDENTITY_RE = re.compile(
    r"^\s*(?:(?:hey|ok|hi|hello)\s+)?(?:nightmare[, ]+)?(?:(?:who|tell\s+me\s+about)\s+(?:is\s+)?(?:your|the)\s+(?:developer|creator|author|programmer|maker|builder)|"
    r"who\s+(?:developed|created|built|made)\s+(?:you|nightmare)|"
    r"who\s+is\s+adrian(?:\s+garcia)?|"
    r"tell\s+me\s+about\s+(?:your\s+developer|adrian))\s*[?.!]*$",
    re.I,
)
DEVELOPER_WHY_RE = re.compile(
    r"^\s*(?:(?:hey|ok|hi|hello)\s+)?(?:nightmare[, ]+)?(?:"
    r"why\s+(?:did\s+)?(?:adrian|he|your\s+developer)\s+(?:develop|make|build|create)\s+(?:you|nightmare)|"
    r"why\s+(?:you\s+are|are\s+you|were\s+you)\s+(?:develop|developed|made|built|created)|"
    r"why\s+were\s+you\s+(?:created|built|made|developed)|"
    r"what\s+(?:is|was)\s+the\s+purpose\s+of\s+(?:developing|creating|building)\s+(?:you|nightmare)|"
    r"why\s+did\s+adrian\s+create\s+you|"
    r"why\s+do\s+you\s+exist|"
    r"what\s+is\s+your\s+purpose"
    r")\s*[?.!]*$",
    re.I,
)
OPEN_PORTFOLIO_RE = re.compile(
    r"^\s*(?:(?:hey|ok|hi|hello)\s+)?(?:nightmare[, ]+)?(?:please\s+)?(?:"
    r"(?:open|visit|launch|show|go\s+to)\s+(?:that|the|this)\s+(?:link|url|website|web|page)|"
    r"(?:open|visit|launch|show|go\s+to)\s+(?:(?:your|the)\s+)?(?:developer(?:'s|s)?|adrian(?:'s)?)\s+portfolio(?:\s+(?:web|website|page|site))?|"
    r"(?:open|visit|launch|show|go\s+to)\s+(?:the\s+)?portfolio(?:\s+website|\s+web|\s+page)?|"
    r"open\s+(?:that\s+)?portfolio"
    r")\s*[?.!]*$",
    re.I,
)
OPEN_LAST_LINK_RE = re.compile(
    r"^\s*(?:(?:hey|ok|hi|hello)\s+)?(?:nightmare[, ]+)?(?:please\s+)?(?:"
    r"(?:open|visit|launch|show|go\s+to)\s+(?:that|the|this)\s+(?:link|url|website|web|page)"
    r")\s*[?.!]*$",
    re.I,
)
DEVELOPER_SKILLS_RE = re.compile(
    r"^\s*(?:(?:hey|ok|hi|hello)\s+)?(?:nightmare[, ]+)?(?:what\s+(?:are\s+)?(?:adrian(?:'s)?|your\s+developer(?:'s)?)\s+skills|"
    r"what\s+(?:tech\s+stack|technologies|tools)\s+does\s+(?:adrian|your\s+developer)\s+use)\s*[?.!]*$",
    re.I,
)
DEVELOPER_PROJECTS_RE = re.compile(
    r"^\s*(?:(?:hey|ok|hi|hello)\s+)?(?:nightmare[, ]+)?(?:what\s+(?:other\s+)?projects\s+did\s+(?:adrian|your\s+developer)\s+build|"
    r"what\s+(?:else\s+)?did\s+(?:adrian|your\s+developer)\s+(?:create|build|make))\s*[?.!]*$",
    re.I,
)
SYSTEM_TELEMETRY_RE = re.compile(
    r"^\s*(?:(?:hey|ok|hi|hello)\s+)?(?:nightmare[, ]+)?(?:please\s+)?(?:"
    r"how\s+much\s+(?:ram|memory|cpu)\s+(?:is\s+used|usage)|"
    r"(?:check\s+|show\s+|what\s+is\s+)?(?:system|laptop|pc|hardware)\s+(?:status|health|telemetry)|"
    r"how\s+is\s+(?:my|the)\s+(?:laptop|pc|system)\s+running|"
    r"system\s+(?:status|health)"
    r")\s*[?.!]*$",
    re.I,
)
SYSTEM_BATTERY_RE = re.compile(
    r"^\s*(?:(?:hey|ok|hi|hello)\s+)?(?:nightmare[, ]+)?(?:please\s+)?(?:"
    r"check\s+battery(?:\s+and\s+thermals)?|"
    r"(?:what\s+is\s+)?(?:my\s+)?battery\s+(?:status|percent|percentage|level)|"
    r"how\s+is\s+(?:my\s+)?battery|"
    r"is\s+ac\s+plugged\s+in|"
    r"battery\s+and\s+power"
    r")\s*[?.!]*$",
    re.I,
)
SYSTEM_PROCESSES_RE = re.compile(
    r"^\s*(?:(?:hey|ok|hi|hello)\s+)?(?:nightmare[, ]+)?(?:please\s+)?(?:"
    r"what\s+(?:processes|apps)\s+are\s+running|"
    r"which\s+(?:processes|apps)\s+are\s+running|"
    r"(?:what|list|show)\s+(?:running\s+)?processes|"
    r"what\s+is\s+using\s+(?:my\s+)?(?:memory|ram)|"
    r"which\s+(?:app|process)\s+is\s+eating\s+(?:ram|memory)|"
    r"(?:what\s+are\s+the\s+)?(?:top|heavy)\s+processes|"
    r"list\s+heavy\s+processes|"
    r"which\s+processes\s+are\s+heavy"
    r")\s*[?.!]*$",
    re.I,
)
DEFENSE_START_RE = re.compile(
    r"^\s*(?:(?:hey|ok|hi|hello)\s+)?(?:nightmare[, ]+)?(?:please\s+)?(?:"
    r"start\s+(?:the\s+)?(?:thesis\s+|presentation\s+|mock\s+)?defense(?:\s+rehearsal|\s+practice|\s+mode)?|"
    r"activate\s+defense\s+mode|"
    r"begin\s+(?:thesis\s+|defense\s+)rehearsal|"
    r"start\s+mock\s+defense|"
    r"start\s+defense\s+rehearsal"
    r")\s*[?.!]*$",
    re.I,
)
DEFENSE_STOP_RE = re.compile(
    r"^\s*(?:(?:hey|ok|hi|hello)\s+)?(?:nightmare[, ]+)?(?:please\s+)?(?:"
    r"(?:stop|end|finish|exit)\s+(?:the\s+)?(?:defense|rehearsal|mock\s+defense)(?:\s+mode)?|"
    r"stop\s+defense\s+mode|"
    r"end\s+defense\s+mode"
    r")\s*[?.!]*$",
    re.I,
)
DEFENSE_QUESTION_RE = re.compile(
    r"^\s*(?:(?:hey|ok|hi|hello)\s+)?(?:nightmare[, ]+)?(?:please\s+)?(?:"
    r"ask\s+(?:me\s+)?(?:a\s+)?(?:defense|panelist|panel|mock\s+defense)\s+question|"
    r"panelist\s+question|"
    r"ask\s+(?:me\s+)?(?:a\s+)?question\s+about\s+this\s+slide|"
    r"challenge\s+me(?:\s+on\s+this\s+slide)?|"
    r"panelist\s+interrogation"
    r")\s*[?.!]*$",
    re.I,
)
DEFENSE_STATUS_RE = re.compile(
    r"^\s*(?:(?:hey|ok|hi|hello)\s+)?(?:nightmare[, ]+)?(?:please\s+)?(?:"
    r"(?:check\s+)?defense\s+(?:timing|pace|status)|"
    r"how\s+is\s+my\s+defense\s+(?:timing|pace)|"
    r"rehearsal\s+(?:timing|pace|status)"
    r")\s*[?.!]*$",
    re.I,
)
# well-known desktop programs; if one is asked for and is not in apps.json, say so at once
# instead of spending ~12 s on the model just to be told no
UNLISTED_APP_NAMES = {
    "word": "Microsoft Word", "microsoft word": "Microsoft Word", "ms word": "Microsoft Word",
    "powerpoint": "PowerPoint", "microsoft powerpoint": "PowerPoint", "power point": "PowerPoint",
    "excel": "Excel", "microsoft excel": "Excel", "outlook": "Outlook", "teams": "Teams",
    "onenote": "OneNote", "photoshop": "Photoshop", "discord": "Discord", "zoom": "Zoom",
    "steam": "Steam", "vlc": "VLC", "obs": "OBS", "slack": "Slack", "telegram": "Telegram",
}
GIT_STATUS_RE = re.compile(
    r"\b(?:git\s+(?:status|branch)|what\s+branch\s+is|uncommitted\s+changes)\b",
    re.I,
)
RERUN_TASK_RE = re.compile(
    r"^\s*(?:(?:hey|ok|hi)\s+)?(?:nightmare[, ]+)?(?:please\s+)?"
    r"(?:run\s+(?:it|that)\s+again|run\s+again|re-?run|retry\s+(?:last\s+task|it|that))\s*[.!?]*$",
    re.I,
)
WORKSPACE_CHANGES_RE = re.compile(
    r"\b("
    r"what\s+changed\s+(?:since\s+(?:yesterday|last\s+week)|today|recently)|"
    r"changes\s+since\s+(?:yesterday|today|last\s+week)|"
    r"recent\s+changes(?:\s+across\s+projects)?|"
    r"what\s+did\s+i\s+(?:change|commit|work\s+on)\s+(?:yesterday|today|recently)"
    r")\b",
    re.I,
)
WORK_PRIORITIES_RE = re.compile(
    r"\b("
    r"what\s+should\s+i\s+(?:work\s+on|do(?:\s+next)?|focus\s+on)|"
    r"which\s+project\s+should\s+i\s+work\s+on|"
    r"what\s+project\s+(?:should\s+i|needs)\s+work|"
    r"where\s+should\s+i\s+(?:start|focus)|"
    r"(?:work|project)\s+priorit(?:y|ies)"
    r")\b",
    re.I,
)
WORKSPACE_BRIEFING_RE = re.compile(
    r"\b("
    r"(?:workspace|daily|morning)\s+(?:briefing|overview|summary|status)|"
    r"(?:give\s+me\s+a\s+|tell\s+me\s+the\s+)?briefing|"
    r"workspace\s+health"
    r")\b",
    re.I,
)
DEV_TASK_KIND_RE = re.compile(
    r"\b(?P<kind>npm\s+tests?|pytest|tests?|build|dev|lint|preview|typecheck|type-check)\b",
    re.I,
)
RUN_VERB = re.compile(r"\b(start|run|launch|execute|kick off|fire up|spin up)\b")
OPEN_VERB = re.compile(r"\b(open|launch|start|run|fire up)\b")
FOLDER_WORD = re.compile(r"\b(folder|directory|explorer|file explorer)\b")
IN_WITH = re.compile(r"\b(in|with|using)\b")
LIST_PROJECTS = re.compile(
    r"\b(list|show|which|what|how\s+many|count)\b.*\bprojects\b|\bprojects\s+on\s+(?:my\s+)?desktop\b"
    r"|\b(?:how\s+many|count)\s+(?:(?:my|the)\s+)?project\b"
)
VOICE_SETTINGS_RE = re.compile(
    LEAD
    + r"(?:(?:switch|change|set|use)\s+(?:the\s+)?(?:voice\s+to|to\s+)?(?P<g1>male|female)(?:\s+voice)?|(?P<g2>male|female)\s+voice)\s*[.!?]*$",
    re.I,
)
CONVERSATION_HISTORY_RE = re.compile(
    r"\b(?:(?:what\s+did\s+we|what\s+were\s+we|what\s+was\s+our|what\s+have\s+we)\s+(?:discuss(?:ed)?|talk(?:ed)?\s+about|conversation(?:\s+was)?)|"
    r"earlier\s+what\s+(?:we\s+have\s+discussed|did\s+we\s+discuss)|"
    r"what\s+did\s+i\s+(?:ask|say)(?:\s+earlier)?|"
    r"recap\s+(?:our\s+)?conversation|previous\s+conversation)\b",
    re.I,
)
SEARCH_PROJECTS_RE = re.compile(
    r"^\s*(?:(?:hey|ok|hi)\s+)?(?:nightmare[, ]+)?(?:please\s+)?"
    r"(?:search\s+(?:all\s+)?(?:projects?|docs?|code|repos?)\s+(?:for|about)|"
    r"find\s+in\s+projects?|"
    r"search\s+project\s+(?:docs|documentation|notes)\s+(?:for|about)?)\s+"
    r"(?P<query>.+?)\s*[.!?]*$",
    re.I,
)
FIND_OPEN_FILE_RE = re.compile(
    r"^\s*(?:(?:hey|ok|hi)\s+)?(?:nightmare[, ]+)?(?:please\s+)?"
    r"(?:"
    r"find\s+(?:the\s+|a\s+|an\s+)?(?:file|doc|document|docs|presentation|spreadsheet)?(?:\s+related\s+to|\s+about)?\s+(?P<q1>.+?)\s+(?:and\s+)?open\s+(?:it\s+)?(?:(?:in|on|with|using)\s+(?P<app1>[a-zA-Z\s]+?))?|"
    r"find\s+(?:the\s+|a\s+|an\s+)?(?:file|doc|document|docs|presentation|spreadsheet)(?:\s+related\s+to|\s+about)?\s+(?P<q2>.+?)|"
    r"(?:open\s*file|open\s+(?:the\s+|a\s+|an\s+)?(?:file|doc|document|docs|presentation|spreadsheet)(?:\s+related\s+to|\s+about)?)\s+(?P<q3>.+?)(?:\s+(?:(?:and\s+)?open\s+(?:it\s+)?(?:in|on|with|using)|(?:in|on|with|using))\s+(?P<app3>[a-zA-Z\s]+?))?|"
    r"open\s+(?P<q4>[a-zA-Z0-9_\-.\s]+?)\s+(?:in|on|with|using)\s+(?P<app4>word|powerpoint|excel|notepad|sheets|slides|acrobat|wordpad|doc|docx|ppt|pptx|xls|xlsx|pdf)|"
    r"open\s+(?P<q5>[a-zA-Z0-9_\-.\s]+?)\s+(?P<ext5>ppt|pptx|doc|docx|xls|xlsx|pdf|txt|md)|"
    r"open\s+(?P<q6>[a-zA-Z0-9_\-.\s]+?\.(?:pptx?|docx?|xlsx?|pdf|txt|md))|"
    r"open\s+(?:the\s+|a\s+|an\s+)?(?P<q7>[a-zA-Z0-9_\-.\s]*?\b(?:checklist|document|doc|paper|chapter|report|presentation|spreadsheet|notes|draft|outline|lesson|slides?|lecture|syllabus|letter|interview|attendance|proposal|manuscript|timeline|summary|evidence|approval)\b[a-zA-Z0-9_\-.\s]*)|"
    r"(?:list|show|find)\s+(?:all\s+)?(?:the\s+)?files?\s+(?:related\s+to|about)\s+(?P<q8>.+?)|"
    r"(?:do\s+i\s+have\s+any|what\s+about\s+(?:the\s+)?)\s*(?:files?|documents?|docs?)(?:\s+related\s+to|\s+about)\s+(?P<q9>.+?)|"
    r"create\s+(?:a\s+|an\s+)?(?P<q10>.+?)\s+(?:in|on|with|using)\s+(?P<app10>word|powerpoint|excel|notepad|sheets|slides|acrobat|wordpad|doc|docx|ppt|pptx|xls|xlsx|pdf)|"
    r"open\s+(?:the\s+)?(?P<q11>sana\s+ma\s+gets\s+mo\s+na\s+ako|el\s+filibusterismo|filibusterismo|inspiro\s+coc|lcro|readme)"
    r")\s*[.!?]*$",
    re.I,
)
PPT_OPEN_SLIDE_RE = re.compile(
    LEAD
    + r"(?:(?:no|wait|actually)[,\s]+.*?[.!?]\s*)?"
    r"(?:"
    r"(?:find\s+and\s+open|open|launch)\s+(?:the\s+|a\s+|an\s+)?(?P<q1>.+?)\s+(?:ppt|pptx|presentation|slides?)(?:\s+(?:to|in)\s+powerpoint)?\s+(?:and\s+)?(?:show|display|go\s+to|move\s+to|jump\s+to)?\s*(?:the\s+)?slide\s+(?P<s1>\d+|[a-zA-Z]+)|"
    r"(?:find\s+and\s+open|open|launch)\s+(?:the\s+|a\s+|an\s+)?(?P<q2>.+?)(?:\s+(?:presentation|slides?|ppt|pptx))?(?:\s+(?:in|on|with|using)\s+powerpoint)?\s+(?:(?:and\s+)?(?:move\s+to|go\s+to|jump\s+to|show|display)\s+|(?:at|on|to)\s+)(?:the\s+)?slide\s+(?P<s2>\d+|[a-zA-Z]+)|"
    r"(?:find\s+and\s+open|open|launch)\s+(?:the\s+|a\s+|an\s+)?(?P<q3>.+?)\s+(?:in|on|with|using)\s+powerpoint\s+(?:(?:at|on)\s+|(?:and\s+)?(?:show|display|go\s+to|move\s+to|jump\s+to)\s+)?(?:the\s+)?slide\s+(?P<s3>\d+|[a-zA-Z]+)|"
    r"(?:find\s+and\s+open|open|launch)\s+(?:the\s+|a\s+|an\s+)?(?P<q4>.+?)\s+(?:ppt|pptx|presentation|slides?)(?:\s+(?:to|in)\s+powerpoint)?\s+(?:and\s+)?(?:show|display|go\s+to|move\s+to|jump\s+to)\s+(?:the\s+)?slide\s+(?:about|on|regarding)\s+(?P<t4>.+?)"
    r")\s*[.!?]*$",
    re.I,
)
PPT_CONTROL_RE = re.compile(
    LEAD
    + r"(?:"
    r"(?:go\s+to|jump\s+to|switch\s+to|move\s+to|show|display)\s+(?:the\s+)?(?:next\s+|previous\s+)?slide\s+(?P<s1>\d+|[a-zA-Z]+)|"
    r"slide\s+(?P<s2>\d+)|"
    r"(?P<next>next\s+slide|advance\s+slide)|"
    r"(?P<prev>previous\s+slide|prev\s+slide|back\s+(?:one\s+)?slide)|"
    r"(?P<start>present\s+(?:it|this|the\s+presentation|slideshow)?|start\s+(?:the\s+)?(?:presentation|slideshow)|run\s+(?:the\s+)?slideshow)|"
    r"(?:show|display|go\s+to|jump\s+to|find)\s+(?:the\s+)?slide\s+(?:about|on|regarding)\s+(?P<topic>.+?)"
    r")\s*[.!?]*$",
    re.I,
)
SYSTEM_COMMAND_RE = re.compile(
    LEAD
    + r"(?:"
    r"(?P<restart_nightmare>rerun\s+yourself|restart\s+nightmare|reboot\s+nightmare)|"
    r"(?P<restart_pc>restart\s+(?:my\s+|the\s+)?pc|reboot\s+(?:my\s+|the\s+)?(?:pc|computer|system|machine))|"
    r"(?P<shutdown_pc>shut\s*down\s+(?:my\s+|the\s+)?(?:pc|computer|system|machine)|power\s+off\s+(?:my\s+|the\s+)?(?:pc|computer|system))|"
    r"(?P<cancel_shutdown>cancel\s+(?:the\s+)?shut\s*down|abort\s+(?:the\s+)?shut\s*down)"
    r")\s*[.!?]*$",
    re.I,
)
TEAM_PROGRESS_RE = re.compile(
    LEAD
    + r"(?:"
    r"(?:show|open|check|display|view)\s+(?:the\s+)?(?:(?:team(?:\s+\d+|\s+[a-z0-9_-]+)?\s+)?(?:timeline\s+tracker|timeline|progress|team\s+progress|quota|tracker))|"
    r"open\s+(?:the\s+)?(?:citizengraph\s+)?timeline(?:\s+tracker)?|"
    r"(?:citizengraph\s+)?timeline\s+tracker|"
    r"(?:show\s+)?citizengraph\s+timeline|"
    r"team\s+progress(?:\s+tracker)?|"
    r"check\s+(?:the\s+)?team(?:\s+\d+|\s+[a-z0-9_-]+)?\s+progress"
    r")(?:\s+(?:for|of|on)?\s*(?P<target>team\s*\d+|team\s*[a-z0-9_-]+))?\s*[.!?]*$",
    re.I,
)
TIMELINE_DIFF_RE = re.compile(
    LEAD
    + r"(?:"
    r"(?:what\s+(?:did\s+(?:my\s+)?team\s+update|changed?|change|is\s+different)\s+(?:in|on)\s+(?:the\s+)?(?:citizengraph\s+)?timeline(?:\s+from\s+(?:the\s+)?(?:gdrive|google\s+drive))?)|"
    r"(?:what\s+change(?:d)?\s+in\s+the\s+(?:citizengraph\s+)?timeline(?:\s+from\s+(?:the\s+)?(?:gdrive|google\s+drive))?)|"
    r"(?:compare\s+(?:the\s+)?(?:citizengraph\s+)?timeline(?:\s+with|\s+to|\s+against)\s+(?:the\s+)?(?:gdrive|google\s+drive))|"
    r"(?:check\s+(?:the\s+)?(?:gdrive|google\s+drive)\s+timeline\s+updates?)|"
    r"(?:check\s+(?:the\s+)?(?:citizengraph\s+)?timeline\s+diff)|"
    r"(?:what\s+did\s+(?:my\s+)?team\s+update\s+in\s+the\s+(?:citizengraph\s+)?timeline)"
    r")\s*[.!?]*$",
    re.I,
)
APPROVE_EMAIL_RE = re.compile(
    LEAD
    + r"(?:"
    r"approve\s+(?:the\s+)?(?:team\s+)?(?:reminder\s+)?email(?:\s+reminder)?|"
    r"send\s+(?:the\s+)?(?:team\s+)?(?:reminder\s+)?email(?:\s+reminder)?|"
    r"confirm\s+(?:the\s+)?(?:team\s+)?email"
    r")\s*[.!?]*$",
    re.I,
)
EMAIL_REPORT_RE = re.compile(
    LEAD
    + r"(?:"
    r"(?:(?:check|read|show|view|open|inspect|tell\s+me\s+about)\s+(?:all\s+)?(?:my\s+|the\s+)?(?:priority\s+)?(?:inbox|emails?))|"
    r"(?:(?:check|read|show|view|open|inspect)\s+(?:all\s+)?(?:my\s+|the\s+)?priority\s+inbox)|"
    r"(?:(?:do\s+i\s+have|have\s+i\s+got|are\s+there)\s+(?:any\s+)?(?:new|unread|pending|priority)\s+emails?)|"
    r"(?:(?:do\s+i\s+have|have\s+i\s+got)\s+(?:any\s+)?emails?)|"
    r"(?:what(?:'s|\s+is)\s+in\s+(?:my|the)\s+(?:priority\s+)?(?:inbox|emails?))|"
    r"(?:any\s+(?:new|unread|pending|priority)\s+emails?)|"
    r"(?:(?:priority\s+)?email\s+report)|"
    r"(?:inbox\s+report)"
    r")\s*[.!?]*$",
    re.I,
)
CALENDAR_QUERY_RE = re.compile(
    LEAD
    + r"(?:"
    r"(?:(?:do\s+i\s+have|have\s+i\s+got|are\s+there)\s+(?:any\s+)?(?:meetings?|events?|appointments?|calls?)(?:\s+(?P<timeframe1>this\s+week|today|tomorrow|this\s+month|upcoming))?)|"
    r"(?:what\s+(?:meetings?|events?|appointments?|calls?)\s+do\s+i\s+have(?:\s+(?P<timeframe2>this\s+week|today|tomorrow|this\s+month|upcoming))?)|"
    r"(?:(?:check|show|list|read|view|get|tell\s+me\s+about)\s+(?:my\s+)?(?:meetings?|calendar(?:\s+events?)?|schedule)(?:\s+(?:for\s+)?(?P<timeframe3>this\s+week|today|tomorrow|this\s+month|upcoming))?)|"
    r"(?:(?:any\s+)?(?:meetings?|events?)\s+(?P<timeframe4>this\s+week|today|tomorrow))|"
    r"(?:what(?:'s|\s+is|\s+are)\s+(?:on|in)\s+(?:my\s+)?(?:calendar|schedule)(?:\s+(?:for\s+)?(?P<timeframe5>this\s+week|today|tomorrow))?)|"
    r"(?:check\s+(?:my\s+)?calendar)|"
    r"(?:calendar\s+events?)"
    r")\s*[?.!]*$",
    re.I,
)
CALENDAR_CREATE_RE = re.compile(
    LEAD
    + r"(?:"
    r"(?:(?:create|schedule|add|set(?:\s+up)?)\s+(?:a\s+|an\s+)?(?:new\s+)?meeting(?:\s+scheduled|\s+for)?\s+(?P<details1>.+))|"
    r"(?:(?:create|schedule|add|set(?:\s+up)?)\s+(?:a\s+|an\s+)?(?:new\s+)?calendar\s+event(?:\s+for)?\s+(?P<details2>.+))"
    r")\s*[.!?]*$",
    re.I,
)
MEASURABLE_TASK_UPDATE_RE = re.compile(
    LEAD
    + r"(?:"
    r"(?:(?:update|set|change|record|log)(?:\s+my)?\s+(?:(?P<target_hint1>\d+)\s+)?(?P<title1>.+?)\s+progress\s+(?:to|at|=)\s+(?P<value1>\d+))|"
    r"(?:(?:update|set|change|record|log)\s+(?:my\s+)?progress\s+(?:on|for|of)\s+(?:(?P<target_hint2>\d+)\s+)?(?P<title2>.+?)\s+(?:to|at|=)\s+(?P<value2>\d+))|"
    r"(?:(?:update|set)(?:\s+my)?\s+(?:(?P<target_hint3>\d+)\s+)?(?P<title3>[a-zA-Z0-9_\-\s]+?)\s+to\s+(?P<value3>\d+)\s+progress)"
    r")\s*[.!?]*$",
    re.I,
)
MEASURABLE_TASK_CREATE_RE = re.compile(
    LEAD
    + r"(?:"
    r"(?:(?:create|add|set(?:\s+up)?|track)\s+(?:a\s+|an\s+)?(?:new\s+)?(?:measurable\s+)?task(?:\s+to)?\s+(?:(?P<verb1>write|read|review|finish|complete|track|contact|call|reach|inform|message|email|acquire|acquire\s+or\s+finish)\s+)?(?:a\s+|an\s+|my\s+)?(?P<target1>\d+)\s*(?P<unit1>(?:pages?|sources?|chapters?|clients?|items?|articles?|words?|papers?)\b)?(?:\s+(?:of\s+)?(?P<title1>[a-zA-Z0-9_\-\s]+))?)|"
    r"(?:(?P<verb2>write|read|review|finish|complete|track|contact|call|reach|inform|message|email|acquire|acquire\s+or\s+finish)\s+(?:a\s+|an\s+|my\s+)?(?P<target2>\d+)\s*(?P<unit2>(?:pages?|sources?|chapters?|clients?|items?|articles?|words?|papers?)\b)?(?:\s+(?:of\s+)?(?P<title2>[a-zA-Z0-9_\-\s]+))?)"
    r")\s*[.!?]*$",
    re.I,
)
MEASURABLE_TASK_LIST_RE = re.compile(
    LEAD
    + r"(?:"
    r"(?:(?:list|show|check|view|what\s+is\s+the|what\s+are)\s+(?:all\s+)?(?:my\s+)?(?:measurable\s+)?(?:tasks?|to-?dos?))|"
    r"(?:(?:have\s+(?:i\s+got\s+)?|do\s+i\s+have\s+)?any\s+(?:measurable\s+)?(?:tasks?|to-?dos?))|"
    r"(?:open\s+(?:my\s+)?(?:measurable\s+)?(?:tasks?|to-?dos?))|"
    r"(?:measurable\s+tasks?)"
    r")\s*[?.!]*$",
    re.I,
)
OPEN_TIMELINE_EXCEL_RE = re.compile(
    LEAD
    + r"(?:open|launch)\s+(?:the\s+)?(?:citizengraph\s+)?(?:thesis\s+)?(?:team\s+)?timeline(?:\s+tracker)?\s+(?:in|on|with|using)\s+excel\s*[.!?]*$",
    re.I,
)
GITHUB_CHECK_RE = re.compile(
    r"\b("
    r"(?:force\s+)?refresh\s+(?:my\s+)?github(?:\s+(?:repos|repositories|status|cache))?|"
    r"force\s+refresh\s+github|"
    r"check\s+(?:my\s+)?github(?:\s+repositories|\s+repos)?"
    r"(?:\s+for\s+(?:commits|pull\s+requests|merge\s+conflicts|conflicts|updates)(?:\s*(?:and|or|,|/)\s*(?:commits|pull\s+requests|merge\s+conflicts|conflicts|updates))*)?|"
    r"github\s+(?:repo\s+)?check(?:s)?|"
    r"github\s+status|"
    r"check\s+(?:for\s+)?(?:merge\s+)?conflicts(?:\s+in\s+repos)?|"
    r"check\s+(?:my\s+)?pull\s+requests"
    r")\b",
    re.I,
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
    r"progress|status|handoff|hand off|hand\s+of|handocks?|left off|leave off|where am i|update on|catch me up|"
    r"summary|summarize|summarise|check on|check project|read handoff|what did i do on|"
    r"latest (?:on|of|for)|latest\s+update|last\s+update|how (?:is|s) .+ going|what(?: is| s) going on with|"
    r"what(?: is| s) next|next (?:tasks?|steps?)|(?:to )?do next"
    r")\b"
)
# "what is citizengraph all about" -> the project's README, not its progress log
ABOUT = re.compile(
    r"\b("
    r"what\s+about\s+(?:the\s+|my\s+)?(?:project\s+)?\S+|"
    r"what(?: is| s| was)\b.*\babout|tell me (?:all )?about|what does .+ do|"
    r"describe|explain (?:the |my )?(?:project )?\w+|what kind of (?:project|app|system) is|"
    r"what(?: is| s) (?:the |my )?(?:project )?\S+ (?:project|app|system)$"
    r")\b"
)
USAGE = re.compile(
    r"^\s*(?:(?:hey|ok|hi)\s+)?(?:nightmare[, ]+)?(?:please\s+)?(?:check\s+|show\s+|what\s+(?:is|are)\s+|tell\s+me\s+)?(?:my\s+)?(?:(?:model|llm|api|call|request)\s+)*(?:usage|quota)\s*[?.!]*$|"
    r"^\s*(?:(?:hey|ok|hi)\s+)?(?:nightmare[, ]+)?how\s+many\s+(?:model\s+|api\s+)?(?:calls|requests|prompts)\s*(?:did\s+you\s+make\s*)?(?:today)?\s*[?.!]*$",
    re.I,
)
FOLLOWUP_REF = re.compile(r"\b(it|its|that|this|there|the project|that project|this project|that folder|the folder)\b")

# Websites open as a new tab in the browser showing Nightmare (the frontend does window.open),
# never by launching a program. URLs come only from these fixed templates; the spoken search
# text is URL-encoded into {q}.
WEB_SITES = {
    "youtube": ("YouTube", "https://www.youtube.com", "https://www.youtube.com/results?search_query={q}", ("you tube", "yt")),
    "youtube music": ("YouTube Music", "https://music.youtube.com", "https://music.youtube.com/search?q={q}", ("yt music", "you tube music", "youtubemusic", "music youtube", "music youtube com", "ytm")),
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
    "dribbble": ("Dribbble", "https://dribbble.com", None, ("dribble", "dribbble", "dribbble.com")),
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
    # remember_fact | forget_fact | list_facts |
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
    voice_gender: str | None = None
    slide: int | None = None
    action: str | None = None
    history: tuple = ()  # recent (user, reply) turns, filled in by the orchestrator for chat
    current_progress: int | None = None
    target_progress: int | None = None
    unit: str | None = None
    force_refresh: bool = False
    router_path: str = "fast_path"
    confidence_margin: float = 1.0
    options: list[str] | None = None
    ppt_path: str | None = None


def describe_intent(intent: Intent) -> str:
    if intent.kind == "calendar_query":
        return f"calendar_query → {intent.query or 'this_week'}"
    if intent.kind == "measurable_task":
        return f"measurable_task → {intent.action} {intent.query or ''} ({intent.current_progress}/{intent.target_progress or '?'})".strip()
    if intent.kind == "ppt_open_slide":
        return f"ppt_open_slide → {intent.query} (slide {intent.slide or 1})"
    if intent.kind == "ppt_control":
        return f"ppt_control → {intent.action} {intent.slide or ''}".strip()
    if intent.kind == "system_authority":
        return f"system_authority → {intent.action}"
    if intent.kind == "team_progress":
        return f"team_progress → {intent.query or 'all teams'}"
    if intent.kind == "email_report":
        return "email_report"
    if intent.kind == "approve_email":
        return "approve_email"
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
    if intent.kind == "run_dev_task":
        proj = intent.resolution.matches[0][0].name if intent.resolution and intent.resolution.matches else "?"
        return f"run_dev_task → {intent.task_id} in {proj}"
    if intent.kind == "rerun_task":
        return "rerun_task"
    if intent.kind == "workspace_changes":
        return "workspace_changes"
    if intent.kind == "work_priorities":
        return "work_priorities"
    if intent.kind == "workspace_briefing":
        return "workspace_briefing"
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
    if intent.kind in {"remember_fact", "forget_fact", "list_facts"}:
        return intent.kind
    if intent.kind in {"complete_note", "delete_note"}:
        target = f"#{intent.note_id}" if intent.note_id is not None else f"“{intent.note_text or '?'}”"
        return f"{intent.kind} → {target}"
    if intent.kind in {"db_open", "db_close", "settings_open", "settings_close", "reset_session", "clear_cache"}:
        return intent.kind
    if intent.kind == "open_url":
        return f"open_url → {intent.site}" + (f" search “{intent.query}”" if intent.query else "")
    if intent.kind == "quick_reply":
        return f"quick_reply → {intent.note_text or 'instant'}"
    if intent.kind == "usage":
        return "usage"
    if intent.kind == "voice_settings":
        return f"voice_settings → {intent.voice_gender or 'toggle'}"
    if intent.kind == "conversation_history":
        return "conversation_history"
    if intent.kind == "search_projects":
        return f"search_projects → {intent.query or 'all'}"
    if intent.kind == "clearance_status":
        return "clearance_status"
    if intent.kind == "open_file":
        detail = intent.query or "?"
        if intent.note_text:
            detail += f" ({intent.note_text})"
        return f"open_file → {detail}"
    if intent.kind == "open_team_excel":
        return "open_team_excel → Microsoft Excel"
    if intent.kind == "github_check":
        return "github_check → tracked repos"
    if intent.kind == "developer_info":
        return "developer_info → Adrian S. Garcia"
    if intent.kind == "developer_why":
        return "developer_why → origin story"
    if intent.kind == "open_portfolio":
        target = intent.url or "Adrian's Portfolio"
        return f"open_portfolio → {target}"
    if intent.kind == "developer_skills":
        return "developer_skills → Adrian's stack"
    if intent.kind == "developer_projects":
        return "developer_projects → Adrian's projects"
    if intent.kind == "system_telemetry":
        return "system_telemetry → CPU/RAM/Battery"
    if intent.kind == "system_battery":
        return "system_battery → battery status"
    if intent.kind == "system_processes":
        return "system_processes → top processes"
    if intent.kind == "defense_start":
        return "defense_start → Thesis Rehearsal"
    if intent.kind == "defense_stop":
        return "defense_stop → End Rehearsal"
    if intent.kind == "defense_question":
        return "defense_question → Mock Panelist"
    if intent.kind == "defense_status":
        return "defense_status → Rehearsal Pacing"
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


def _match_open_file(text: str, n: str) -> Intent | None:
    # 1. Exact FIND_OPEN_FILE_RE
    m_open_file = FIND_OPEN_FILE_RE.match(text)
    if m_open_file:
        q = (
            m_open_file.group("q1")
            or m_open_file.group("q2")
            or m_open_file.group("q3")
            or m_open_file.group("q4")
            or m_open_file.group("q5")
            or m_open_file.group("q6")
            or m_open_file.group("q7")
            or m_open_file.group("q8")
            or m_open_file.group("q9")
            or m_open_file.group("q10")
            or m_open_file.group("q11")
            or ""
        ).strip()
        q = re.sub(r"\s+(?:and\s+)?open(?:\s+it)?\s*$", "", q, flags=re.I).strip()
        app_or_ext = (
            m_open_file.group("app1")
            or m_open_file.group("app3")
            or m_open_file.group("app4")
            or m_open_file.group("ext5")
            or m_open_file.group("app10")
            or ""
        ).strip()

        # Check for parenthesized app hint, e.g. "LCRO Interview checklist.docx (word)"
        m_paren = re.search(r"\s*\(\s*([a-zA-Z]+)\s*\)\s*$", q)
        if m_paren:
            paren_val = m_paren.group(1).lower()
            if paren_val in {"word", "excel", "powerpoint", "ppt", "doc", "docx", "pdf", "notepad", "sheets", "slides"}:
                q = q[: m_paren.start()].strip()
                if not app_or_ext:
                    app_or_ext = paren_val

        return Intent("open_file", text, query=q, note_text=app_or_ext or None)

    # 2. Pattern: <query> and open it in/on/with <app>
    # e.g. "comments and find citizen graph chapter 1 docs and open it on word"
    # or "ilcro interview checklist and open it in word"
    m_and_open = re.search(
        r"(?:(?:and\s+)?open\s+(?:it\s+)?(?:in|on|with|using)\s+(?P<app>[a-zA-Z\s]+?))\s*[.!?]*$",
        text,
        re.I,
    )
    if m_and_open:
        raw_app = m_and_open.group("app").strip().lower()
        app_tokens = set(raw_app.split())
        is_file_app = bool(
            app_tokens
            & {
                "word",
                "powerpoint",
                "excel",
                "notepad",
                "sheets",
                "slides",
                "acrobat",
                "wordpad",
                "reader",
                "ppt",
                "pptx",
                "doc",
                "docx",
                "xls",
                "xlsx",
                "pdf",
            }
        )
        if is_file_app:
            query_part = text[: m_and_open.start()].strip()
            clean_q = re.sub(
                r"^\s*(?:(?:hey|ok|hi)\s+)?(?:nightmare[, ]+)?(?:please\s+)?",
                "",
                query_part,
                flags=re.I,
            )
            clean_q = re.sub(
                r"^\s*(?:comments?\s+(?:and\s+)?|so\s+|well\s+|can\s+you\s+|could\s+you\s+)",
                "",
                clean_q,
                flags=re.I,
            )
            clean_q = re.sub(
                r"^\s*(?:find|search\s+for|locate|look\s+up|get)\s+(?:the\s+|a\s+|an\s+)?(?:file|doc|document|presentation|spreadsheet)?(?:\s+related\s+to|\s+about)?\s*",
                "",
                clean_q,
                flags=re.I,
            )
            clean_q = clean_q.strip(" .,?!")
            if clean_q:
                return Intent("open_file", text, query=clean_q, note_text=raw_app)

    # 3. Pattern: open <query> in/on/with <app>
    m_open_in = re.match(
        r"^\s*(?:(?:hey|ok|hi)\s+)?(?:nightmare[, ]+)?(?:please\s+)?"
        r"(?:(?:comments?\s+(?:and\s+)?|so\s+|well\s+|can\s+you\s+|could\s+you\s+))?"
        r"open\s+(?:the\s+|a\s+|an\s+)?(?:file|doc|document|presentation|spreadsheet)?(?:\s+related\s+to|\s+about)?\s*"
        r"(?P<q>.+?)\s+(?:in|on|with|using)\s+(?P<app>[a-zA-Z\s]+?)\s*[.!?]*$",
        text,
        re.I,
    )
    if m_open_in:
        raw_app = m_open_in.group("app").strip().lower()
        app_tokens = set(raw_app.split())
        is_file_app = bool(
            app_tokens
            & {
                "word",
                "powerpoint",
                "excel",
                "notepad",
                "sheets",
                "slides",
                "acrobat",
                "wordpad",
                "reader",
                "ppt",
                "pptx",
                "doc",
                "docx",
                "xls",
                "xlsx",
                "pdf",
            }
        )
        if is_file_app:
            q = m_open_in.group("q").strip()
            return Intent("open_file", text, query=q, note_text=raw_app)

    # 4. Pattern: open <query> (ppt|pptx|doc|docx|xls|xlsx|pdf|txt|md)
    m_ext = re.match(
        r"^\s*(?:(?:hey|ok|hi)\s+)?(?:nightmare[, ]+)?(?:please\s+)?"
        r"open\s+(?:the\s+|a\s+|an\s+)?(?:file|doc|document)?\s*"
        r"(?P<q>.+?)\s+(?P<ext>pptx?|docx?|xlsx?|pdf|txt|md)\s*[.!?]*$",
        text,
        re.I,
    )
    if m_ext:
        q = m_ext.group("q").strip()
        ext = m_ext.group("ext").strip().lower()
        return Intent("open_file", text, query=q, note_text=ext)

    # 5. Phrasing: "it is a lesson 7 elfilibusterismo" or "what about lesson 7"
    if re.search(r"\b(?:lesson\s*7\b.*?(?:el\s*filibusterismo|filibusterismo)?|el\s*filibusterismo|filibusterismo)\b", text, re.I):
        if "defense" not in text.lower():
            return Intent("open_file", text, query="GE9-Lesson7-El-Filibusterismo-Presentation")

    # 6. Loose "open <filename>" when <filename> is not a command/app/clearance
    m_loose_open = re.match(r"^\s*(?:open|launch)\s+(?:the\s+)?(?P<q>[a-zA-Z0-9_\-\s.]+?)\s*[.!?]*$", text, re.I)
    if m_loose_open:
        cand = m_loose_open.group("q").strip()
        low_cand = cand.lower()
        if not any(w in low_cand for w in ("folder", "directory", "project", "explorer", "settings", "database", "menu", "word", "excel", "powerpoint", "vs code", "chrome", "notepad")):
            if "." in cand or any(w in low_cand for w in ("lesson", "sana", "inspiro", "lcro", "citizengraph", "thesis", "presentation", "checklist", "doc", "pdf", "report", "paper", "slides", "chapter", "spreadsheet", "attendance", "notes", "interview")):
                return Intent("open_file", text, query=cand)

    return None


def _parse_slide_number(val: str | None) -> int | None:
    if not val:
        return None
    clean = val.strip().lower()
    if clean.isdigit():
        return int(clean)
    if clean in NUMBER_WORDS:
        return NUMBER_WORDS[clean]
    return None


def _match_system_authority(text: str) -> Intent | None:
    m = SYSTEM_COMMAND_RE.match(text)
    if not m:
        return None
    if m.group("restart_nightmare"):
        return Intent("system_authority", text, action="restart_nightmare")
    if m.group("restart_pc"):
        return Intent("system_authority", text, action="restart_pc")
    if m.group("shutdown_pc"):
        return Intent("system_authority", text, action="shutdown_pc")
    if m.group("cancel_shutdown"):
        return Intent("system_authority", text, action="cancel_shutdown")
    return None


def _match_ppt_open_slide(text: str) -> Intent | None:
    m = PPT_OPEN_SLIDE_RE.match(text)
    if not m:
        return None
    q = m.group("q1") or m.group("q2") or m.group("q3") or m.group("q4")
    raw_s = m.group("s1") or m.group("s2") or m.group("s3")
    topic = m.group("t4")

    clean_q = (q or "").strip()
    clean_q = re.sub(r"^\s*(?:(?:hey|ok|hi)\s+)?(?:nightmare[, ]+)?(?:please\s+)?", "", clean_q, flags=re.I)
    clean_q = re.sub(r"^\s*(?:comments?\s+(?:and\s+)?|so\s+|well\s+|can\s+you\s+|could\s+you\s+)", "", clean_q, flags=re.I)
    clean_q = re.sub(r"^\s*(?:no[,\s]+)?(?:a\s+lesson\s+\d+\s+is[.,\s]+)?(?:it\s+is\s+)?", "", clean_q, flags=re.I)
    clean_q = re.sub(r"^\s*(?:\d+\.\s*)?(?:open\s+\d+\.?\s*)?", "", clean_q, flags=re.I)
    clean_q = re.sub(r"^\s*(?:find\s+and\s+open|open\s*file|open|find|launch)\s+(?:the\s+|a\s+|an\s+)?(?:file\s+)?(?:presentation|slides?|document)?(?:\s+related\s+to|\s+about)?\s*", "", clean_q, flags=re.I)
    clean_q = re.sub(r"\s+(?:in|on|with|using)\s+(?:powerpoint|ppt|presentation)\b.*$", "", clean_q, flags=re.I)
    clean_q = re.sub(r"\s+(?:and\s+)?(?:move|go|jump|show|display)\s*$", "", clean_q, flags=re.I)
    clean_q = clean_q.strip(" .,?!")

    slide_num = _parse_slide_number(raw_s) if raw_s else None
    return Intent(
        "ppt_open_slide",
        text,
        query=clean_q or text,
        slide=slide_num,
        note_text=topic.strip() if topic else None,
        action="topic" if topic else ("goto" if slide_num else None),
    )


def _match_ppt_control(text: str) -> Intent | None:
    m = PPT_CONTROL_RE.match(text)
    if not m:
        return None
    if m.group("next"):
        return Intent("ppt_control", text, action="next")
    if m.group("prev"):
        return Intent("ppt_control", text, action="previous")
    if m.group("start"):
        return Intent("ppt_control", text, action="start")
    if m.group("topic"):
        topic = m.group("topic").strip()
        return Intent("ppt_control", text, action="topic", query=topic)
    raw_s = m.group("s1") or m.group("s2")
    slide_num = _parse_slide_number(raw_s)
    if slide_num is not None:
        return Intent("ppt_control", text, action="goto", slide=slide_num)
    return None


def _match_timeline_diff(text: str) -> Intent | None:
    t = text.strip()
    if TIMELINE_DIFF_RE.match(t):
        return Intent("timeline_diff", text)
    t_clean = re.sub(r"[^a-z0-9\s]", "", t.lower()).strip()
    if t_clean in {
        "what change in the citizengraph timeline from the gdrive",
        "what changed in the citizengraph timeline",
        "compare citizengraph timeline with gdrive",
        "check gdrive timeline updates",
        "what did my team update in the timeline",
        "check timeline diff",
        "timeline diff",
        "citizengraph timeline diff",
        "check timeline changes",
    }:
        return Intent("timeline_diff", text)
    return None


def _match_team_progress(text: str) -> Intent | None:
    t = text.strip()
    if t.lower().startswith("/timeline"):
        return Intent("team_progress", text)

    m = TEAM_PROGRESS_RE.match(t)
    if m:
        target = (m.groupdict().get("target") or "").strip()
        if not target:
            # Check if team number was in the main phrase
            m_team = re.search(r"\b(team\s*\d+|team\s+[a-z0-9_-]+)\b", t, re.I)
            if m_team:
                target = m_team.group(1).strip()
        return Intent("team_progress", text, query=target)

    t_clean = re.sub(r"[^a-z0-9\s]", "", t.lower()).strip()
    if t_clean in {
        "show team progress", "open timeline tracker", "check team 1 progress",
        "show team 1 progress", "team progress", "timeline tracker", "open timeline",
        "check team progress", "check progress", "open team tracker", "team tracker",
        "citizengraph timeline", "citizengraph timeline tracker", "open citizengraph timeline",
        "citizengraph thesis timeline",
    }:
        target = "team 1" if "team 1" in t_clean else ""
        return Intent("team_progress", text, query=target)

    if re.search(r"\b(check|show|view|open)\s+(?:the\s+)?(team\s*\d+)\s+progress\b", t_clean):
        m_team = re.search(r"\b(team\s*\d+)\b", t_clean)
        return Intent("team_progress", text, query=m_team.group(1) if m_team else "")

    if not re.search(r"\b(?:file|document|find|related|search)\b", t_clean):
        if re.search(r"^(?:(?:open|show|check|view|display)\s+)?(?:the\s+)?(?:project\s+|citizengraph\s+)?timeline\b", t_clean):
            return Intent("team_progress", text)

    return None


def _match_approve_email(text: str) -> Intent | None:
    t = text.strip()
    if APPROVE_EMAIL_RE.match(t):
        return Intent("approve_email", text)
    t_clean = re.sub(r"[^a-z0-9\s]", "", t.lower()).strip()
    if t_clean in {"approve email", "send email", "send the email", "approve reminder email", "confirm email", "approve reminder"}:
        return Intent("approve_email", text)
    return None


def _match_email_report(text: str) -> Intent | None:
    t = text.strip()
    if EMAIL_REPORT_RE.match(t):
        return Intent("email_report", text)
    # Phrasing: (?:do i have|check|what is|open).*?(?:new |latest |priority )?(?:mail|email|notif).*
    if re.search(r"\b(?:do\s+i\s+have|check|what\s+is|whats|open).*?(?:new\s+|latest\s+|priority\s+)?(?:mail|email|notif)\b", t, re.I):
        return Intent("email_report", text)
    t_clean = re.sub(r"[^a-z0-9\s]", "", t.lower()).strip()
    if t_clean in {
        "check my priority emails",
        "read my inbox",
        "do i have any new emails",
        "check priority emails",
        "check my inbox",
        "check the inbox",
        "read the inbox",
        "read inbox",
        "read my emails",
        "read priority emails",
        "read my priority emails",
        "do i have new emails",
        "do i have any emails",
        "do i have any new email",
        "any new emails",
        "any priority emails",
        "email report",
        "inbox report",
        "priority email report",
        "my priority emails",
        "what is in my inbox",
        "whats in my inbox",
    }:
        return Intent("email_report", text)
    return None


def _match_priority_emails(text: str) -> Intent | None:
    t = text.strip()
    if t.lower().startswith("/emails") or t.lower().startswith("/priority"):
        return Intent("priority_emails", text)
    t_clean = re.sub(r"[^a-z0-9\s]", "", t.lower()).strip()
    if t_clean in {
        "show priority emails", "priority emails", "check priority emails",
        "open priority emails", "show emails", "priority email feed",
        "check emails", "email feed", "open emails", "view priority emails",
        "show priority email", "priority dispatch",
    }:
        return Intent("priority_emails", text)
    if re.search(r"\b(show|open|check|view)\s+(?:the\s+)?priority\s+emails?\b", t_clean):
        return Intent("priority_emails", text)
    return None


def _match_calendar_query(text: str) -> Intent | None:
    t = text.strip()
    m = CALENDAR_QUERY_RE.match(t)
    if m:
        tf = (
            m.group("timeframe1")
            or m.group("timeframe2")
            or m.group("timeframe3")
            or m.group("timeframe4")
            or m.group("timeframe5")
            or "this week"
        ).strip().lower()
        return Intent("calendar_query", text, query=tf)
    t_clean = re.sub(r"[^a-z0-9\s]", "", t.lower()).strip()
    if t_clean in {
        "do i have any meetings this week",
        "do i have meetings this week",
        "what meetings do i have this week",
        "any meetings this week",
        "meetings this week",
        "check meetings this week",
        "check calendar this week",
        "calendar this week",
        "my schedule this week",
        "schedule this week",
        "do i have any meetings today",
        "meetings today",
        "do i have any meetings",
        "check my calendar",
        "what meetings do i have",
        "what are in my calendar",
        "what is in my calendar",
        "whats in my calendar",
        "what is on my calendar",
        "whats on my calendar",
        "calendar events",
        "calendar",
        "show my calendar",
        "check calendar",
    }:
        tf = "today" if "today" in t_clean else "this week"
        return Intent("calendar_query", text, query=tf)
    if re.search(r"\bwhat(?:'s|\s+is|\s+are)\s+(?:in|on)\s+(?:my\s+)?calendar\b", t.lower()):
        tf = "today" if "today" in t.lower() else "this week"
        return Intent("calendar_query", text, query=tf)
    return None


def _match_calendar_create(text: str) -> Intent | None:
    t = text.strip()
    m = CALENDAR_CREATE_RE.match(t)
    if m:
        details = (m.group("details1") or m.group("details2") or "").strip()
        return Intent("calendar_create", text, query=details)

    # (?:create|add|schedule).*?(?:meeting|calendar|birthday).*
    if re.search(r"\b(?:create|add|schedule)\b.*?\b(?:meeting|calendar|birthday)\b", t, re.I):
        return Intent("calendar_create", text, query=t.strip())
    return None


def _match_measurable_task(text: str) -> Intent | None:
    t = text.strip()
    t_norm = re.sub(
        r"^(?:create|add|set(?:\s+up)?|track)\s+(?:a\s+|an\s+)?(?:new\s+)?(?:measurable\s+)?task\s*[\.:,]\s*(?:to\s+)?",
        "create a task to ",
        t,
        flags=re.I,
    )
    if MEASURABLE_TASK_LIST_RE.match(t) or re.search(r"\b(?:what\s+are\s+my|do\s+i\s+have\s+any|have\s+any|open|list|what\s+is\s+the)\s+(?:\d+\s+)?(?:tasks?|to-?dos?)\b", t.lower()):
        return Intent("measurable_task", text, action="list")



    m_up = MEASURABLE_TASK_UPDATE_RE.match(t) or MEASURABLE_TASK_UPDATE_RE.match(t_norm)
    if m_up:
        th = m_up.group("target_hint1") or m_up.group("target_hint2") or m_up.group("target_hint3")
        title = (m_up.group("title1") or m_up.group("title2") or m_up.group("title3") or "").strip()
        val = m_up.group("value1") or m_up.group("value2") or m_up.group("value3") or "0"
        return Intent(
            "measurable_task",
            text,
            action="update",
            query=title,
            current_progress=int(val),
            target_progress=int(th) if th else None,
        )

    # Direct update regex: ^update (?:task )?(?P<name>.+?) to (?P<val>\d+)$
    m_direct = re.match(r"^\s*update\s+(?:task\s+)?(?P<name>[a-zA-Z0-9_\-\s]+?)\s+to\s+(?P<val>\d+)\s*[.!?]*$", t, re.I)
    if m_direct:
        name = m_direct.group("name").strip()
        val = int(m_direct.group("val"))
        return Intent("measurable_task", text, action="update", query=name, current_progress=val)

    m_task_only = re.match(r"^\s*update\s+task\s+(?P<name>[a-zA-Z0-9_\-\s]+?)\s*[.!?]*$", t, re.I)
    if m_task_only:
        name = m_task_only.group("name").strip()
        return Intent("measurable_task", text, action="update", query=name)

    inline_curr = None
    m_prog = re.search(r"\b(?:and\s+)?(?:my\s+)?progress\s+(?:is|=|at)\s+(\d+)\b", t_norm, re.I)
    t_to_match = t_norm
    if m_prog:
        inline_curr = int(m_prog.group(1))
        t_to_match = t_norm[: m_prog.start()].strip()

    # Natural task creation: create a task.*
    m_nat = re.match(r"^\s*(?:create|add|set(?:\s+up)?|track)\s+(?:a\s+|an\s+)?(?:new\s+)?(?:measurable\s+)?task[\.:,\s]+(?P<rest>.+)$", t, re.I)
    if m_nat:
        rest = m_nat.group("rest").strip()
        inline_c = inline_curr
        m_p = re.search(r"\b(?:and\s+)?(?:my\s+)?progress\s+(?:is|=|at)\s+(\d+)\b", rest, re.I)
        if m_p:
            inline_c = int(m_p.group(1))
            rest = rest[:m_p.start()].strip(" .,;!")
        m_rng = re.search(r"\bchapters?\s+(?:one|[1])\s+to\s+(?:three|[3])\b", rest, re.I)
        if m_rng:
            verb_m = re.search(r"\b(acquire|finish|complete|write|read|review)\b", rest, re.I)
            verb = verb_m.group(1).capitalize() if verb_m else "Finish"
            return Intent("measurable_task", text, action="create", query=f"{verb} chapters 1 to 3", target_progress=3, current_progress=inline_c if inline_c is not None else 0, unit="chapters")
        m_num_u = re.search(r"\b(\d+)\s*(clients?|pages?|sources?|chapters?|items?|articles?|words?|papers?)\b", rest, re.I)
        if m_num_u:
            tgt_v = int(m_num_u.group(1))
            unit_v = m_num_u.group(2).lower()
            title_v = re.sub(r"^[Tt]o\s+", "", rest).strip(" .,;!")
            return Intent("measurable_task", text, action="create", query=title_v.capitalize(), target_progress=tgt_v, current_progress=inline_c if inline_c is not None else 0, unit=unit_v)
        clean_tit = re.sub(r"^[Tt]o\s+", "", rest).strip(" .,;!")
        if clean_tit:
            return Intent("measurable_task", text, action="create", query=clean_tit.capitalize(), target_progress=1, current_progress=inline_c if inline_c is not None else 0)



    m_cr = MEASURABLE_TASK_CREATE_RE.match(t) or MEASURABLE_TASK_CREATE_RE.match(t_norm) or MEASURABLE_TASK_CREATE_RE.match(t_to_match)
    if m_cr:
        verb = m_cr.group("verb1") or m_cr.group("verb2") or ""
        tgt = m_cr.group("target1") or m_cr.group("target2") or "0"
        unit = (m_cr.group("unit1") or m_cr.group("unit2") or "").strip()
        title = (m_cr.group("title1") or m_cr.group("title2") or "").strip()
        title = re.sub(r"\s+task$", "", title, flags=re.I).strip()
        if not title:
            title = f"{verb.capitalize()} {tgt} {unit}".strip() if unit else f"{verb.capitalize()} {tgt}".strip()
        full_title = f"{verb.capitalize()} {tgt} {title}".strip() if verb and not title.lower().startswith(verb.lower()) else (title or verb)
        return Intent(
            "measurable_task",
            text,
            action="create",
            query=title or full_title,
            target_progress=int(tgt),
            current_progress=inline_curr if inline_curr is not None else 0,
            unit=unit,
        )

    m_range = re.search(r"\bchapters?\s+(?:one|[1])\s+to\s+(?:three|[3])\b", t_to_match, re.I)
    if m_range:
        verb_m = re.search(r"\b(acquire|finish|complete|write|read|review)\b", t_to_match, re.I)
        verb = verb_m.group(1).capitalize() if verb_m else "Finish"
        return Intent(
            "measurable_task",
            text,
            action="create",
            query=f"{verb} chapters 1 to 3",
            target_progress=3,
            current_progress=inline_curr if inline_curr is not None else 0,
            unit="chapters",
        )

    t_clean = t.lower()
    m_loose = re.search(r"\bupdate\s+(?:my\s+)?(?:(\d+)\s+)?([a-z0-9_\-\s]+?)\s+progress\s+to\s+(\d+)\b", t_clean)
    if m_loose:
        th, title, val = m_loose.groups()
        return Intent(
            "measurable_task",
            text,
            action="update",
            query=title.strip(),
            current_progress=int(val),
            target_progress=int(th) if th else None,
        )

    return None


def route(
    text: str,
    settings: Settings,
    registry: Registry,
    last_project: Path | None = None,
    context: ConversationContext | None = None,
) -> Intent:
    raw_text = text
    text = pre_normalize(text)
    n = normalize(text)

    # Layer 2 Stateful ConversationContext Buffer check
    if context is None:
        try:
            from .context_buffer import get_context_buffer
            context = get_context_buffer()
        except Exception:
            context = None

    if context and not context.is_expired():
        # 1. Resolve ordinal follow-ups ("the first one", "#1", "the Readme.md") in <5 ms
        cand = context.resolve_ordinal(text)
        if cand:
            return Intent("open_file", raw_text, query=cand, router_path="context_buffer", confidence_margin=1.0)

        # 2. Resolve coreference pronouns ("present it", "open it", "read it") against last_opened_file
        pronoun_match = context.resolve_pronoun(text)
        if pronoun_match:
            act, fpath = pronoun_match
            if act == "present" and (fpath.lower().endswith((".pptx", ".ppt")) or "ppt" in fpath.lower()):
                return Intent("ppt_control", raw_text, action="start", ppt_path=fpath, router_path="context_buffer", confidence_margin=1.0)
            elif act == "open":
                return Intent("open_file", raw_text, query=fpath, router_path="context_buffer", confidence_margin=1.0)

    if re.match(r"^https?://\S+$", text.strip(), re.I):
        return Intent("open_url", raw_text, url=text.strip(), site="URL")

    if re.match(r"^[a-zA-Z0-9_\-\.\s\(\)]+\.(?:docx?|pptx?|xlsx?|pdf|txt|md)$", text.strip(), re.I):
        return Intent("open_file", raw_text, query=text.strip())

    m = RAW_CMD.match(text)
    if m:
        return Intent("run_command", text, command=m.group("cmd"))

    sys_cmd = _match_system_authority(text)
    if sys_cmd is not None:
        return sys_cmd

    cal_q = _match_calendar_query(text)
    if cal_q is not None:
        return cal_q

    cal_cr = _match_calendar_create(text)
    if cal_cr is not None:
        return cal_cr

    meas_task = _match_measurable_task(text)
    if meas_task is not None:
        return meas_task

    email_rep = _match_email_report(text)
    if email_rep is not None:
        return email_rep

    p_emails = _match_priority_emails(text)
    if p_emails is not None:
        return p_emails

    appr_email = _match_approve_email(text)
    if appr_email is not None:
        return appr_email

    diff_prog = _match_timeline_diff(text)
    if diff_prog is not None:
        return diff_prog

    if OPEN_TIMELINE_EXCEL_RE.match(text):
        return Intent("open_team_excel", text)

    team_prog = _match_team_progress(text)
    if team_prog is not None:
        return team_prog

    if RERUN_TASK_RE.match(text):
        return Intent("rerun_task", text)

    if RESET_RE.match(text):
        return Intent("reset_session", text)
    if DB_OPEN_RE.match(text):
        return Intent("db_open", text)
    if DB_CLOSE_RE.match(text):
        return Intent("db_close", text)
    if SETTINGS_OPEN_RE.match(text):
        return Intent("settings_open", text)
    if SETTINGS_CLOSE_RE.match(text):
        return Intent("settings_close", text)

    if CLEARANCE_STATUS_RE.match(text):
        return Intent("clearance_status", text)

    if CLEAR_CACHE_RE.match(text):
        return Intent("clear_cache", text)

    m_fact = REMEMBER_RE.match(text)
    if m_fact:
        return Intent("remember_fact", text, note_text=m_fact.group("fact").strip())
    if LIST_FACTS_RE.search(n) and not ANY_FILENAME_RE.search(text):
        return Intent("list_facts", text)

    m_note = ADD_NOTE_RE.match(text)
    if m_note:
        return Intent("add_note", text, note_text=m_note.group("note").strip())

    if not ANY_FILENAME_RE.search(text):
        for regex, kind in ((DELETE_NOTE_RE, "delete_note"), (COMPLETE_NOTE_RE, "complete_note")):
            m_target = regex.match(text)
            if m_target:
                note_id, description = _note_target(m_target.group("rest"))
                return Intent(kind, text, note_id=note_id, note_text=description)

    if not ANY_FILENAME_RE.search(text):
        m_forget = FORGET_RE.match(text)
        if m_forget:
            return Intent("forget_fact", text, note_text=m_forget.group("fact").strip())

    if LIST_NOTES_RE.search(n) and not _is_doc_query(text, n):
        return Intent("list_notes", text)

    if OPEN_PORTFOLIO_RE.match(text):
        target_url = None if OPEN_LAST_LINK_RE.match(text) else getattr(settings, "developer_portfolio_url", "https://github.com/Raizel-Codes/MyPortfolioV2")
        return Intent("open_portfolio", text, url=target_url)

    web = _web_target(text, n, registry)
    if web is not None:
        return web

    if RUN_VERB.search(n):
        task_id = registry.find_task(n)
        if task_id:
            return Intent("run_task", text, task_id=task_id)

        m_dev = DEV_TASK_KIND_RE.search(n)
        if m_dev:
            raw_k = m_dev.group("kind").lower().replace(" ", "").replace("-", "")
            if raw_k in {"tests", "test"}:
                k = "test"
            elif "npm" in raw_k:
                k = "npmtest"
            elif raw_k == "pytest":
                k = "pytest"
            elif raw_k == "typecheck":
                k = "typecheck"
            else:
                k = raw_k
            res = _resolve_with_followup(text, n, settings.desktop_root, last_project)
            return Intent("run_dev_task", text, task_id=k, resolution=res)

    m_voice = VOICE_SETTINGS_RE.match(text)
    if m_voice:
        g = (m_voice.group("g1") or m_voice.group("g2") or "").lower()
        return Intent("voice_settings", text, voice_gender=g)

    if CONVERSATION_HISTORY_RE.search(text):
        return Intent("conversation_history", text)

    m_search = SEARCH_PROJECTS_RE.match(text)
    if m_search:
        q = m_search.group("query").strip().strip(" .,?!")
        return Intent("search_projects", text, query=q)

    if OPEN_HELPER_RE.match(text):
        return Intent("quick_reply", text, note_text="helper")

    if QUICK_TIME_RE.search(text):
        return Intent("quick_reply", text, note_text="time")
    if QUICK_HELP_RE.match(text):
        return Intent("quick_reply", text, note_text="help")
    if QUICK_GREET_RE.match(text):
        return Intent("quick_reply", text, note_text="greet")
    if QUICK_THANKS_RE.match(text):
        return Intent("quick_reply", text, note_text="thanks")
    if QUICK_NAME_RE.match(text):
        return Intent("quick_reply", text, note_text="name")
    if DEVELOPER_IDENTITY_RE.match(text):
        return Intent("developer_info", text)
    if DEVELOPER_WHY_RE.match(text):
        return Intent("developer_why", text)
    if DEVELOPER_SKILLS_RE.match(text):
        return Intent("developer_skills", text)
    if DEVELOPER_PROJECTS_RE.match(text):
        return Intent("developer_projects", text)
    if SYSTEM_TELEMETRY_RE.match(text):
        return Intent("system_telemetry", text)
    if SYSTEM_BATTERY_RE.match(text):
        return Intent("system_battery", text)
    if SYSTEM_PROCESSES_RE.match(text):
        return Intent("system_processes", text)
    if DEFENSE_START_RE.match(text):
        return Intent("defense_start", text)
    if DEFENSE_STOP_RE.match(text):
        return Intent("defense_stop", text)
    if DEFENSE_QUESTION_RE.match(text):
        return Intent("defense_question", text)
    if DEFENSE_STATUS_RE.match(text):
        return Intent("defense_status", text)
    if MODEL_IDENTITY_RE.match(text):
        return Intent("quick_reply", text, note_text="model_identity")

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

    if WORKSPACE_BRIEFING_RE.search(n):
        return Intent("workspace_briefing", text)

    if WORKSPACE_CHANGES_RE.search(n):
        return Intent("workspace_changes", text)

    if WORK_PRIORITIES_RE.search(n):
        return Intent("work_priorities", text)

    if CROSS_PROJECT.search(n):
        return Intent("cross_project", text)

    ppt_open = _match_ppt_open_slide(text)
    if ppt_open is not None:
        return ppt_open

    ppt_ctrl = _match_ppt_control(text)
    if ppt_ctrl is not None:
        return ppt_ctrl

    if GITHUB_CHECK_RE.search(text):
        force = bool(re.search(r"\b(?:force|refresh|now|live)\b", text, re.I))
        return Intent("github_check", text, force_refresh=force)

    file_intent = _match_open_file(text, n)
    if file_intent is not None:
        return file_intent

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
            if app_id.lower() not in {"powerpoint", "ppt"} and not re.search(r"\b(slides?|ppt|pptx|presentation|docx?|word|xlsx?|excel|pdf)\b", n):
                return Intent("open_project_in", text, app_id=app_id, resolution=res)
        if wants_folder and has_project and not is_progress:
            return Intent("open_folder", text, resolution=res)
        if app_id:
            return Intent("open_app", text, app_id=app_id)
        if has_project and not is_progress:
            if not re.search(r"\b(doc|docs|document|chapter|checklist|file|pdf|sheet|slide|notes)\b", n):
                return Intent("open_folder", text, resolution=res)

    if OPEN_VERB.search(n) and not registry.find_app(n):
        padded = f" {n} "
        for alias in sorted(UNLISTED_APP_NAMES, key=len, reverse=True):
            if f" {alias} " in padded:
                return Intent("quick_reply", text, note_text="unknown_app", query=UNLISTED_APP_NAMES[alias])

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

    # Level 2 Semantic Router (FastEmbed ONNX): matches queries that miss exact regexes
    try:
        from .semantic_router import match_semantic_intent
        matched_semantic = match_semantic_intent(text)
        if matched_semantic is not None:
            return matched_semantic
    except Exception:
        pass

    return Intent("chat", text, router_path="fallback", confidence_margin=0.0)
