import asyncio
import os
import time

from backend.core.actions import PendingStore
from backend.core.llm import LLMProvider
from backend.core.orchestrator import Orchestrator
from backend.tools.audit import Audit


class CountingProvider(LLMProvider):
    name = "fake"

    def __init__(self):
        self.calls = 0

    async def complete(self, prompt, **kw):
        self.calls += 1
        return "A summary."


def _make(settings, registry):
    provider = CountingProvider()
    return Orchestrator(settings, provider, registry, Audit(settings.db_path)), provider


def _age(settings):
    old = time.time() - 3600
    for f in settings.desktop_root.rglob("handoff.md"):
        os.utime(f, (old, old))


def test_summary_survives_restart(settings, registry):
    _age(settings)
    orch, provider = _make(settings, registry)
    asyncio.run(orch.handle("progress of bims"))
    assert provider.calls == 1
    orch2, provider2 = _make(settings, registry)  # fresh process, same database
    reply = asyncio.run(orch2.handle("progress of bims"))
    assert provider2.calls == 0 and "A summary." in reply.text


def test_refresher_prewarms_then_answers_instantly(settings, registry):
    _age(settings)
    orch, provider = _make(settings, registry)
    made = 0
    while asyncio.run(orch.refresh_summaries_once()):
        made += 1
    assert made >= 2  # bims + citizengraph handoffs (about falls back to the handoff)
    calls = provider.calls
    asyncio.run(orch.handle("progress of bims"))
    assert provider.calls == calls


def test_refresher_skips_files_being_edited(settings, registry):
    orch, provider = _make(settings, registry)  # files were just written
    assert asyncio.run(orch.refresh_summaries_once()) is False
    assert provider.calls == 0
