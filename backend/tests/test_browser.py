"""Browser tests (Phase 6): the built UI in your installed Chrome, against a backend running in this
process with a fake model, a temporary Desktop and a temporary apps.json. Nothing is launched:
`execute` is replaced, so approved actions are only recorded.

    .venv\\Scripts\\python.exe -m pytest backend -m browser

Skipped when Playwright is not installed, Chrome can't be started, or frontend/dist is missing.
"""
import json
import socket
import threading
import time
from dataclasses import replace
from types import SimpleNamespace

import pytest

sync_api = pytest.importorskip("playwright.sync_api")
import uvicorn  # noqa: E402

from backend.core.actions import ActionResult  # noqa: E402
from backend.main import FRONTEND_DIST, create_app  # noqa: E402

expect = sync_api.expect
pytestmark = [
    pytest.mark.browser,
    pytest.mark.skipif(not (FRONTEND_DIST / "index.html").is_file(), reason="run npm run build in frontend first"),
]

PIN, PHONE_PIN = "246810", "135799"


class FakeLLM:
    name = "fake"

    async def complete(self, prompt):
        return "Login page is done. Reports are next."


@pytest.fixture(scope="module")
def browser():
    with sync_api.sync_playwright() as p:
        try:
            b = p.chromium.launch(channel="chrome", headless=True)
        except Exception as exc:  # no Chrome on this machine
            pytest.skip(f"Chrome is not available to Playwright: {exc}")
        yield b
        b.close()


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture
def server(settings, monkeypatch):
    ran = []
    monkeypatch.setattr(
        "backend.core.orchestrator.execute",
        lambda plan: ran.append(plan) or ActionResult(True, f"Done: {plan.label}."),
    )
    s = replace(settings, pin=PIN, phone_pin=PHONE_PIN)
    port = _free_port()
    srv = uvicorn.Server(uvicorn.Config(create_app(s, FakeLLM(), dist_dir=FRONTEND_DIST),
                                        host="127.0.0.1", port=port, log_level="warning"))
    thread = threading.Thread(target=srv.run, daemon=True)
    thread.start()
    deadline = time.monotonic() + 10
    while not srv.started:
        assert time.monotonic() < deadline, "test server did not start"
        time.sleep(0.05)
    yield SimpleNamespace(url=f"http://127.0.0.1:{port}", settings=s, ran=ran)
    srv.should_exit = True
    thread.join(5)


def _context(browser, **kwargs):
    return browser.new_context(reduced_motion="reduce", **kwargs)


@pytest.fixture
def page(browser, server):
    ctx = _context(browser, viewport={"width": 1400, "height": 900})
    yield ctx.new_page()
    ctx.close()


def unlock(page, server, pin=PIN, path="/"):
    page.goto(server.url + path)
    page.get_by_placeholder("PIN or token").fill(pin)
    page.get_by_role("button", name="Unlock").click()
    expect(page.get_by_role("button", name="Hold to talk").first).to_be_visible()


def send(page, text):
    box = page.get_by_label("Command", exact=True)
    box.fill(text)
    box.press("Enter")


def conversation(page):
    page.get_by_role("tab", name="Conversation").click()
    return page.get_by_role("log", name="Conversation")


def test_wrong_pin_then_unlock_and_lock(page, server):
    page.goto(server.url)
    page.get_by_placeholder("PIN or token").fill("000000")
    page.get_by_role("button", name="Unlock").click()
    expect(page.get_by_text("Invalid PIN")).to_be_visible()

    unlock(page, server)
    for node in ("Projects", "Reminders", "Apps", "Tasks", "Quick asks"):
        expect(page.get_by_role("button", name=node)).to_be_visible()
    expect(page.get_by_text("Hold the eye or Space to talk")).to_be_visible()

    page.get_by_role("button", name="Lock Nightmare").click()
    expect(page.get_by_role("heading", name="Locked")).to_be_visible()


def test_command_gets_an_answer(page, server):
    unlock(page, server)
    send(page, "list my projects")
    log = conversation(page)
    expect(log).to_contain_text("list my projects")
    expect(log).to_contain_text("bims")
    expect(log).to_contain_text("citizengraph")


def test_confirmation_needs_a_click(page, server):
    unlock(page, server)
    send(page, "start the bims dev server")
    dialog = page.get_by_role("alertdialog")
    expect(dialog).to_contain_text("npm run dev")
    dialog.get_by_role("button", name="Deny").click()
    expect(dialog).to_be_hidden()
    expect(conversation(page)).to_contain_text("Cancelled.")
    assert server.ran == []

    send(page, "start the bims dev server")
    page.get_by_role("alertdialog").get_by_role("button", name="Run it").click()
    expect(page.get_by_role("log", name="Conversation")).to_contain_text("Done: BIMS dev server")
    assert [p.argv for p in server.ran] == [["npm", "run", "dev"]]


