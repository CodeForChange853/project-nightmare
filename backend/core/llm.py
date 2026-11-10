"""LLM providers. The orchestrator only sees the LLMProvider interface.

AgyProvider shells out to the Antigravity CLI (`agy -p`), which uses your signed-in
Google AI Pro account instead of an API key. Print mode auto-approves every tool call,
so this wrapper (1) runs agy from an empty scratch folder and (2) the prompts we send
tell it to use no tools. The model is never given a path or a shell by this app.
"""
from __future__ import annotations

import asyncio
import json
import os
import re
import shutil
import subprocess
import tempfile
import time
from pathlib import Path
from typing import AsyncIterator, Protocol

# If any of these are set, agy may bill an API/Cloud project instead of your subscription.
SCRUB_ENV = (
    "GEMINI_API_KEY",
    "GOOGLE_API_KEY",
    "GOOGLE_CLOUD_PROJECT",
    "GOOGLE_GENAI_USE_VERTEXAI",
    "GOOGLE_APPLICATION_CREDENTIALS",
)
NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


class LLMError(RuntimeError):
    pass


class LLMProvider(Protocol):
    name: str

    async def complete(self, prompt: str) -> str: ...


class NoLLMProvider:
    name = "none"

    async def complete(self, prompt: str) -> str:
        raise LLMError("the language model is turned off (LLM_ENABLED=0)")


def parse_agy_json(stdout: str) -> str:
    """Extract the answer from `agy -p --output-format json` output."""
    try:
        data = json.loads(stdout)
    except ValueError:
        return stdout.strip()
    if isinstance(data, dict):
        for key in ("response", "result", "text", "output"):
            value = data.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
        return ""
    if isinstance(data, str):
        return data.strip()
    return ""


DEEP_OR_CODE_RE = re.compile(
    r"\b("
    r"think\s+deeply|analyze\s+deeply|in-?depth|in\s+detail|detailed|deep\s+dive|elaborate|"
    r"code|script|python|javascript|implementation|function|class|method|program|syntax|snippet|"
    r"full\s+details|step-by-step"
    r")\b",
    re.I,
)

VOICE_CONCISENESS_CONSTRAINT = (
    "\n\n[STRICT VOICE CONCISENESS CONSTRAINT: You are speaking aloud to the user over voice. "
    "Limit your response strictly to 50-60 words (at most 2-3 crisp sentences). "
    "Never use markdown formatting, bullet points, numbered lists, or unnecessary introductory filler.]"
)


class AgyProvider:
    name = "agy"

    def __init__(
        self,
        command: str = "agy",
        timeout: int = 90,
        fmt: str = "auto",
        scratch_dir: Path | None = None,
        fast_model: str = "",
        smart_model: str = "",
    ):
        self.command = command
        self.timeout = timeout
        self.fmt = fmt
        self.fast_model = fast_model
        self.smart_model = smart_model
        self.scratch = Path(scratch_dir or Path(tempfile.gettempdir()) / "nightmare-agy-scratch")
        self.scratch.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def inject_conciseness(prompt: str, smart: bool = False) -> str:
        """Injects a strict conciseness cap for spoken/chat turns unless deep detail or code is requested."""
        if smart or DEEP_OR_CODE_RE.search(prompt):
            return prompt
        return f"{prompt}{VOICE_CONCISENESS_CONSTRAINT}"

    def _env(self) -> dict:
        return {k: v for k, v in os.environ.items() if k not in SCRUB_ENV}

    def _exec(self, exe: str, prompt: str, fmt: str, model: str = "") -> str:
        argv = [exe, "-p", prompt, "--output-format", fmt, "--print-timeout", f"{self.timeout}s"]
        if model:
            argv.extend(["--model", model, "--disable-slash-commands"])
        try:
            proc = subprocess.run(
                argv,
                capture_output=True,
                cwd=str(self.scratch),
                env=self._env(),
                stdin=subprocess.DEVNULL,
                timeout=self.timeout + 15,
                creationflags=NO_WINDOW,
            )
        except subprocess.TimeoutExpired as exc:
            raise LLMError(f"agy ({fmt}) timed out after {self.timeout}s") from exc
        except OSError as exc:
            raise LLMError(f"could not start agy: {exc}") from exc

        stdout = proc.stdout.decode("utf-8", errors="replace")
        if proc.returncode != 0:
            err = proc.stderr.decode("utf-8", errors="replace").strip()[-300:]
            raise LLMError(f"agy ({fmt}) exited {proc.returncode}: {err or 'no error text'}")
        return parse_agy_json(stdout) if fmt == "json" else stdout.strip()

    def _run_sync(self, prompt: str, smart: bool = False) -> str:
        exe = shutil.which(self.command)
        if exe is None:
            raise LLMError(f"'{self.command}' not found on PATH; is Antigravity CLI installed?")
        constrained_prompt = self.inject_conciseness(prompt, smart=smart)
        model = self.smart_model if smart else self.fast_model
        formats = ("json", "text") if self.fmt == "auto" else (self.fmt,)
        problems = []
        for fmt in formats:
            try:
                out = self._exec(exe, constrained_prompt, fmt, model=model)
            except LLMError as exc:
                problems.append(str(exc))
                continue
            if out:
                return out
            problems.append(f"agy ({fmt}) returned empty output")
        raise LLMError("; ".join(problems))

    def _run_stream_sync(self, prompt: str, smart: bool = False):
        exe = shutil.which(self.command)
        if exe is None:
            raise LLMError(f"'{self.command}' not found on PATH; is Antigravity CLI installed?")
        constrained_prompt = self.inject_conciseness(prompt, smart=smart)
        model = self.smart_model if smart else self.fast_model
        argv = [exe, "-p", constrained_prompt, "--output-format", "text", "--print-timeout", f"{self.timeout}s"]
        if model:
            argv.extend(["--model", model, "--disable-slash-commands"])
        try:
            proc = subprocess.Popen(
                argv,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                cwd=str(self.scratch),
                env=self._env(),
                creationflags=NO_WINDOW,
                bufsize=1,
            )
            for line in proc.stdout:
                yield line
            proc.wait()
        except Exception as exc:
            raise LLMError(f"Streaming from agy failed: {exc}") from exc

    async def complete(self, prompt: str, smart: bool = False) -> str:
        return await asyncio.to_thread(self._run_sync, prompt, smart)

    async def stream(self, prompt: str, smart: bool = False) -> AsyncIterator[str]:
        loop = asyncio.get_running_loop()
        queue: asyncio.Queue[str | Exception | None] = asyncio.Queue()

        def worker():
            try:
                for chunk in self._run_stream_sync(prompt, smart=smart):
                    loop.call_soon_threadsafe(queue.put_nowait, chunk)
            except Exception as e:
                loop.call_soon_threadsafe(queue.put_nowait, e)
            finally:
                loop.call_soon_threadsafe(queue.put_nowait, None)

        import threading
        t = threading.Thread(target=worker, daemon=True)
        t.start()
        while True:
            item = await queue.get()
            if item is None:
                break
            if isinstance(item, Exception):
                raise item
            yield item


def timed_ms(start: float) -> int:
    return int((time.monotonic() - start) * 1000)
