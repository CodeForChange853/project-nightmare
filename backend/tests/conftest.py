import json

import pytest

from backend.config import Settings
from backend.core.actions import Registry

TOKEN = "t" * 32

APPS = {
    "apps": {
        "vscode": {"label": "VS Code", "argv": ["code"], "project_arg": True,
                   "aliases": ["vs code", "visual studio code"]},
        "notepad": {"label": "Notepad", "argv": ["notepad.exe"], "aliases": ["notepad"]},
        "chrome": {"label": "Chrome", "argv": ["chrome.exe"], "aliases": ["chrome"], "project_arg": False},
    },
    "tasks": {
        "bims-dev": {"label": "BIMS dev server", "project": "bims", "argv": ["npm", "run", "dev"],
                     "aliases": ["bims dev server"], "confirm": True},
        "bims-git": {"label": "git status in BIMS", "project": "bims", "argv": ["git", "status"],
                     "aliases": ["bims git status"], "wait": True, "confirm": False},
    },
}


@pytest.fixture
def desktop(tmp_path):
    root = tmp_path / "Desktop"
    (root / "bims").mkdir(parents=True)
    (root / "bims" / "handoff.md").write_text("# BIMS\nDone: login page. Next: reports. Blocker: none.")
    (root / "citizengraph" / "docs").mkdir(parents=True)
    (root / "citizengraph" / "docs" / "handoff.md").write_text("CitizenGraph: schema done, API next.")
    (root / "other").mkdir()
    (root / "node_modules").mkdir()
    return root


@pytest.fixture
def settings(tmp_path, desktop):
    apps_file = tmp_path / "apps.json"
    apps_file.write_text(json.dumps(APPS))
    return Settings(desktop_root=desktop, api_token=TOKEN, db_path=tmp_path / "n.db", apps_file=apps_file)


@pytest.fixture
def registry():
    return Registry(APPS)


def pytest_configure(config):
    config.addinivalue_line("markers", "browser: drives the built UI in Chrome (needs Playwright)")
