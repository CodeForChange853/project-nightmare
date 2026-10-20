"""Settings screen: editing apps.json from the browser (Phase 6)."""
import json
from dataclasses import replace

import pytest
from fastapi.testclient import TestClient

from backend.core import apps_config
from backend.core.actions import ActionResult
from backend.main import create_app

from .conftest import APPS


class FakeLLM:
    name = "fake"

    async def complete(self, prompt):
        return "ok"


@pytest.fixture
def full(settings):
    s = replace(settings, pin="123456", phone_pin="999999")
    c = TestClient(create_app(s, FakeLLM()), base_url="http://127.0.0.1:8000")
    assert c.post("/api/login", json={"pin": "123456"}).status_code == 200
    return c, s


def unlock(c):
    token = c.post("/api/settings/open", json={"pin": "123456"}).json()["token"]
    return {"X-Settings-Token": token}


def load(c, hdr):
    r = c.get("/api/settings/apps", headers=hdr)
    assert r.status_code == 200
    return r.json()


def save(c, hdr, data):
    body = {"apps": data["apps"], "tasks": data["tasks"], "version": data["version"]}
    return c.post("/api/settings/apps", json=body, headers=hdr)


def on_disk(s):
    return json.loads(s.apps_file.read_text())


def test_settings_need_the_typed_pin(full):
    c, _ = full
    assert c.get("/api/settings/apps").status_code == 403
    assert c.post("/api/settings/open", json={"pin": "000000"}).status_code == 403
    hdr = unlock(c)
    data = load(c, hdr)
    assert set(data["apps"]) == set(APPS["apps"]) and "bims" in data["projects"]
    c.post("/api/settings/close", headers=hdr)
    assert c.get("/api/settings/apps", headers=hdr).status_code == 403


def test_voice_can_only_open_the_panel(full):
    c, _ = full
    r = c.post("/api/chat", json={"text": "open settings"}).json()
    assert r["intent"] == "settings_open" and r["ui"] == "settings_pin"
    assert c.post("/api/chat", json={"text": "close settings"}).json()["ui"] == "settings_close"


def test_readonly_and_phone_cannot_use_settings(settings):
    s = replace(settings, pin="123456", phone_pin="999999", remote_hosts=("laptop.t.ts.net",))
    c = TestClient(create_app(s, FakeLLM()), base_url="http://127.0.0.1:8000")
    c.post("/api/login", json={"pin": "999999"})
    assert c.post("/api/settings/open", json={"pin": "123456"}).status_code == 403
    assert not c.post("/api/chat", json={"text": "open settings"}).json()["ok"]

    phone = TestClient(c.app, base_url="https://laptop.t.ts.net")
    phone.headers.update({"X-Forwarded-For": "100.64.0.7", "Origin": "https://laptop.t.ts.net"})
    phone.post("/api/login", json={"pin": "123456"})  # laptop PIN, but through the proxy
    assert phone.post("/api/settings/open", json={"pin": "123456"}).status_code == 403


def test_save_adds_an_app_backs_up_and_takes_effect_now(full, monkeypatch):
    c, s = full
    hdr = unlock(c)
    data = load(c, hdr)
    data["apps"]["paint"] = {"label": "Paint", "argv": ["mspaint.exe"], "aliases": ["paint", "ms paint"]}
    r = save(c, hdr, data)
    assert r.status_code == 200, r.text
    assert r.json()["changes"] == ["added app paint"] and r.json()["notes"] == []
    assert on_disk(s)["apps"]["paint"]["argv"] == ["mspaint.exe"]
    assert len(list((s.apps_file.parent / "backups").glob("apps-*.json"))) == 1

    # no restart needed: the very next command sees the new app
    ran = []
    monkeypatch.setattr("backend.core.orchestrator.execute",
                        lambda plan: ran.append(plan.argv) or ActionResult(True, "Opened."))
    assert c.post("/api/chat", json={"text": "open paint"}).json()["intent"] == "open_app"
    assert ran == [["mspaint.exe"]]
    assert "paint" in c.get("/api/status").json()["apps"]


def test_new_or_changed_tasks_always_ask_first(full):
    c, s = full
    hdr = unlock(c)
    data = load(c, hdr)
    assert data["tasks"]["bims-git"]["confirm"] is False  # hand-written and untouched: stays as it is
    data["tasks"]["build"] = {"label": "Build", "argv": ["npm", "run", "build"], "project": "bims",
                              "confirm": False, "wait": True, "timeout": 120}
    r = save(c, hdr, data).json()
    assert on_disk(s)["tasks"]["build"]["confirm"] is True
    assert on_disk(s)["tasks"]["bims-git"]["confirm"] is False
    assert any("build" in n for n in r["notes"])

    data = load(c, hdr)
    data["tasks"]["bims-git"]["label"] = "git status (BIMS)"
    save(c, hdr, data)
    assert on_disk(s)["tasks"]["bims-git"]["confirm"] is True


