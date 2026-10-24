import pytest
from backend.core.router import route
from backend.core.semantic_router import match_semantic_intent, get_semantic_router


@pytest.mark.parametrize("query,expected_kind,expected_sub", [
    ("who are you again", "quick_reply", "name"),
    ("who the heck are you", "quick_reply", "name"),
    ("nightmare", "quick_reply", "greet"),
    ("what is your capability", "quick_reply", "help"),
    ("what is nightmare can do", "quick_reply", "help"),
    ("you're not doing anything go to sleep", "quick_reply", "sleep"),
    ("sleep mode please", "quick_reply", "sleep"),
    ("tell me my notes", "list_notes", None),
    ("notes right now", "list_notes", None),
    ("open access database", "db_open", None),
    ("can you open the settings menu", "settings_open", None),
    ("what did i change today", "workspace_changes", None),
    ("flush cache", "clear_cache", None),
    ("check github repos", "github_check", None),
    ("find roadmap document and open it", "open_file", None),
])
def test_semantic_intent_matching(query, expected_kind, expected_sub):
    intent = match_semantic_intent(query, threshold=0.80)
    assert intent is not None, f"Expected match for '{query}'"
    assert intent.kind == expected_kind
    if expected_sub:
        assert intent.note_text == expected_sub


def test_semantic_router_negative_controls():
    # Irrelevant or conversational queries must NOT match canonical system intents
    for query in [
        "what is the recipe for chocolate chip cookies",
        "tell me a bedtime story",
        "why is the sky blue",
        "what's for dinner tonight",
    ]:
        intent = match_semantic_intent(query, threshold=0.82)
        assert intent is None, f"Expected no match for '{query}', got {intent}"


def test_route_integration(settings, registry):
    # Tests that route() integrates the semantic router seamlessly
    intent1 = route("who the heck are you", settings, registry)
    assert intent1.kind == "quick_reply"
    assert intent1.note_text == "name"

    intent2 = route("can you open the settings menu", settings, registry)
    assert intent2.kind == "settings_open"

    intent3 = route("tell me a bedtime story", settings, registry)
    assert intent3.kind == "chat"