def test_phone_pin_is_read_only(page, server):
    unlock(page, server, pin=PHONE_PIN)
    expect(page.get_by_text("Read-only", exact=True)).to_be_visible()
    expect(page.get_by_role("button", name="Apps")).to_have_count(0)
    expect(page.get_by_role("button", name="Settings")).to_have_count(0)
    send(page, "open notepad")
    expect(conversation(page)).to_contain_text("read-only session")
    assert server.ran == []


def test_phone_tabs_project_page_and_back(browser, server):
    ctx = _context(browser, viewport={"width": 412, "height": 880}, is_mobile=True, has_touch=True)
    page = ctx.new_page()
    try:
        unlock(page, server, pin=PHONE_PIN)
        nav = page.get_by_role("navigation", name="Sections")
        for tab in ("Talk", "Projects", "Reminders", "Chat"):
            expect(nav.get_by_role("button", name=tab)).to_be_visible()
        expect(page.get_by_text("Hold the eye to talk")).to_be_visible()
        expect(page.get_by_role("button", name="Open the database")).to_have_count(0)  # read-only

        nav.get_by_role("button", name="Projects").tap()
        page.get_by_role("button", name="bims").tap()
        expect(page.get_by_role("button", name="Read progress")).to_be_visible()
        expect(page.get_by_role("button", name="Open folder")).to_have_count(0)
        page.go_back()  # Android back gesture closes the project page, not Nightmare
        expect(page.get_by_label("Search projects")).to_be_visible()

        page.get_by_label("Search projects").fill("citi")
        page.get_by_role("button", name="citizengraph").tap()
        page.get_by_role("button", name="Read progress").tap()
        # answered on the Talk tab, right under the eye
        expect(page.get_by_role("region", name="Latest answer")).to_contain_text("Login page is done")

        nav.get_by_role("button", name="Chat").tap()
        expect(page.get_by_label("Command", exact=True)).to_be_visible()
        expect(page.get_by_role("log", name="Conversation")).to_contain_text("progress of citizengraph")
    finally:
        ctx.close()


def test_mini_window_home_and_back(browser, server):
    ctx = _context(browser, viewport={"width": 400, "height": 560})
    page = ctx.new_page()
    try:
        unlock(page, server, path="/?mini")
        expect(page).to_have_title("Nightmare Mini")
        send(page, "list my projects")
        expect(page.get_by_role("region", name="Latest answer")).to_contain_text("bims")

        send(page, "home")  # asks the helper to maximize: the title is the signal
        expect(page).to_have_title("Nightmare")
        page.set_viewport_size({"width": 1300, "height": 800})
        expect(page.get_by_label("Nightmare core")).to_be_visible()

        page.set_viewport_size({"width": 400, "height": 560})  # what Ctrl+Alt+N does to a full window
        expect(page).to_have_title("Nightmare Mini")
        expect(page.get_by_role("button", name="Full view")).to_be_visible()
    finally:
        ctx.close()


def test_database_viewer_and_activity_filters(page, server):
    unlock(page, server)
    send(page, "database access open")
    page.locator("#db-pin").fill(PIN)
    page.get_by_role("button", name="Open database").click()
    page.get_by_role("tab", name="Activity log").click()
    page.get_by_role("button", name="Logins & access").click()
    rows = page.get_by_role("dialog").locator("tbody tr")
    expect(page.get_by_role("dialog").locator("tbody")).to_contain_text("login")
    for kind in rows.locator("td:nth-child(2)").all_inner_texts():
        assert kind.split()[0] in {"login", "db"}, kind
    page.keyboard.press("Escape")
    expect(page.get_by_role("dialog")).to_have_count(0)


def test_settings_add_app_works_without_restart(page, server):
    unlock(page, server)
    page.get_by_role("button", name="Settings").click()
    page.locator("#settings-pin").fill(PIN)
    page.get_by_role("button", name="Open settings").click()
    dialog = page.get_by_role("dialog")
    dialog.get_by_role("button", name="Add app").click()
    dialog.get_by_label("New app id").fill("paint")
    dialog.get_by_role("button", name="Add", exact=True).click()
    dialog.get_by_label("Name shown in Nightmare").fill("Paint")
    dialog.get_by_label("Program").fill("mspaint.exe")
    expect(dialog).to_contain_text("1 unsaved change: add app paint")
    dialog.get_by_role("button", name="Save changes").click()
    expect(dialog).to_contain_text("Saved: added app paint")

    saved = json.loads(server.settings.apps_file.read_text())
    assert saved["apps"]["paint"]["argv"] == ["mspaint.exe"]
    page.keyboard.press("Escape")
    send(page, "open paint")
    expect(conversation(page)).to_contain_text("Done: open Paint")
    assert [p.argv for p in server.ran] == [["mspaint.exe"]]