def test_shell_apps_always_ask_first(full):
    c, s = full
    hdr = unlock(c)
    data = load(c, hdr)
    data["apps"]["ps"] = {"label": "PowerShell", "argv": ["C:\\Windows\\powershell.EXE", "-c", "calc"]}
    r = save(c, hdr, data).json()
    assert on_disk(s)["apps"]["ps"]["confirm"] is True
    assert any("ask before opening" in n for n in r["notes"])


@pytest.mark.parametrize("bad", [
    {"apps": {"Bad Id": {"label": "x", "argv": ["x"]}}},
    {"apps": {"x": {"label": "x", "argv": []}}},
    {"apps": {"x": {"label": "x", "argv": ["a\nb"]}}},
    {"apps": {"x": {"label": "", "argv": ["x"]}}},
    {"apps": {"x": {"label": "x", "argv": ["x"], "project_arg": True, "project_flag": "; rm"}}},
    {"tasks": {"t": {"label": "t", "argv": ["x"], "project": "nope"}}},
    {"tasks": {"t": {"label": "t", "argv": ["x"], "timeout": 9999}}},
    {"tasks": {"t": {"label": "t", "argv": ["x"], "wait": "yes"}}},
])
def test_invalid_entries_are_refused_and_nothing_is_written(full, bad):
    c, s = full
    hdr = unlock(c)
    data = load(c, hdr)
    before = s.apps_file.read_text()
    body = {
        "apps": {**data["apps"], **bad.get("apps", {})},
        "tasks": {**data["tasks"], **bad.get("tasks", {})},
        "version": data["version"],
    }
    r = c.post("/api/settings/apps", json=body, headers=hdr)
    assert r.status_code == 422 and r.json()["detail"]["errors"]
    assert s.apps_file.read_text() == before


def test_unknown_keys_are_dropped(full):
    c, s = full
    hdr = unlock(c)
    data = load(c, hdr)
    data["apps"]["calc"] = {"label": "Calc", "argv": ["calc.exe"], "shell": True, "env": {"X": "1"}}
    save(c, hdr, data)
    assert on_disk(s)["apps"]["calc"] == {"label": "Calc", "argv": ["calc.exe"], "aliases": []}


def test_hand_edit_in_between_is_not_overwritten(full):
    c, s = full
    hdr = unlock(c)
    data = load(c, hdr)
    s.apps_file.write_text(json.dumps({"apps": {}, "tasks": {}}))
    data["apps"]["paint"] = {"label": "Paint", "argv": ["mspaint.exe"]}
    assert save(c, hdr, data).status_code == 409
    assert on_disk(s) == {"apps": {}, "tasks": {}}


def test_saving_drops_waiting_confirmations(full, monkeypatch):
    c, _ = full
    ran = []
    monkeypatch.setattr("backend.core.orchestrator.execute", lambda plan: ran.append(plan))
    pending = c.post("/api/chat", json={"text": "start the bims dev server"}).json()
    assert pending["needs_confirm"]
    hdr = unlock(c)
    data = load(c, hdr)
    data["tasks"]["bims-dev"]["argv"] = ["npm", "run", "start"]
    save(c, hdr, data)
    r = c.post("/api/confirm", json={"id": pending["pending_id"], "approve": True}).json()
    assert not r["ok"] and ran == []


def test_only_five_backups_are_kept(full):
    c, s = full
    hdr = unlock(c)
    for i in range(7):
        data = load(c, hdr)
        data["apps"]["notepad"]["label"] = f"Notepad {i}"
        assert save(c, hdr, data).status_code == 200
    assert len(list((s.apps_file.parent / "backups").glob("apps-*.json"))) == 5


def test_check_is_a_dry_run(full, monkeypatch):
    c, _ = full
    hdr = unlock(c)
    monkeypatch.setattr("subprocess.Popen", lambda *a, **k: pytest.fail("Check must not run anything"))
    r = c.post("/api/settings/apps/check", headers=hdr, json={
        "kind": "task", "spec": {"argv": ["definitely-not-a-program-xyz", "--go"], "project": "bims"},
    }).json()
    assert r["found"] is None and r["note"] and r["folder"].endswith("bims") and r["asks_first"]
    r = c.post("/api/settings/apps/check", headers=hdr,
               json={"kind": "app", "spec": {"argv": ["cmd.exe", "/c", "x"]}}).json()
    assert r["shell"] and r["asks_first"]


def test_is_shell_names():
    assert apps_config.is_shell("C:\\Windows\\System32\\WindowsPowerShell\\v1.0\\powershell.exe")
    assert apps_config.is_shell("py") and apps_config.is_shell("CMD.EXE")
    assert not apps_config.is_shell("notepad.exe") and not apps_config.is_shell("code")
