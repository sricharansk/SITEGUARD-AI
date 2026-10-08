"""Document ingestion and lexical (BM25) retrieval with tenant scoping and injection flagging.

pgvector/hybrid retrieval is the next step (docs/ROADMAP.md); the interface stays the same.
"""

import hashlib
import math
import re
from collections import Counter
from dataclasses import dataclass

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.models import Document, DocumentChunk, Domain

MAX_CHUNK_CHARS = 900
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
    """Split by headings, then by paragraphs so each chunk stays under MAX_CHUNK_CHARS."""
    sections: list[tuple[str, list[str]]] = [("Introduction", [])]
    for line in text.splitlines():
        m = re.match(r"^#{1,4}\s+(.*)", line)
        if m:
            sections.append((m.group(1).strip(), []))
        else:
            sections[-1][1].append(line)
    chunks: list[tuple[str, str]] = []
    for heading, lines in sections:
        buf = ""
        for para in re.split(r"\n\s*\n", "\n".join(lines)):
            para = para.strip()
            if not para:
                continue
            if buf and len(buf) + len(para) > MAX_CHUNK_CHARS:
                chunks.append((heading, buf))
                buf = ""
            buf = f"{buf}\n\n{para}" if buf else para
        if buf:
            chunks.append((heading, buf))
    return chunks


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
) -> Document:
    doc = Document(
        organization_id=organization_id,
        project_id=project_id,
        title=title,
        doc_type=doc_type,
        source=source,
        version=version,
        domain=domain,
        sha256=hashlib.sha256(text.encode()).hexdigest(),
    )
    db.add(doc)
    db.flush()
    for i, (section, body) in enumerate(chunk_markdown(text)):
        db.add(
            DocumentChunk(
                document_id=doc.id,
                ordinal=i,
                section=section,
                text=body,
                suspicious=looks_like_injection(body),
            )
        )
    db.flush()
    return doc


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
            "text": self.text,
            "score": round(self.score, 3),
            "suspicious": self.suspicious,
        }


def search(
    db: Session,
    *,
    organization_id: str,
    query: str,
    project_id: str | None = None,
    domain: Domain | None = None,
    limit: int = 5,
) -> list[Hit]:
    """BM25 over chunks visible to the organization (org-wide docs + the given project's docs)."""
    stmt = (
        select(DocumentChunk, Document)
        .join(Document, DocumentChunk.document_id == Document.id)
        .where(Document.organization_id == organization_id)
    )
    if project_id:
        stmt = stmt.where(or_(Document.project_id.is_(None), Document.project_id == project_id))
    else:
        stmt = stmt.where(Document.project_id.is_(None))
    if domain and domain != Domain.BOTH:
        stmt = stmt.where(Document.domain.in_([domain, Domain.BOTH]))
    rows = db.execute(stmt).all()
    q_terms = tokenize(query)
    if not rows or not q_terms:
        return []
    docs_tokens = [tokenize(f"{d.title} {c.section} {c.text}") for c, d in rows]
    n = len(rows)
    avgdl = sum(len(t) for t in docs_tokens) / n
    df: Counter[str] = Counter()
    for toks in docs_tokens:
        df.update(set(toks))
    k1, b = 1.5, 0.75
    hits: list[Hit] = []
    for (chunk, doc), toks in zip(rows, docs_tokens, strict=True):
        tf = Counter(toks)
        score = 0.0
        for term in set(q_terms):
            if term not in tf:
                continue
            idf = math.log(1 + (n - df[term] + 0.5) / (df[term] + 0.5))
            score += idf * tf[term] * (k1 + 1) / (tf[term] + k1 * (1 - b + b * len(toks) / avgdl))
        if score > 0:
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
                    score,
                    chunk.suspicious,
                )
            )
    hits.sort(key=lambda h: (-h.score, h.chunk_id))
    return hits[:limit]
