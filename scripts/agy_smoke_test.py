#!/usr/bin/env python3
"""Probe how Antigravity CLI (agy) behaves when called from Python.

Standard library only. The prompts are harmless and run from an empty temp folder.

    python scripts/agy_smoke_test.py            # json + text + tricky-prompt probes
    python scripts/agy_smoke_test.py --pty      # also try a Windows ConPTY run (needs: pip install pywinpty)

Paste the whole output (or agy_smoke_result.txt) back into the chat.
"""
from __future__ import annotations

import argparse
import json
import os
import platform
import re
import secrets
import shutil
import subprocess
import sys
import tempfile
import time

SCRUB = ("GEMINI_API_KEY", "GOOGLE_API_KEY", "GOOGLE_CLOUD_PROJECT",
         "GOOGLE_GENAI_USE_VERTEXAI", "GOOGLE_APPLICATION_CREDENTIALS")
NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)
ANSI = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]|\x1b\][^\x07]*\x07")
LINES: list[str] = []


def say(text: str = "") -> None:
    print(text)
    LINES.append(text)


def clean_env() -> dict:
    return {k: v for k, v in os.environ.items() if k not in SCRUB}


def extract_json(stdout: str) -> str:
    try:
        data = json.loads(stdout)
    except ValueError:
        return stdout.strip()
    if isinstance(data, dict):
        for key in ("response", "result", "text", "output"):
            if isinstance(data.get(key), str) and data[key].strip():
                return data[key].strip()
        return ""
    return data.strip() if isinstance(data, str) else ""


def run(argv: list[str], cwd: str, timeout: int) -> dict:
    start = time.monotonic()
    try:
        proc = subprocess.run(argv, capture_output=True, cwd=cwd, env=clean_env(),
                              stdin=subprocess.DEVNULL, timeout=timeout, creationflags=NO_WINDOW)
    except subprocess.TimeoutExpired:
        return {"rc": None, "out": "", "err": "", "secs": time.monotonic() - start, "timeout": True}
    except OSError as exc:
        return {"rc": None, "out": "", "err": str(exc), "secs": time.monotonic() - start, "timeout": False}
    return {
        "rc": proc.returncode,
        "out": proc.stdout.decode("utf-8", errors="replace"),
        "err": proc.stderr.decode("utf-8", errors="replace"),
        "secs": time.monotonic() - start,
        "timeout": False,
    }


def verdict(name: str, token: str, r: dict, fmt: str) -> str:
    answer = extract_json(r["out"]) if fmt == "json" else r["out"].strip()
    if r["timeout"]:
        status = "FAIL (timed out)"
    elif r["rc"] != 0:
        status = f"FAIL (exit {r['rc']})"
    elif token in answer:
        status = "PASS"
    elif not r["out"].strip():
        status = "EMPTY (exit 0 but nothing on stdout)"
    else:
        status = "WRONG (output did not contain the token)"
    say(f"[{status}] {name}  ({r['secs']:.1f}s, stdout {len(r['out'])} chars)")
    if status != "PASS":
        say(f"    stdout head: {r['out'][:200]!r}")
        say(f"    stderr tail: {r['err'][-300:]!r}")
    return status


def probe_cli(exe: str, name: str, prompt: str, token: str, fmt: str, cwd: str, timeout: int) -> str:
    argv = [exe, "-p", prompt, "--output-format", fmt, "--print-timeout", f"{timeout}s"]
    return verdict(name, token, run(argv, cwd, timeout + 15), fmt)


def probe_pty(exe: str, prompt: str, token: str, cwd: str, timeout: int) -> str:
    try:
        from winpty import PtyProcess  # type: ignore
    except ImportError:
        say("[SKIP] pty/text  (pywinpty not installed: pip install pywinpty)")
        return "SKIP"
    start = time.monotonic()
    chunks: list[str] = []
    try:
        proc = PtyProcess.spawn([exe, "-p", prompt, "--output-format", "text"], cwd=cwd)
        while time.monotonic() - start < timeout:
            try:
                chunks.append(proc.read(4096))
            except EOFError:
                break
        proc.close()
    except Exception as exc:  # diagnostic script: report anything
        say(f"[FAIL] pty/text  ({exc!r})")
        return "FAIL"
    text = ANSI.sub("", "".join(chunks))
    ok = token in text
    say(f"[{'PASS' if ok else 'EMPTY/WRONG'}] pty/text  ({time.monotonic() - start:.1f}s, {len(text)} chars)")
    if not ok:
        say(f"    output head: {text[:200]!r}")
    return "PASS" if ok else "FAIL"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--timeout", type=int, default=90)
    parser.add_argument("--command", default="agy")
    parser.add_argument("--pty", action="store_true", help="also try a ConPTY run (Windows, needs pywinpty)")
    args = parser.parse_args()

    say(f"Python {sys.version.split()[0]} on {platform.platform()}")
    exe = shutil.which(args.command)
    say(f"agy path: {exe}")
    if exe is None:
        say("agy was not found on PATH. Open a new terminal after installing, or pass --command <full path>.")
        return 2

    scratch = tempfile.mkdtemp(prefix="nightmare-smoke-")
    ver = run([exe, "--version"], scratch, 30)
    say(f"agy --version: {ver['out'].strip() or ver['err'].strip()!r} (exit {ver['rc']})")
    say(f"scrubbed env vars present: {[k for k in SCRUB if k in os.environ] or 'none'}")
    say("")

    t1, t2, t3 = (f"NM_{secrets.token_hex(4)}" for _ in range(3))
    results = {
        "json": probe_cli(exe, "json/simple", f"Reply with exactly this token and nothing else: {t1}",
                          t1, "json", scratch, args.timeout),
        "text": probe_cli(exe, "text/simple", f"Reply with exactly this token and nothing else: {t2}",
                          t2, "text", scratch, args.timeout),
    }
    tricky = (f"Reply with just this token: {t3}\n"
              'Context line 1: "quoted" & ampersand | pipe 100% done\n'
              "Context line 2: ünïcode ✓")
    results["json_tricky"] = probe_cli(exe, "json/tricky (multi-line, quotes, & | %)", tricky,
                                       t3, "json", scratch, args.timeout)
    if args.pty:
        t4 = f"NM_{secrets.token_hex(4)}"
        results["pty"] = probe_pty(exe, f"Reply with exactly this token and nothing else: {t4}",
                                   t4, scratch, args.timeout)

    say("")
    if results["json"] == "PASS":
        say("RESULT: set AGY_FORMAT=json (or leave auto). Plain subprocess capture works.")
        if results["json_tricky"] != "PASS":
            say("NOTE: the tricky prompt failed. Special characters may break argv; tell me and I'll switch to stdin.")
    elif results["text"] == "PASS":
        say("RESULT: set AGY_FORMAT=text. JSON output did not work but text does.")
    elif results.get("pty") == "PASS":
        say("RESULT: plain capture fails but ConPTY works. Tell me and I'll add a pty strategy.")
    else:
        say("RESULT: no strategy worked. Paste this whole output into the chat.")

    try:
        with open("agy_smoke_result.txt", "w", encoding="utf-8") as fh:
            fh.write("\n".join(LINES) + "\n")
        say("(saved to agy_smoke_result.txt)")
    except OSError:
        pass
    shutil.rmtree(scratch, ignore_errors=True)
    return 0 if "PASS" in results.values() else 1


if __name__ == "__main__":
    sys.exit(main())
