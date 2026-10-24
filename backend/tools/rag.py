"""Local Project Knowledge RAG (Retrieval-Augmented Generation / Semantic Search).

Indexes safe project documentation (handoff.md, README.md, .md, .txt) across Desktop
projects using FastEmbed ONNX embeddings in memory. Caches by file mtime_ns so re-indexing
is fast and non-blocking.
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass
import logging
from pathlib import Path
import re
import time

from ..tools.fs_reader import PathError, _iter_safe_docs, list_projects, safe_path

logger = logging.getLogger("nightmare.rag")

CHUNK_SIZE = 400
CHUNK_OVERLAP = 80


@dataclass
class DocChunk:
    project: str
    rel_path: str
    text: str


@dataclass
class SearchHit:
    project: str
    rel_path: str
    snippet: str
    score: float


def chunk_text(text: str, max_chars: int = CHUNK_SIZE, overlap: int = CHUNK_OVERLAP) -> list[str]:
    """Split text into readable paragraph chunks with overlap."""
    clean = text.strip()
    if not clean:
        return []
    # Split by double newlines (paragraphs) first
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", clean) if p.strip()]
    chunks: list[str] = []
    
    current = ""
    for p in paragraphs:
        if len(p) > max_chars:
            # Paragraph is long, split by sentences or chunks
            words = p.split()
            buf = []
            buf_len = 0
            for w in words:
                buf.append(w)
                buf_len += len(w) + 1
                if buf_len >= max_chars:
                    chunks.append(" ".join(buf))
                    # keep overlap words
                    overlap_words = buf[-int(overlap / 6):] if len(buf) > 10 else []
                    buf = list(overlap_words)
                    buf_len = sum(len(x) + 1 for x in buf)
            if buf:
                chunks.append(" ".join(buf))
        else:
            if current and len(current) + len(p) + 2 > max_chars:
                chunks.append(current)
                current = p
            else:
                current = f"{current}\n\n{p}".strip()
    if current:
        chunks.append(current)
    return chunks


class ProjectRAG:
    """Indexes Desktop project docs into CPU embeddings and provides fast semantic search."""

    def __init__(self, desktop_root: Path, model_name: str = "BAAI/bge-small-en-v1.5"):
        self.desktop_root = Path(desktop_root)
        self.model_name = model_name
        self._model = None
        self._chunks: list[DocChunk] = []
        self._embs_norm = None
        self._file_cache: dict[tuple[str, int], list[DocChunk]] = {}  # (path_str, mtime_ns) -> chunks
        self._indexed_mtimes: dict[str, int] = {}

    def _get_model(self):
        if self._model is not None:
            return self._model
        try:
            # Share model with semantic router if already loaded
            from ..core.semantic_router import get_semantic_router
            sr = get_semantic_router()
            if sr._ensure_initialized() and sr._model is not None:
                self._model = sr._model
                return self._model
        except Exception:
            pass

        try:
            from fastembed import TextEmbedding
            self._model = TextEmbedding(model_name=self.model_name)
            return self._model
        except Exception as exc:
            logger.warning("Could not load embedding model for RAG: %s", exc)
            return None

    def index_all(self) -> int:
        """Scan desktop project docs and build in-memory embedding matrix."""
        model = self._get_model()
        if model is None:
            return 0

        try:
            projects = list_projects(self.desktop_root)
        except (PathError, OSError):
            return 0

        all_chunks: list[DocChunk] = []
        for project in projects:
            try:
                for doc in _iter_safe_docs(project, self.desktop_root):
                    if not doc.is_file():
                        continue
                    try:
                        mtime = doc.stat().st_mtime_ns
                    except OSError:
                        continue
                    cache_key = (str(doc), mtime)
                    if cache_key in self._file_cache:
                        all_chunks.extend(self._file_cache[cache_key])
                        continue
                    try:
                        content = doc.read_text(encoding="utf-8", errors="replace")
                    except OSError:
                        continue
                    rel = str(doc.relative_to(project))
                    doc_chunks = [
                        DocChunk(project=project.name, rel_path=rel, text=ch)
                        for ch in chunk_text(content)
                    ]
                    self._file_cache[cache_key] = doc_chunks
                    all_chunks.extend(doc_chunks)
            except (PathError, OSError):
                continue

        if not all_chunks:
            self._chunks = []
            self._embs_norm = None
            return 0

        try:
            import numpy as np
            texts = [c.text for c in all_chunks]
            embs = np.array(list(model.embed(texts)))
            norms = np.linalg.norm(embs, axis=1, keepdims=True)
            self._embs_norm = embs / np.maximum(norms, 1e-9)
            self._chunks = all_chunks
            return len(all_chunks)
        except Exception as exc:
            logger.warning("Failed to embed RAG chunks: %s", exc)
            return 0

    async def search(self, query: str, top_k: int = 3, threshold: float = 0.60) -> list[SearchHit]:
        """Perform semantic search across indexed project documents."""
        clean = " ".join(query.strip().split())
        if not clean:
            return []

        # Run index in thread if not indexed or stale
        await asyncio.to_thread(self.index_all)

        if not self._chunks or self._embs_norm is None:
            return []

        model = self._get_model()
        if model is None:
            return []

        def _calc_hits() -> list[SearchHit]:
            import numpy as np
            q_emb = np.array(list(model.embed([clean])))[0]
            norm = np.linalg.norm(q_emb)
            if norm == 0:
                return []
            q_emb_norm = q_emb / norm
            sims = np.dot(self._embs_norm, q_emb_norm)

            top_indices = np.argsort(sims)[::-1][:top_k]
            hits = []
            for idx in top_indices:
                score = float(sims[idx])
                if score >= threshold:
                    chunk = self._chunks[idx]
                    snippet = " ".join(chunk.text.split())
                    if len(snippet) > 220:
                        snippet = snippet[:220].rstrip() + "..."
                    hits.append(SearchHit(
                        project=chunk.project,
                        rel_path=chunk.rel_path,
                        snippet=snippet,
                        score=score,
                    ))
            return hits

        return await asyncio.to_thread(_calc_hits)
