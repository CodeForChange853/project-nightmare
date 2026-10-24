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
from .clearance import INTENT_CLEARANCE_MAP

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
    LEAD + r"(?:remember\s+(?:that|this)|keep\s+in\s+mind(?:\s+that)?)[:,\s]+(?P<fact>.+?)\s*[.!]*$",
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
    + r"(?:(?:open|show|unlock)\s+(?:me\s+)?(?:the\s+|my\s+)?(?:nightmare\s+)?settings|settings\s+open"
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
CLEARANCE_ELEVATE_RE = re.compile(
    LEAD
    + r"(?:(?:open|elevate(?:\s+to)?|unlock)\s+(?:nightmare\s+)?level\s+(?P<lvl1>[135])(?:\s+access)?|"
    r"level\s+(?P<lvl2>[135])\s+access)\s*[.!?]*$",
    re.I,
)
CLEARANCE_LOCKDOWN_RE = re.compile(
    LEAD
    + r"(?:(?:emergency\s+)?lock\s*down|drop\s+to\s+level\s+1|reset\s+clearance(?:\s+to\s+level\s+1)?)\s*[.!?]*$",
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
    r"who\s+(?:powers?|trained?|made|built|created)\s+(?:you|nightmare))\s*[?.!]*$",
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
    r"(?:open\s*file|open\s+(?:the\s+|a\s+|an\s+)?(?:file|doc|document|docs|presentation|spreadsheet)(?:\s+related\s+to|\s+about)?)\s+(?P<q3>.+?)(?:\s+(?:in|on|with|using)\s+(?P<app3>[a-zA-Z\s]+?))?|"
    r"open\s+(?P<q4>[a-zA-Z0-9_\-.\s]+?)\s+(?:in|on|with|using)\s+(?P<app4>word|powerpoint|excel|notepad|sheets|slides|acrobat|wordpad|doc|docx|ppt|pptx|xls|xlsx|pdf)|"
    r"open\s+(?P<q5>[a-zA-Z0-9_\-.\s]+?)\s+(?P<ext5>ppt|pptx|doc|docx|xls|xlsx|pdf|txt|md)|"
    r"open\s+(?P<q6>[a-zA-Z0-9_\-.\s]+?\.(?:pptx?|docx?|xlsx?|pdf|txt|md))|"
    r"open\s+(?:the\s+|a\s+|an\s+)?(?P<q7>[a-zA-Z0-9_\-.\s]*?\b(?:checklist|document|doc|paper|chapter|report|presentation|spreadsheet|notes|draft|outline)\b[a-zA-Z0-9_\-.\s]*)"
    r")\s*[.!?]*$",
    re.I,
)
PPT_OPEN_SLIDE_RE = re.compile(
    LEAD
    + r"(?:"
    r"(?:find\s+and\s+open|open|launch)\s+(?:the\s+|a\s+|an\s+)?(?P<q1>.+?)\s+(?:ppt|pptx|presentation|slides?)(?:\s+(?:to|in)\s+powerpoint)?\s+(?:and\s+)?(?:show|display|go\s+to)?\s*(?:the\s+)?slide\s+(?P<s1>\d+|[a-zA-Z]+)|"
    r"(?:find\s+and\s+open|open|launch)\s+(?:the\s+|a\s+|an\s+)?(?P<q2>.+?)(?:\s+(?:presentation|slides?|ppt|pptx))?\s+(?:at|on|to)\s+slide\s+(?P<s2>\d+|[a-zA-Z]+)|"
    r"(?:find\s+and\s+open|open|launch)\s+(?:the\s+|a\s+|an\s+)?(?P<q3>.+?)\s+in\s+powerpoint\s+(?:(?:at|on)\s+|(?:and\s+)?(?:show|display|go\s+to)\s+)?(?:the\s+)?slide\s+(?P<s3>\d+|[a-zA-Z]+)|"
    r"(?:find\s+and\s+open|open|launch)\s+(?:the\s+|a\s+|an\s+)?(?P<q4>.+?)\s+(?:ppt|pptx|presentation|slides?)(?:\s+(?:to|in)\s+powerpoint)?\s+(?:and\s+)?(?:show|display|go\s+to)\s+(?:the\s+)?slide\s+(?:about|on|regarding)\s+(?P<t4>.+?)"
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
OPEN_TIMELINE_EXCEL_RE = re.compile(
    LEAD
    + r"(?:open|launch)\s+(?:the\s+)?(?:citizengraph\s+)?(?:thesis\s+)?(?:team\s+)?timeline(?:\s+tracker)?\s+(?:in|on|with|using)\s+excel\s*[.!?]*$",
    re.I,
)
GITHUB_CHECK_RE = re.compile(
    r"\b("
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


def describe_intent(intent: Intent) -> str:
    if intent.kind == "ppt_open_slide":
        return f"ppt_open_slide → {intent.query} (slide {intent.slide or 1})"
    if intent.kind == "ppt_control":
        return f"ppt_control → {intent.action} {intent.slide or ''}".strip()
    if intent.kind == "system_authority":
        return f"system_authority → {intent.action}"
    if intent.kind == "team_progress":
        return f"team_progress → {intent.query or 'all teams'}"
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
    if intent.kind == "clearance_prompt":
        return f"clearance_prompt → Level {intent.query or '3'}"
    if intent.kind == "clearance_lockdown":
        return "clearance_lockdown → Level 1"
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
            or ""
        ).strip()
        app_or_ext = (
            m_open_file.group("app1")
            or m_open_file.group("app3")
            or m_open_file.group("app4")
            or m_open_file.group("ext5")
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
    clean_q = re.sub(r"^\s*(?:find\s+and\s+open|open|find)\s+(?:the\s+|a\s+|an\s+)?", "", clean_q, flags=re.I)
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
    return None


def _match_approve_email(text: str) -> Intent | None:
    t = text.strip()
    if APPROVE_EMAIL_RE.match(t):
        return Intent("approve_email", text)
    t_clean = re.sub(r"[^a-z0-9\s]", "", t.lower()).strip()
    if t_clean in {"approve email", "send email", "send the email", "approve reminder email", "confirm email", "approve reminder"}:
        return Intent("approve_email", text)
    return None


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

    sys_cmd = _match_system_authority(text)
    if sys_cmd is not None:
        return sys_cmd

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

    m_elevate = CLEARANCE_ELEVATE_RE.match(text)
    if m_elevate:
        lvl = m_elevate.group("lvl1") or m_elevate.group("lvl2") or "3"
        return Intent("clearance_prompt", text, query=lvl)

    if CLEARANCE_LOCKDOWN_RE.match(text):
        return Intent("clearance_lockdown", text)

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
        return Intent("github_check", text)

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

    return Intent("chat", text)
