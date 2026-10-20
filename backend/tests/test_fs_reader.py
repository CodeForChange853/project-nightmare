import os

import pytest

from backend.tools import fs_reader as fs


def test_finds_project_from_spoken_sentence(desktop):
    text = "go to my desktop directory look for the project name bims and tell me the progress of it"
    res = fs.resolve_project(text, desktop)
    assert res.status == "found"
    assert res.matches[0][0].name == "bims"
    assert res.matches[0][1] == 1.0


def test_joins_split_words(desktop):
    res = fs.resolve_project("what is the status of citizen graph", desktop)
    assert res.status == "found" and res.matches[0][0].name == "citizengraph"


def test_fuzzy_mishearing_is_flagged_approximate(desktop):
    res = fs.resolve_project("progress of bins", desktop)
    assert res.status == "found"
    assert res.matches[0][0].name == "bims"
    assert res.matches[0][1] < fs.APPROX_BELOW


def test_no_match(desktop):
    assert fs.resolve_project("tell me a joke about cats", desktop).status == "none"


def test_matches_project_nightmare_and_strips_wake_word(desktop):
    (desktop / "project-nightmare").mkdir()
    res = fs.resolve_project("progress of project nightmare", desktop)
    assert res.status == "found" and res.matches[0][0].name == "project-nightmare"

    res2 = fs.resolve_project("hey nightmare what is the progress of bims", desktop)
    assert res2.status == "found" and res2.matches[0][0].name == "bims"


def test_ambiguous_prefix(desktop):
    (desktop / "bims-api").mkdir()
    (desktop / "bims-web").mkdir()
    (desktop / "bims").rmdir() if not any((desktop / "bims").iterdir()) else None
    # bims has a handoff so it stays; "bims" now exactly matches it and wins
    assert fs.resolve_project("bims", desktop).status == "found"
    (desktop / "bims" / "handoff.md").unlink()
    (desktop / "bims").rmdir()
    res = fs.resolve_project("bims", desktop)
    assert res.status == "ambiguous"
    assert {p.name for p, _ in res.matches} == {"bims-api", "bims-web"}


def test_skips_hidden_and_node_modules(desktop):
    (desktop / ".git").mkdir()
    names = [p.name for p in fs.list_projects(desktop)]
    assert "node_modules" not in names and ".git" not in names


def test_find_handoff_shallow_and_nested(desktop):
    assert fs.find_handoff(desktop / "bims").name == "handoff.md"
    nested = fs.find_handoff(desktop / "citizengraph")
    assert nested is not None and nested.parent.name == "docs"
    assert fs.find_handoff(desktop / "other") is None


def test_find_handoff_is_case_insensitive(desktop):
    (desktop / "other" / "HANDOFF.MD").write_text("x")
    assert fs.find_handoff(desktop / "other") is not None


def test_read_handoff_ok_and_truncates(desktop):
    big = desktop / "other" / "handoff.md"
    big.write_text("A" * 5000 + "Z" * 5000)
    text, truncated = fs.read_handoff(big, desktop, max_chars=1000)
    assert truncated and len(text) < 1100 and "[... truncated ...]" in text
    assert text.startswith("A") and text.endswith("Z")


def test_read_refuses_other_filenames(desktop):
    secret = desktop / "bims" / "passwords.txt"
    secret.write_text("hunter2")
    with pytest.raises(fs.PathError):
        fs.read_handoff(secret, desktop)


def test_read_refuses_paths_outside_root(tmp_path, desktop):
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "handoff.md").write_text("nope")
    with pytest.raises(fs.PathError):
        fs.read_handoff(outside / "handoff.md", desktop)
    with pytest.raises(fs.PathError):
        fs.read_handoff(desktop / ".." / "outside" / "handoff.md", desktop)


@pytest.mark.skipif(not hasattr(os, "symlink"), reason="needs symlinks")
def test_symlink_escape_is_blocked(tmp_path, desktop):
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "handoff.md").write_text("secret")
    try:
        os.symlink(outside, desktop / "linked", target_is_directory=True)
    except OSError:
        pytest.skip("symlink not permitted")
    with pytest.raises(fs.PathError):
        fs.read_handoff(desktop / "linked" / "handoff.md", desktop)


def test_find_and_read_documents_blocks_secrets(desktop):
    docs_dir = desktop / "bims" / "docs"
    docs_dir.mkdir(parents=True)
    (docs_dir / "file.md").write_text("API routes: /users and /reports")
    (desktop / "bims" / "passwords.txt").write_text("secret123")
    (desktop / "bims" / ".env").write_text("TOKEN=abc")

    matches = fs.find_documents(
        desktop / "bims",
        "open bims/docs, find file.md and tell me what is written",
        desktop,
    )
    assert len(matches) == 1 and matches[0].name == "file.md"
    text, _ = fs.read_document(matches[0], desktop)
    assert "API routes" in text

    with pytest.raises(fs.PathError):
        fs.read_document(desktop / "bims" / "passwords.txt", desktop)
    with pytest.raises(fs.PathError):
        fs.read_document(desktop / "bims" / ".env", desktop)
