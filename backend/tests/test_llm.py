import asyncio
import stat
import sys
import textwrap
from pathlib import Path

import pytest

from backend.core.llm import AgyProvider, LLMError, parse_agy_json

FAKE_AGY = textwrap.dedent(
    """\
    #!{python}
    import json, os, sys
    args = sys.argv[1:]
    prompt = args[args.index("-p") + 1]
    fmt = args[args.index("--output-format") + 1]
    mode = os.environ.get("FAKE_MODE", "ok")
    if mode == "crash":
        sys.stderr.write("not signed in"); sys.exit(1)
    if mode == "json_empty" and fmt == "json":
        sys.exit(0)  # the "exit 0 but nothing on stdout" bug
    info = "key=" + ("present" if os.environ.get("GEMINI_API_KEY") else "absent")
    info += " cwd=" + os.path.basename(os.getcwd())
    info += " timeout=" + args[args.index("--print-timeout") + 1]
    answer = "answer[" + prompt.splitlines()[0][:20] + "] " + info
    print(json.dumps({{"response": answer}}) if fmt == "json" else answer)
    """
)


@pytest.fixture
def fake_agy(tmp_path):
    if sys.platform == "win32":
        # the real agy is a native .exe, so the stand-in is one too (pip's script launcher);
        # a .cmd wrapper would mangle the newlines and quotes these tests send
        from pip._vendor.distlib.scripts import ScriptMaker

        src = tmp_path / "src"
        src.mkdir()
        (src / "agy.py").write_text(FAKE_AGY.format(python="python"))  # "#!python": use maker.executable
        maker = ScriptMaker(str(src), str(tmp_path), add_launchers=True)
        maker.executable = sys.executable
        maker.variants = {""}
        return Path(maker.make("agy.py")[0])
    path = tmp_path / "agy"
    path.write_text(FAKE_AGY.format(python=sys.executable))
    path.chmod(path.stat().st_mode | stat.S_IEXEC)
    return path


def provider(fake, tmp_path, **kw):
    return AgyProvider(str(fake), timeout=20, scratch_dir=tmp_path / "scratch", **kw)


def test_json_mode_scrubs_api_keys_and_uses_scratch_cwd(fake_agy, tmp_path, monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "real-key-that-would-bill-you")
    out = asyncio.run(provider(fake_agy, tmp_path).complete("hello world\nsecond line"))
    assert out.startswith("answer[hello world]")
    assert "key=absent" in out and "cwd=scratch" in out and "timeout=20s" in out


def test_auto_falls_back_to_text_when_json_is_empty(fake_agy, tmp_path, monkeypatch):
    monkeypatch.setenv("FAKE_MODE", "json_empty")
    out = asyncio.run(provider(fake_agy, tmp_path).complete("hi"))
    assert out.startswith("answer[hi]")


def test_pinned_format_does_not_fall_back(fake_agy, tmp_path, monkeypatch):
    monkeypatch.setenv("FAKE_MODE", "json_empty")
    with pytest.raises(LLMError, match="empty"):
        asyncio.run(provider(fake_agy, tmp_path, fmt="json").complete("hi"))


def test_nonzero_exit_becomes_llm_error(fake_agy, tmp_path, monkeypatch):
    monkeypatch.setenv("FAKE_MODE", "crash")
    with pytest.raises(LLMError, match="not signed in"):
        asyncio.run(provider(fake_agy, tmp_path).complete("hi"))


def test_missing_binary_is_a_clear_error(tmp_path):
    with pytest.raises(LLMError, match="not found on PATH"):
        asyncio.run(AgyProvider("no-such-agy-binary", scratch_dir=tmp_path / "s").complete("hi"))


def test_parse_agy_json_shapes():
    assert parse_agy_json('{"response": " hi "}') == "hi"
    assert parse_agy_json('{"result": "r"}') == "r"
    assert parse_agy_json('{"usage": {}}') == ""
    assert parse_agy_json("plain text, not json") == "plain text, not json"
