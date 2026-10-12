"""Document ingestion and hybrid retrieval with tenant scoping and injection flagging (Prompts 09–12).

Ingestion: parse -> chunk (with section/page provenance) -> flag instruction-like text -> embed. A document moves
PENDING -> PROCESSING -> READY, or FAILED with a safe error; ingesting the same content again into the same scope
returns the existing document instead of creating a duplicate.

Retrieval: access filters (organization, then organization-wide or this project's documents, READY only) are applied
in the database query, before any scoring. BM25 and vector similarity rank the allowed chunks, Reciprocal Rank
Fusion combines them, and a deterministic reranker orders the top candidates. Every hit carries its scores and
citation metadata.
"""

import hashlib
import logging
import math
import re
from collections import Counter
from dataclasses import dataclass, field
from datetime import UTC, date, datetime

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models import ChunkEmbedding, Document, DocumentChunk, DocumentStatus, Domain
from app.services import embeddings
from app.services.chunking import chunk_document
from app.services.parsing import ParsedDocument, ParsedPage, ParseError, parse_document

log = logging.getLogger("siteguard.rag")

MAX_CHUNK_CHARS = 900
RRF_K = 60
MIN_VECTOR_SIMILARITY = 0.15
_TOKEN = re.compile(r"[a-z0-9]+")
_STOP = set(
    "a an and are as at be by for from has have in is it its of on or that the this to was were will with "
    "shall must should be not no all any each per".split()
)
INJECTION_PATTERNS = [
    re.compile(p, re.I)
    for p in [
        r"ignore (all|any|the)? ?(previous|prior|above) (instructions|rules)",
        r"disregard (the|all|your) (instructions|rules|system)",
        r"system prompt",
        r"you are now",
        r"(auto[- ]?)?approve (this|all|the) (capa|action|incident)",
        r"close (this|the) incident (immediately|now)",
        r"reveal (your|the) (secret|api key|token|password)",
    ]
]


def tokenize(text: str) -> list[str]:
    return [t for t in _TOKEN.findall(text.lower()) if t not in _STOP and len(t) > 1]


def looks_like_injection(text: str) -> bool:
    return any(p.search(text) for p in INJECTION_PATTERNS)


def chunk_markdown(text: str) -> list[tuple[str, str]]:
    """Heading-aware chunks of a Markdown/text document as (section, text) pairs."""
    parsed = ParsedDocument("text", [ParsedPage(None, text)])
    return [(c.section, c.text) for c in chunk_document(parsed, "heading", MAX_CHUNK_CHARS)]


def _existing(db: Session, organization_id: str, project_id: str | None, sha256: str, version: str) -> Document | None:
    stmt = select(Document).where(
        Document.organization_id == organization_id,
        Document.sha256 == sha256,
        Document.version == version,
        Document.status == DocumentStatus.READY,
    )
    stmt = stmt.where(Document.project_id.is_(None) if project_id is None else Document.project_id == project_id)
    return db.scalar(stmt.limit(1))


def _process(db: Session, doc: Document, parsed: ParsedDocument) -> Document:
    s = get_settings()
    doc.status = DocumentStatus.PROCESSING
    doc.parser = parsed.parser
    doc.page_count = parsed.page_count
    db.flush()
    chunks = chunk_document(parsed, s.chunk_strategy, s.chunk_max_chars)
    if not chunks:
        raise ParseError("Document produced no text to index")
    rows = [
        DocumentChunk(
            document_id=doc.id,
            ordinal=c.ordinal,
            section=c.section[:300],
            page=c.page,
            text=c.text,
            content_sha256=embeddings.content_hash(c.text),
            suspicious=looks_like_injection(f"{doc.title}\n{c.section}\n{c.text}"),
        )
        for c in chunks
    ]
    db.add_all(rows)
    db.flush()
    embeddings.index_chunks(db, rows)
    doc.status = DocumentStatus.READY
    doc.processed_at = datetime.now(UTC)
    db.flush()
    db.refresh(doc)
    return doc


@dataclass
class IngestResult:
    document: Document
    duplicate: bool = False


