"""Evidence upload validation and storage. Files are stored outside the DB under random keys."""

import hashlib
import re
import uuid
from pathlib import Path

from app.core.config import get_settings
from app.core.errors import AppError

ALLOWED = {
    ".jpg": ("image/jpeg", [b"\xff\xd8\xff"]),
    ".jpeg": ("image/jpeg", [b"\xff\xd8\xff"]),
    ".png": ("image/png", [b"\x89PNG\r\n\x1a\n"]),
    ".pdf": ("application/pdf", [b"%PDF-"]),
    ".txt": ("text/plain", []),
}


def safe_filename(name: str) -> str:
    base = Path(name or "upload").name
    return re.sub(r"[^A-Za-z0-9._-]+", "_", base)[:200] or "upload"


def validate(filename: str, declared_type: str | None, content: bytes) -> tuple[str, str]:
    """Return (safe_filename, content_type) or raise. Checks extension, declared MIME, size and magic bytes."""
    s = get_settings()
    name = safe_filename(filename)
    ext = Path(name).suffix.lower()
    if ext not in ALLOWED:
        raise AppError(f"File type {ext or '(none)'} is not allowed", "UNSUPPORTED_FILE")
    content_type, magics = ALLOWED[ext]
    if declared_type and declared_type not in (content_type, "application/octet-stream"):
        raise AppError("Declared content type does not match the file extension", "UNSUPPORTED_FILE")
    if not content:
        raise AppError("File is empty", "UNSUPPORTED_FILE")
    if len(content) > s.evidence_max_bytes:
        raise AppError(f"File exceeds {s.evidence_max_bytes} bytes", "FILE_TOO_LARGE", 413)
    if magics and not any(content.startswith(m) for m in magics):
        raise AppError("File content does not match its type", "UNSUPPORTED_FILE")
    if ext == ".txt":
        try:
            content.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise AppError("Text evidence must be UTF-8", "UNSUPPORTED_FILE") from exc
    return name, content_type


def store(organization_id: str, incident_id: str, content: bytes) -> tuple[str, str]:
    """Write bytes under a random key; return (storage_key, sha256)."""
    key = f"{organization_id}/{incident_id}/{uuid.uuid4().hex}"
    path = get_settings().evidence_dir / key
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    return key, hashlib.sha256(content).hexdigest()


def path_for(storage_key: str) -> Path:
    return get_settings().evidence_dir / storage_key
