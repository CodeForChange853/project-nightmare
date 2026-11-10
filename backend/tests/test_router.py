import pytest

from backend.core.router import route


@pytest.mark.parametrize(
    "text,kind",
    [
        ("go to my desktop directory look for the project name bims and tell me the progress of it", "progress"),
        ("what is the status of citizen graph", "progress"),
        ("how is bims going", "progress"),
        ("check on citizen graph", "progress"),
        ("what's going on with bims", "progress"),
        ("tell me about project bims", "about"),
        ("tell me about the progress of bims", "progress"),
        ("what is citizen graph all about", "about"),
        ("what's bims about", "about"),
        ("what does citizengraph do", "about"),
        ("describe bims", "about"),
        ("explain the bims project", "about"),
        ("what are my projects about", "list_projects"),
        ("what is love all about", "chat"),
        ("what is next for bims", "progress"),
        ("what's the next task in citizen graph", "progress"),
        ("list my projects", "list_projects"),
        ("how many project i have", "list_projects"),
        ("how many projects do I have", "list_projects"),
        ("what projects are on my desktop", "list_projects"),
        ("open notepad", "open_app"),
        ("launch vs code", "open_app"),
        ("open the bims folder", "open_folder"),
        ("open project bims", "open_folder"),
        ("open bims in vs code", "open_project_in"),
        ("which project needs attention", "cross_project"),
        ("progress of all my projects", "cross_project"),
        ("open bims/docs, find file.md and tell me what is written", "read_doc"),
        ("read architecture.md in bims", "read_doc"),
        ("remind me to submit chapter 3 tomorrow", "add_note"),
        ("what are my reminders", "list_notes"),
        ("complete reminder 2", "complete_note"),
        ("remind me later that i have a class in 4pm", "add_note"),
        ("remind me later for meeting or class", "add_note"),
        ("set a reminder to pay tuition", "add_note"),
        ("do i have any reminder today", "list_notes"),
        ("how many reminders do i have", "list_notes"),
        ("delete the class reminder", "delete_note"),
        ("remove reminder 3", "delete_note"),
        ("mark the class reminder as done", "complete_note"),
        ("database access open", "db_open"),
        ("database close", "db_close"),
        ("new session", "reset_session"),
        ("clear the conversation", "reset_session"),
        ("start over", "reset_session"),
        ("clear reminder 3", "delete_note"),
        ("open youtube in this browser", "open_url"),
        ("open youtube and search lofi", "open_url"),
        ("open youtube music", "open_url"),
        ("play lofi on youtube music", "open_url"),
        ("play lofi on spotify", "open_url"),
        ("google how to center a div", "open_url"),
        ("open chrome", "open_app"),
        ("what is the weather in Manila", "weather"),
        ("check a weather here in calbayog", "weather"),
        ("Calbayog weather", "weather"),
        ("what time is it", "quick_reply"),
        ("what can you do", "quick_reply"),
        ("hello nightmare", "quick_reply"),
        ("what is your name again", "quick_reply"),
        ("what's your name", "quick_reply"),
        ("open powerpoint", "quick_reply"),
        ("open microsoft word", "quick_reply"),
        ("what branch is bims on", "git_status"),
        ("start the bims dev server", "run_task"),
        ("run bims git status", "run_task"),
        ("run command dir", "run_command"),
        ("how many calls did you make today", "usage"),
        ("tell me a joke", "chat"),
        ("what's the status of the server", "chat"),
    ],
)
def test_routes(text, kind, settings, registry):
    assert route(text, settings, registry).kind == kind


def test_unknown_project_still_reports_progress_when_user_says_project(settings, registry):
    intent = route("progress of the project zebra", settings, registry)
    assert intent.kind == "progress" and intent.resolution.status == "none"


def test_project_named_like_a_website_is_not_a_website(settings, registry):
    (settings.desktop_root / "youtube-clone").mkdir()
    assert route("open youtube-clone in vs code", settings, registry).kind == "open_project_in"
    assert route("open the youtube-clone folder", settings, registry).kind == "open_folder"


def test_injected_text_cannot_become_an_action(settings, registry):
    # A handoff file might say this, but routing only ever sees the user's own words.
    intent = route("summarize bims", settings, registry)
    assert intent.kind == "progress"
    assert intent.task_id is None and intent.command is None


def test_youtube_music_routing(settings, registry):
    i1 = route("open youtube music", settings, registry)
    assert i1.kind == "open_url"
    assert i1.url == "https://music.youtube.com"
    assert i1.site == "YouTube Music"

    i2 = route("play bohemian rhapsody on youtube music", settings, registry)
    assert i2.kind == "open_url"
    assert i2.url == "https://music.youtube.com/search?q=bohemian+rhapsody"
    assert i2.site == "YouTube Music"
    assert i2.query == "bohemian rhapsody"

    i3 = route("open yt music", settings, registry)
    assert i3.kind == "open_url"
    assert i3.url == "https://music.youtube.com"
    assert i3.site == "YouTube Music"