def ingest_bytes(
    db: Session,
    *,
    organization_id: str,
    filename: str,
    content: bytes,
    title: str,
    doc_type: str,
    source: str,
    domain: Domain = Domain.BOTH,
    project_id: str | None = None,
    version: str = "1",
    content_type: str | None = None,
    effective_date: date | None = None,
    tags: list[str] | None = None,
    uploaded_by: str | None = None,
    storage_key: str | None = None,
) -> IngestResult:
    """Parse and index a document. Parse failures are recorded as FAILED documents, not raised."""
    digest = hashlib.sha256(content).hexdigest()
    found = _existing(db, organization_id, project_id, digest, version)
    if found is not None:
        return IngestResult(found, duplicate=True)
    doc = Document(
        organization_id=organization_id,
        project_id=project_id,
        title=title,
        doc_type=doc_type,
        source=source,
        version=version,
        domain=domain,
        sha256=digest,
        status=DocumentStatus.PENDING,
        file_name=filename,
        content_type=content_type,
        size_bytes=len(content),
        storage_key=storage_key,
        effective_date=effective_date,
        tags=sorted(set(tags or [])),
        uploaded_by=uploaded_by,
    )
    db.add(doc)
    db.flush()
    s = get_settings()
    try:
        parsed = parse_document(filename, content, timeout=s.parser_timeout_seconds, memory_mb=s.parser_memory_mb)
        return IngestResult(_process(db, doc, parsed))
    except Exception as exc:  # any parse or indexing failure is a FAILED document, never a lost upload
        if not isinstance(exc, ParseError):
            log.error("document processing failed", extra={"extra_fields": {"error": type(exc).__name__}})
        doc.status = DocumentStatus.FAILED
        doc.error = str(exc) if isinstance(exc, ParseError) else "Document could not be processed"
        doc.processed_at = datetime.now(UTC)
        db.flush()
        return IngestResult(doc)


def ingest(
    db: Session,
    *,
    organization_id: str,
    title: str,
    text: str,
    doc_type: str,
    source: str,
    domain: Domain = Domain.BOTH,
    project_id: str | None = None,
    version: str = "1",
    effective_date: date | None = None,
    tags: list[str] | None = None,
    uploaded_by: str | None = None,
) -> Document:
    """Ingest Markdown/plain text (seed data and the JSON documents endpoint)."""
    return ingest_bytes(
        db,
        organization_id=organization_id,
        filename="document.md",
        content=text.encode(),
        title=title,
        doc_type=doc_type,
        source=source,
        domain=domain,
        project_id=project_id,
        version=version,
        content_type="text/markdown",
        effective_date=effective_date,
        tags=tags,
        uploaded_by=uploaded_by,
    ).document


@dataclass
class Hit:
    chunk_id: str
    document_id: str
    document_title: str
    doc_type: str
    domain: str
    source: str
    section: str
    text: str
    score: float
    suspicious: bool
    page: int | None = None
    version: str = "1"
    effective_date: date | None = None
    tags: list[str] = field(default_factory=list)
    project_id: str | None = None
    scores: dict[str, float] = field(default_factory=dict)

    @property
    def ref(self) -> str:
        return f"chunk:{self.chunk_id}"

    def as_dict(self) -> dict:
        return {
            "ref": self.ref,
            "document_id": self.document_id,
            "document_title": self.document_title,
            "doc_type": self.doc_type,
            "domain": self.domain,
            "source": self.source,
            "section": self.section,
            "page": self.page,
            "version": self.version,
            "effective_date": self.effective_date.isoformat() if self.effective_date else None,
            "tags": self.tags,
            "scope": "project" if self.project_id else "organization",
            "project_id": self.project_id,
            "text": self.text,
            "score": round(self.score, 4),
            "scores": {k: round(v, 4) for k, v in self.scores.items()},
            "suspicious": self.suspicious,
        }


def _allowed(organization_id: str, project_id: str | None, domain: Domain | None):
    """The access filter. Every retrieval path starts from this statement."""
    stmt = (
        select(DocumentChunk, Document)
        .join(Document, DocumentChunk.document_id == Document.id)
        .where(Document.organization_id == organization_id, Document.status == DocumentStatus.READY)
    )
    if project_id:
        stmt = stmt.where(or_(Document.project_id.is_(None), Document.project_id == project_id))
    else:
        stmt = stmt.where(Document.project_id.is_(None))
    if domain and domain != Domain.BOTH:
        stmt = stmt.where(Document.domain.in_([domain, Domain.BOTH]))
    return stmt


def _bm25(rows: list, query: str) -> dict[str, float]:
    q_terms = set(tokenize(query))
    if not rows or not q_terms:
        return {}
    docs_tokens = [tokenize(f"{d.title} {c.section} {c.text}") for c, d in rows]
    n = len(rows)
    avgdl = sum(len(t) for t in docs_tokens) / n or 1.0
    df: Counter[str] = Counter()
    for toks in docs_tokens:
        df.update(set(toks))
    k1, b = 1.5, 0.75
    scores: dict[str, float] = {}
    for (chunk, _), toks in zip(rows, docs_tokens, strict=True):
        tf = Counter(toks)
        score = 0.0
        for term in q_terms & tf.keys():
            idf = math.log(1 + (n - df[term] + 0.5) / (df[term] + 0.5))
            score += idf * tf[term] * (k1 + 1) / (tf[term] + k1 * (1 - b + b * len(toks) / avgdl))
        if score > 0:
            scores[chunk.id] = score
    return scores


