"""Back up and restore a Site Guard AI deployment: the PostgreSQL database plus the evidence directory, with checksums.

    python scripts/backup.py backup  --evidence-dir /srv/evidence --out /backups/2026-10-09T1200Z
    python scripts/backup.py restore --backup /backups/2026-10-09T1200Z --evidence-dir /srv/evidence-restored
    python scripts/backup.py verify  --evidence-dir /srv/evidence-restored [--manifest <backup>/manifest.json]

Database URLs are read from environment variables, never from the command line (process listings show arguments):
SITEGUARD_DATABASE_URL for `backup` and `verify`, SITEGUARD_RESTORE_DATABASE_URL for `restore` (change either with
--database-url-env). Both the application form (postgresql+psycopg://...) and plain postgresql:// URLs work.

Needs only Python 3.11+ and the PostgreSQL client tools (pg_dump, pg_restore, psql) of the same major version as
the server (--pg-bin selects a directory). A backup directory holds:

    database.dump     pg_dump custom format (--no-owner --no-acl), restorable into an empty database by any role
    evidence.tar.gz   every file under the evidence directory (incident evidence and original knowledge documents)
    manifest.json     SHA-256 and size of both, per-file evidence hashes, row counts per table, Alembic revision

`restore` checks every checksum before touching anything, refuses a database or evidence directory that is not
empty, restores in one transaction, then runs `verify`. `verify` checks that each evidence and document row has its
file and that the file's SHA-256 matches the hash recorded in the database (and, with --manifest, that row counts
and revision match the backup). Exit code 0 on success, 1 on any failure. The database is dumped before the
evidence is archived: evidence files are written before their rows commit and are never modified, so every row in
the dump has its file in the archive. Backups contain incident data and personal data: keep them encrypted at rest
with restricted access (docs/GOVERNANCE.md).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tarfile
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from urllib.parse import parse_qs, unquote, urlsplit

FORMAT = "siteguard-backup/1"
DUMP_FILE = "database.dump"
EVIDENCE_FILE = "evidence.tar.gz"
MANIFEST_FILE = "manifest.json"
# Rows whose storage_key names a file under the evidence directory, with the SHA-256 recorded at upload.
STORED_FILES = {
    "evidence": "select storage_key, sha256 from evidence order by storage_key",
    "documents": "select storage_key, sha256 from documents where storage_key is not null order by storage_key",
}
SEP = "\x1f"  # psql field separator (storage keys never contain it)


class BackupError(Exception):
    """A check failed; the message says which and the command exits 1."""


# -- connection --------------------------------------------------------------------------------------------------


def libpq_env(url: str) -> dict[str, str]:
    """Translate a database URL into libpq environment variables, so the password never appears in argv."""
    parts = urlsplit(url)
    scheme = parts.scheme.split("+", 1)[0]
    if scheme not in ("postgresql", "postgres"):
        raise BackupError(f"only PostgreSQL URLs are supported (got {scheme or 'no'} scheme)")
    database = unquote(parts.path.lstrip("/"))
    if not database:
        raise BackupError("the database URL has no database name")
    env = {"PGDATABASE": database}
    if parts.hostname:
        env["PGHOST"] = parts.hostname
    if parts.port:
        env["PGPORT"] = str(parts.port)
    if parts.username:
        env["PGUSER"] = unquote(parts.username)
    if parts.password:
        env["PGPASSWORD"] = unquote(parts.password)
    query = parse_qs(parts.query)
    for key, var in (
        ("sslmode", "PGSSLMODE"),
        ("sslrootcert", "PGSSLROOTCERT"),
        ("connect_timeout", "PGCONNECT_TIMEOUT"),
    ):
        if key in query:
            env[var] = query[key][-1]
    env.setdefault("PGCONNECT_TIMEOUT", "15")
    return env


class Postgres:
    """Runs the PostgreSQL client tools against one database (connection from libpq environment variables)."""

    def __init__(self, url: str, pg_bin: str | None = None):
        self.env = {**os.environ, **libpq_env(url)}
        self.database = self.env["PGDATABASE"]
        self.pg_bin = pg_bin

    def tool(self, name: str) -> str:
        path = shutil.which(name, path=self.pg_bin) if self.pg_bin else shutil.which(name)
        if not path:
            raise BackupError(f"{name} not found (install the PostgreSQL client tools or pass --pg-bin)")
        return path

    def run(self, args: list[str], **kw) -> subprocess.CompletedProcess[str]:
        proc = subprocess.run(args, env=self.env, capture_output=True, text=True, check=False, **kw)
        if proc.returncode != 0:
            raise BackupError(f"{Path(args[0]).name} failed: {proc.stderr.strip()[-2000:]}")
        return proc

    def query(self, sql: str) -> list[list[str]]:
        out = self.run([self.tool("psql"), "-X", "-q", "-A", "-t", "-F", SEP, "-v", "ON_ERROR_STOP=1", "-c", sql])
        return [line.split(SEP) for line in out.stdout.splitlines() if line]

    def tables(self) -> list[str]:
        rows = self.query("select tablename from pg_tables where schemaname = current_schema() order by tablename")
        return [r[0] for r in rows]

    def row_counts(self) -> dict[str, int]:
        tables = self.tables()
        if not tables:
            return {}
        sql = " union all ".join(f"select {quote_literal(t)}, count(*) from {quote_ident(t)}" for t in tables)
        return {name: int(count) for name, count in self.query(sql)}

    def alembic_revision(self) -> str | None:
        if "alembic_version" not in self.tables():
            return None
        rows = self.query("select version_num from alembic_version")
        return rows[0][0] if rows else None

    def stored_files(self) -> dict[str, list[tuple[str, str]]]:
        # Only tables that have a storage_key column at this schema revision (documents gains one with uploads).
        cols = self.query(
            "select table_name from information_schema.columns "
            "where table_schema = current_schema() and column_name = 'storage_key'"
        )
        with_files = {r[0] for r in cols}
        return {t: [(k, h) for k, h in self.query(sql)] for t, sql in STORED_FILES.items() if t in with_files}

    def server_version(self) -> str:
        return self.query("show server_version")[0][0]


def quote_ident(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def quote_literal(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def database_url(env_name: str) -> str:
    url = os.environ.get(env_name, "")
    if not url:
        raise BackupError(f"set {env_name} to the database URL")
    return url


# -- files -------------------------------------------------------------------------------------------------------


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def evidence_files(root: Path) -> dict[str, dict[str, int | str]]:
    """Every regular file under root, keyed by its POSIX path relative to root. Symbolic links are refused."""
    files: dict[str, dict[str, int | str]] = {}
    if not root.exists():
        return files
    for path in sorted(root.rglob("*")):
        if path.is_symlink():
            raise BackupError(f"symbolic link in the evidence directory: {path}")
        if path.is_file():
            rel = path.relative_to(root).as_posix()
            files[rel] = {"sha256": sha256_file(path), "size": path.stat().st_size}
    return files


def write_archive(root: Path, files: dict[str, dict[str, int | str]], archive: Path) -> None:
    with tarfile.open(archive, "w:gz") as tar:
        for rel in files:
            info = tar.gettarinfo(str(root / rel), arcname=rel)
            info.uid = info.gid = 0
            info.uname = info.gname = ""
            info.mode = 0o640
            with (root / rel).open("rb") as f:
                tar.addfile(info, f)


def extract_archive(archive: Path, target: Path, expected: dict[str, dict[str, int | str]]) -> None:
    """Extract only regular files whose names are safe relative paths listed in the manifest."""
    with tarfile.open(archive, "r:gz") as tar:
        members = tar.getmembers()
        for m in members:
            name = PurePosixPath(m.name)
            if not m.isfile() or name.is_absolute() or ".." in name.parts or m.name not in expected:
                raise BackupError(f"unexpected entry in the evidence archive: {m.name!r}")
        tar.extractall(target, members=members, filter="data")


def check_file(path: Path, expected_sha256: str, expected_size: int | None = None) -> None:
    if not path.is_file():
        raise BackupError(f"missing file: {path}")
    if expected_size is not None and path.stat().st_size != expected_size:
        raise BackupError(f"size mismatch: {path}")
    if sha256_file(path) != expected_sha256:
        raise BackupError(f"SHA-256 mismatch: {path}")


def file_problems(stored: dict[str, list[tuple[str, str]]], root: Path) -> list[str]:
    """Rows whose file is missing under root or whose SHA-256 differs from the hash recorded in the database."""
    problems = []
    for table, rows in stored.items():
        for key, recorded in rows:
            rel = PurePosixPath(key)
            if rel.is_absolute() or ".." in rel.parts:
                problems.append(f"{table}: unsafe storage key {key!r}")
                continue
            path = root / rel
            if not path.is_file():
                problems.append(f"{table}: missing file {key}")
            elif sha256_file(path) != recorded:
                problems.append(f"{table}: SHA-256 mismatch for {key}")
    return problems


def count_problems(expected: dict[str, int], actual: dict[str, int]) -> list[str]:
    problems = []
    for table in sorted(set(expected) | set(actual)):
        if expected.get(table) != actual.get(table):
            problems.append(f"row count for {table}: backup {expected.get(table)}, database {actual.get(table)}")
    return problems


def tool_version(pg: Postgres, name: str) -> str:
    return pg.run([pg.tool(name), "--version"]).stdout.strip()


def private_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)
    path.chmod(0o700)


# -- commands ----------------------------------------------------------------------------------------------------


def backup(args: argparse.Namespace) -> dict:
    pg = Postgres(database_url(args.database_url_env), args.pg_bin)
    out: Path = args.out
    if out.exists() and any(out.iterdir()):
        raise BackupError(f"backup directory is not empty: {out}")
    evidence_root: Path = args.evidence_dir
    if not evidence_root.is_dir():
        raise BackupError(f"evidence directory not found: {evidence_root}")
    private_dir(out)
    old_umask = os.umask(0o077)
    try:
        dump = out / DUMP_FILE
        # Database first: evidence files exist before their rows commit, so the archive covers every dumped row.
        pg.run([pg.tool("pg_dump"), "--format=custom", "--no-owner", "--no-acl", f"--file={dump}", pg.database])
        counts = pg.row_counts()
        revision = pg.alembic_revision()
        stored = pg.stored_files()
        files = evidence_files(evidence_root)
        archive = out / EVIDENCE_FILE
        write_archive(evidence_root, files, archive)
        integrity = file_problems(stored, evidence_root)
        manifest = {
            "format": FORMAT,
            "created_at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "database": {
                "file": DUMP_FILE,
                "sha256": sha256_file(dump),
                "size": dump.stat().st_size,
                "name": pg.database,
                "server_version": pg.server_version(),
                "pg_dump": tool_version(pg, "pg_dump"),
                "alembic_revision": revision,
                "row_counts": counts,
            },
            "evidence": {
                "file": EVIDENCE_FILE,
                "sha256": sha256_file(archive),
                "size": archive.stat().st_size,
                "files": files,
                "referenced_rows": {t: len(rows) for t, rows in stored.items()},
                "integrity_problems": integrity,
            },
        }
        (out / MANIFEST_FILE).write_text(json.dumps(manifest, indent=1, sort_keys=True) + "\n")
    finally:
        os.umask(old_umask)
    for problem in integrity:
        print(f"WARNING (already in the source, kept in the backup): {problem}", file=sys.stderr)
    return {
        "backup": str(out),
        "tables": len(counts),
        "rows": sum(counts.values()),
        "evidence_files": len(files),
        "alembic_revision": revision,
        "integrity_problems": len(integrity),
    }


def load_manifest(path: Path) -> dict:
    try:
        manifest = json.loads(path.read_text())
    except (OSError, ValueError) as exc:
        raise BackupError(f"cannot read manifest {path}: {exc}") from exc
    if manifest.get("format") != FORMAT:
        raise BackupError(f"unsupported backup format {manifest.get('format')!r} (expected {FORMAT})")
    return manifest


def restore(args: argparse.Namespace) -> dict:
    source: Path = args.backup
    manifest = load_manifest(source / MANIFEST_FILE)
    dump = source / manifest["database"]["file"]
    archive = source / manifest["evidence"]["file"]
    # Check everything before changing anything.
    check_file(dump, manifest["database"]["sha256"], manifest["database"]["size"])
    check_file(archive, manifest["evidence"]["sha256"], manifest["evidence"]["size"])
    pg = Postgres(database_url(args.database_url_env), args.pg_bin)
    if pg.tables():
        raise BackupError(f"target database {pg.database} is not empty; restore only into a new, empty database")
    target: Path = args.evidence_dir
    if target.exists() and any(target.iterdir()):
        raise BackupError(f"target evidence directory is not empty: {target}")

    pg.run(
        [
            pg.tool("pg_restore"),
            "--no-owner",
            "--no-acl",
            "--exit-on-error",
            "--single-transaction",
            f"--dbname={pg.database}",
            str(dump),
        ]
    )
    target.mkdir(parents=True, exist_ok=True)
    expected = manifest["evidence"]["files"]
    extract_archive(archive, target, expected)
    for rel, meta in expected.items():
        check_file(target / rel, meta["sha256"], meta["size"])
    result = verify_database(pg, target, manifest)
    return {"restored_into": pg.database, "evidence_dir": str(target), **result}


def verify_database(pg: Postgres, evidence_root: Path, manifest: dict | None) -> dict:
    stored = pg.stored_files()
    problems = file_problems(stored, evidence_root)
    counts = pg.row_counts()
    revision = pg.alembic_revision()
    if manifest is not None:
        problems += count_problems(manifest["database"]["row_counts"], counts)
        if manifest["database"]["alembic_revision"] != revision:
            problems.append(f"Alembic revision: backup {manifest['database']['alembic_revision']}, database {revision}")
    if problems:
        raise BackupError("verification failed:\n  " + "\n  ".join(problems))
    return {
        "verified_tables": len(counts),
        "verified_rows": sum(counts.values()),
        "verified_files": sum(len(rows) for rows in stored.values()),
        "alembic_revision": revision,
    }


def verify(args: argparse.Namespace) -> dict:
    pg = Postgres(database_url(args.database_url_env), args.pg_bin)
    manifest = load_manifest(args.manifest) if args.manifest else None
    return verify_database(pg, args.evidence_dir, manifest)


# -- entry point -------------------------------------------------------------------------------------------------


def parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--pg-bin", help="directory with pg_dump, pg_restore and psql (default: PATH)")
    sub = ap.add_subparsers(dest="command", required=True)

    b = sub.add_parser("backup", help="dump the database and archive the evidence directory")
    b.add_argument("--evidence-dir", type=Path, required=True)
    b.add_argument("--out", type=Path, required=True, help="new or empty directory for the backup")
    b.add_argument("--database-url-env", default="SITEGUARD_DATABASE_URL")
    b.set_defaults(func=backup)

    r = sub.add_parser("restore", help="restore a backup into an empty database and evidence directory")
    r.add_argument("--backup", type=Path, required=True)
    r.add_argument("--evidence-dir", type=Path, required=True, help="new or empty directory")
    r.add_argument("--database-url-env", default="SITEGUARD_RESTORE_DATABASE_URL")
    r.set_defaults(func=restore)

    v = sub.add_parser("verify", help="check evidence files against the hashes recorded in the database")
    v.add_argument("--evidence-dir", type=Path, required=True)
    v.add_argument("--manifest", type=Path, help="also compare row counts and revision with this backup")
    v.add_argument("--database-url-env", default="SITEGUARD_DATABASE_URL")
    v.set_defaults(func=verify)
    return ap


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        result = args.func(args)
    except (BackupError, OSError, tarfile.TarError) as exc:
        print(f"{args.command} FAILED: {exc}", file=sys.stderr)
        return 1
    print(json.dumps({"command": args.command, "status": "ok", **result}, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
