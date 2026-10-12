"""Configurable chunking with provenance (Playbook Prompt 10).

Strategies:
- "heading": split at headings, then pack paragraphs up to max_chars. Chunks never cross a page boundary, so each
  keeps its page number. PDF headings are recognised from numbered ("3.2 Inspection") or upper-case lines.
- "page": one chunk per page, split at paragraph boundaries only when a page is longer than max_chars.
- "semantic": like "heading", but also starts a new chunk where consecutive paragraphs stop sharing vocabulary.

Paragraph blocks (tables, numbered instructions) are never split, so a block longer than max_chars becomes its own
chunk rather than being cut mid-row or mid-step.
"""

import re
from dataclasses import dataclass

from app.services.parsing import ParsedDocument, ParsedPage

STRATEGIES = ("heading", "page", "semantic")
_MD_HEADING = re.compile(r"^#{1,4}\s+(.*)")
_NUMBERED_HEADING = re.compile(r"^(\d+(\.\d+)*)\.?\s+[A-Z][^.!?]{1,80}$")
_WORD = re.compile(r"[a-z]{4,}")


@dataclass
class Chunk:
    ordinal: int
    section: str
    page: int | None
    text: str


def _heading(line: str, pdf: bool) -> str | None:
    m = _MD_HEADING.match(line)
    if m:
        return m.group(1).strip()
    stripped = line.strip()
    if pdf and stripped and len(stripped) <= 80:
        if _NUMBERED_HEADING.match(stripped):
            return stripped
        letters = [c for c in stripped if c.isalpha()]
        if len(letters) >= 4 and all(c.isupper() for c in letters):
            return stripped.title()
    return None


def _blocks(lines: list[str]) -> list[str]:
    return [b.strip() for b in re.split(r"\n\s*\n", "\n".join(lines)) if b.strip()]


def _shift(a: str, b: str) -> bool:
    """True when two paragraphs share almost no vocabulary (a topic boundary)."""
    wa, wb = set(_WORD.findall(a.lower())), set(_WORD.findall(b.lower()))
    if len(wa) < 5 or len(wb) < 5:
        return False
    return len(wa & wb) / len(wa | wb) < 0.05


def _pack(blocks: list[str], max_chars: int, semantic: bool) -> list[str]:
    out: list[str] = []
    buf = ""
    last = ""
    for block in blocks:
        boundary = semantic and buf and _shift(last, block)
        if buf and (len(buf) + len(block) > max_chars or boundary):
            out.append(buf)
            buf = ""
        buf = f"{buf}\n\n{block}" if buf else block
        last = block
    if buf:
        out.append(buf)
    return out


def _sections(page: ParsedPage, current: str, pdf: bool) -> tuple[list[tuple[str, list[str]]], str]:
    sections: list[tuple[str, list[str]]] = [(current, [])]
    for line in page.text.splitlines():
        title = _heading(line, pdf)
        if title:
            sections.append((title, []))
            if not pdf:
                continue
            # PDF heading lines stay in the text too (they carry the clause number used in citations).
        sections[-1][1].append(line)
    return [s for s in sections if any(line.strip() for line in s[1])], sections[-1][0]


def chunk_document(parsed: ParsedDocument, strategy: str = "heading", max_chars: int = 900) -> list[Chunk]:
    if strategy not in STRATEGIES:
        raise ValueError(f"Unknown chunking strategy {strategy!r}; use one of {', '.join(STRATEGIES)}")
    pdf = parsed.parser == "pdf"
    chunks: list[Chunk] = []
    current = "Introduction"
    for page in parsed.pages:
        if strategy == "page":
            label = f"Page {page.number}" if page.number else current
            for body in _pack(_blocks(page.text.splitlines()), max_chars, semantic=False):
                chunks.append(Chunk(len(chunks), label, page.number, body))
            continue
        sections, current = _sections(page, current, pdf)
        for title, lines in sections:
            for body in _pack(_blocks(lines), max_chars, semantic=strategy == "semantic"):
                chunks.append(Chunk(len(chunks), title, page.number, body))
    return chunks