def _vector(db: Session, stmt, query: str, candidates: int) -> dict[str, float]:
    embedder = embeddings.get_embedder()
    qvec = embedder.embed([query])[0]
    if not any(qvec):
        return {}
    vstmt = stmt.join(ChunkEmbedding, ChunkEmbedding.chunk_id == DocumentChunk.id).where(
        ChunkEmbedding.model == embedder.name, ChunkEmbedding.model_version == embedder.version
    )
    if db.get_bind().dialect.name == "postgresql":
        from pgvector.sqlalchemy import Vector
        from sqlalchemy import Float, cast, literal

        distance = ChunkEmbedding.vector.op("<=>", return_type=Float())(cast(literal(str(qvec)), Vector()))
        rows = db.execute(
            vstmt.with_only_columns(DocumentChunk.id, distance.label("d")).order_by(distance).limit(candidates)
        ).all()
        sims = {cid: 1.0 - float(d) for cid, d in rows}
    else:
        rows = db.execute(vstmt.with_only_columns(DocumentChunk.id, ChunkEmbedding.vector)).all()
        sims = {cid: embeddings.cosine(qvec, vec) for cid, vec in rows}
    return {cid: s for cid, s in sims.items() if s >= MIN_VECTOR_SIMILARITY}


def _rank(scores: dict[str, float]) -> dict[str, int]:
    ordered = sorted(scores, key=lambda cid: (-scores[cid], cid))
    return {cid: i + 1 for i, cid in enumerate(ordered)}


def rerank_score(query: str, title: str, section: str, text: str) -> float:
    """Deterministic reranker: query coverage, heading match and phrase matches, each in [0, 1]."""
    q = [embeddings.stem(t) for t in tokenize(query)]
    if not q:
        return 0.0
    body = {embeddings.stem(t) for t in tokenize(text)}
    head = {embeddings.stem(t) for t in tokenize(f"{title} {section}")}
    coverage = sum(1 for t in set(q) if t in body or t in head) / len(set(q))
    heading = sum(1 for t in set(q) if t in head) / len(set(q))
    pairs = list(zip(q, q[1:], strict=False))
    body_seq = [embeddings.stem(t) for t in tokenize(text)]
    body_pairs = set(zip(body_seq, body_seq[1:], strict=False))
    phrase = sum(1 for p in pairs if p in body_pairs) / len(pairs) if pairs else 0.0
    return 0.6 * coverage + 0.25 * heading + 0.15 * phrase


def search(
    db: Session,
    *,
    organization_id: str,
    query: str,
    project_id: str | None = None,
    domain: Domain | None = None,
    limit: int = 5,
    mode: str | None = None,
) -> list[Hit]:
    """Hybrid (default) or lexical search over chunks the caller's scope allows."""
    mode = mode or get_settings().retrieval_mode
    stmt = _allowed(organization_id, project_id, domain)
    rows = list(db.execute(stmt).all())
    if not rows or not tokenize(query):
        return []
    by_id = {c.id: (c, d) for c, d in rows}
    lexical = _bm25(rows, query)
    vector = _vector(db, stmt, query, candidates=max(limit * 8, 40)) if mode == "hybrid" else {}
    lex_rank, vec_rank = _rank(lexical), _rank(vector)
    fused = {
        cid: sum(1.0 / (RRF_K + r[cid]) for r in (lex_rank, vec_rank) if cid in r) for cid in set(lexical) | set(vector)
    }
    if not fused:
        return []
    top = sorted(fused, key=lambda cid: (-fused[cid], cid))[: max(limit * 4, 20)]
    best = max(fused.values())
    hits: list[Hit] = []
    for cid in top:
        chunk, doc = by_id[cid]
        rr = rerank_score(query, doc.title, chunk.section, chunk.text)
        final = 0.5 * fused[cid] / best + 0.5 * rr
        hits.append(
            Hit(
                chunk.id,
                doc.id,
                doc.title,
                doc.doc_type,
                Domain(doc.domain).value,
                doc.source,
                chunk.section,
                chunk.text,
                final,
                chunk.suspicious,
                page=chunk.page,
                version=doc.version,
                effective_date=doc.effective_date,
                tags=list(doc.tags or []),
                project_id=doc.project_id,
                scores={
                    "bm25": lexical.get(cid, 0.0),
                    "vector": vector.get(cid, 0.0),
                    "fused": fused[cid],
                    "rerank": rr,
                },
            )
        )
    hits.sort(key=lambda h: (-h.score, h.chunk_id))
    return hits[:limit]
