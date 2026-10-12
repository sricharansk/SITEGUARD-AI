"""Embeddings for vector retrieval (Playbook Prompt 11).

`Embedder` is the provider interface. The default `HashingEmbedder` is offline and deterministic: it hashes
stemmed words and word pairs into a fixed-size, L2-normalised vector. It captures lexical overlap that BM25 misses
(word forms, phrases) but not meaning; a semantic embedding model plugs in behind the same interface once one is
chosen (open decision O5 in docs/DECISIONS.md).

Indexing is idempotent: a chunk is embedded once per (model, model_version) and re-embedded only when its
content checksum changes.
"""

import hashlib
import logging
import math
import re
import time
from collections import Counter
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Protocol

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models import ChunkEmbedding, Document, DocumentChunk, DocumentStatus

log = logging.getLogger("siteguard.embeddings")

_WORD = re.compile(r"[a-z0-9]+")
_STOP = set(
    "a an and are as at be by for from has have in is it its of on or that the this to was were will with "
    "shall must should not no all any each per".split()
)


class Embedder(Protocol):
    name: str
    version: str
    dim: int

    def embed(self, texts: Sequence[str]) -> list[list[float]]: ...


_SUFFIXES = ("ations", "ation", "ated", "ates", "ate", "ions", "ion", "ings", "ing", "ers", "er", "ed", "es", "s")


def stem(word: str) -> str:
    """Light suffix stripping so inspect/inspected/inspection and excavate/excavated/excavations share a stem."""
    if word.endswith("es") and word[:-2].endswith(("ss", "x", "z", "ch", "sh")) and len(word) >= 5:
        return word[:-2]  # boxes -> box, trenches -> trench; slopes falls through to -> slope
    for suffix in _SUFFIXES:
        if word.endswith(suffix) and len(word) - len(suffix) >= 4 and not (suffix == "s" and word.endswith("ss")):
            word = word[: -len(suffix) if suffix != "es" else -1]
            break
    return word[:-1] if word.endswith("e") and len(word) >= 5 else word


def features(text: str) -> Counter[str]:
    words = [stem(w) for w in _WORD.findall(text.lower()) if w not in _STOP and len(w) > 1]
    feats: Counter[str] = Counter(words)
    feats.update(f"{a}_{b}" for a, b in zip(words, words[1:], strict=False))
    return feats


class HashingEmbedder:
    name = "hashing-bow"
    version = "1"

    def __init__(self, dim: int = 384):
        self.dim = dim

    def _vector(self, text: str) -> list[float]:
        vec = [0.0] * self.dim
        for feat, count in features(text).items():
            h = int.from_bytes(hashlib.blake2b(feat.encode(), digest_size=8).digest(), "big")
            weight = (1.0 + math.log(count)) * (0.5 if "_" in feat else 1.0)
            vec[h % self.dim] += weight if (h >> 32) & 1 else -weight
        norm = math.sqrt(sum(v * v for v in vec))
        return [v / norm for v in vec] if norm else vec

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        return [self._vector(t) for t in texts]


def get_embedder() -> Embedder:
    provider = get_settings().embedding_provider
    if provider == "hashing":
        return HashingEmbedder()
    raise ValueError(f"Unknown embedding provider {provider!r}")


def cosine(a: Sequence[float], b: Sequence[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b, strict=False))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    return dot / (na * nb) if na and nb else 0.0


def content_hash(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


@dataclass
class IndexReport:
    embedded: int = 0
    skipped: int = 0
    failed: int = 0


def _with_retries(fn: Callable[[], list[list[float]]], attempts: int, sleep: Callable[[float], None]):
    delay = 0.5
    for attempt in range(1, attempts + 1):
        try:
            return fn()
        except Exception as exc:  # provider errors are retried, then reported as failed chunks
            if attempt == attempts:
                raise
            log.warning("embedding batch failed, retrying", extra={"extra_fields": {"error": type(exc).__name__}})
            sleep(delay)
            delay *= 2
    raise AssertionError("unreachable")


def index_chunks(
    db: Session,
    chunks: Sequence[DocumentChunk],
    *,
    embedder: Embedder | None = None,
    batch_size: int = 64,
    attempts: int = 3,
    sleep: Callable[[float], None] = time.sleep,
) -> IndexReport:
    """Embed chunks that have no current embedding. Safe to run repeatedly (idempotent)."""
    embedder = embedder or get_embedder()
    report = IndexReport()
    ids = [c.id for c in chunks]
    existing = {
        e.chunk_id: e
        for e in db.scalars(
            select(ChunkEmbedding).where(
                ChunkEmbedding.chunk_id.in_(ids),
                ChunkEmbedding.model == embedder.name,
                ChunkEmbedding.model_version == embedder.version,
            )
        )
    }
    todo: list[DocumentChunk] = []
    for chunk in chunks:
        digest = content_hash(chunk.text)  # always from the text, so edited chunks are re-embedded
        chunk.content_sha256 = digest
        current = existing.get(chunk.id)
        if current is not None and current.content_sha256 == digest:
            report.skipped += 1
            continue
        todo.append(chunk)
    for start in range(0, len(todo), batch_size):
        batch = todo[start : start + batch_size]
        try:
            texts = [c.text for c in batch]
            vectors = _with_retries(lambda t=texts: embedder.embed(t), attempts, sleep)  # type: ignore[misc]
            if len(vectors) != len(batch) or any(len(v) != embedder.dim for v in vectors):
                raise ValueError(f"embedder returned wrong shape (expected {len(batch)} x {embedder.dim})")
        except Exception as exc:
            log.error("embedding batch failed", extra={"extra_fields": {"error": type(exc).__name__}})
            report.failed += len(batch)
            for chunk in batch:  # a vector for old content must not be served for new content
                if chunk.id in existing:
                    db.delete(existing.pop(chunk.id))
            continue
        for chunk, vector in zip(batch, vectors, strict=True):
            row = existing.get(chunk.id)
            if row is None:
                row = ChunkEmbedding(chunk_id=chunk.id, model=embedder.name, model_version=embedder.version)
                db.add(row)
            row.dim, row.vector = embedder.dim, vector
            row.content_sha256 = chunk.content_sha256 or content_hash(chunk.text)
        report.embedded += len(batch)
    db.flush()
    return report


def index_pending(db: Session, *, embedder: Embedder | None = None, organization_id: str | None = None) -> IndexReport:
    """Batch job: embed every chunk of READY documents that lacks a current embedding."""
    stmt = (
        select(DocumentChunk)
        .join(Document, Document.id == DocumentChunk.document_id)
        .where(Document.status == DocumentStatus.READY)
    )
    if organization_id:
        stmt = stmt.where(Document.organization_id == organization_id)
    return index_chunks(db, list(db.scalars(stmt.order_by(DocumentChunk.id))), embedder=embedder)
