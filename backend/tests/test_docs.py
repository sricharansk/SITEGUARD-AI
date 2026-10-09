"""Keeps the source-of-truth documents in step with the code (Playbook Prompt 01)."""

import ast
import re

from app.core.config import REPO_ROOT
from app.main import app
from app.models import Role

DOCS = REPO_ROOT / "docs"
SOURCE_OF_TRUTH = [
    "PRD.md",
    "DESIGN_SYSTEM.md",
    "UX_FLOWS.md",
    "ARCHITECTURE.md",
    "DATABASE.md",
    "API.md",
    "SECURITY.md",
    "CODE_STYLE.md",
    "TESTING.md",
    "ENVIRONMENT.md",
    "ERROR_HANDLING.md",
    "DEPLOYMENT.md",
    "OBSERVABILITY.md",
    "DECISIONS.md",
    "ROADMAP.md",
    "CHANGELOG.md",
    "AGENTS.md",
    "DATASETS.md",
    "PROJECT_STATUS.md",
]
ERROR_CLASSES = {"AppError", "NotFound", "Forbidden", "Conflict"}


def _normalize(path: str) -> str:
    return re.sub(r"\{[^}]*\}", "{}", path)


def _error_codes() -> set[str]:
    app_dir = REPO_ROOT / "backend" / "app"
    errors_py = app_dir / "core" / "errors.py"
    codes = {
        n.value
        for n in ast.walk(ast.parse(errors_py.read_text()))
        if isinstance(n, ast.Constant) and isinstance(n.value, str) and re.fullmatch(r"[A-Z_]{4,}", n.value)
    }
    for f in app_dir.rglob("*.py"):
        for node in ast.walk(ast.parse(f.read_text())):
            if not (isinstance(node, ast.Call) and getattr(node.func, "id", None) in ERROR_CLASSES):
                continue
            args = node.args[1:2] + [k.value for k in node.keywords if k.arg == "code"]
            codes |= {a.value for a in args if isinstance(a, ast.Constant) and isinstance(a.value, str)}
    return codes


def test_source_of_truth_documents_exist():
    missing = [name for name in SOURCE_OF_TRUTH if not (DOCS / name).is_file()]
    assert not missing, missing


def test_every_route_is_documented_in_api_md():
    documented = {_normalize(p) for p in re.findall(r"(/[a-z][a-z0-9/{}_-]*)", (DOCS / "API.md").read_text())}
    routes = {_normalize(path) for path in app.openapi()["paths"]}
    assert len(routes) > 20  # the route scan itself works
    assert routes - documented == set(), "add these routes to docs/API.md"


def test_every_role_is_documented_in_security_md():
    text = (DOCS / "SECURITY.md").read_text()
    assert [r.value for r in Role if r.value not in text] == []


def test_every_error_code_is_documented_in_api_md():
    text = (DOCS / "API.md").read_text()
    codes = _error_codes()
    assert {"RATE_LIMITED", "CLOSE_BLOCKED", "NOT_FOUND"} <= codes  # the scan itself works
    assert sorted(c for c in codes if f"`{c}`" not in text) == []
