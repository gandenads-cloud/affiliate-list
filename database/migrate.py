#!/usr/bin/env python3
"""Apply ordered, checksum-protected SQLite migrations for AFS."""

import argparse
import hashlib
import sqlite3
from pathlib import Path


APP_DIR = Path(__file__).resolve().parent.parent
DEFAULT_DB_PATH = APP_DIR / 'database' / 'afs.db'
MIGRATIONS_DIR = APP_DIR / 'database' / 'migrations'


def split_statements(sql_text):
    """Split SQL without breaking statements that contain embedded semicolons."""
    statement = []
    for line in sql_text.splitlines(keepends=True):
        statement.append(line)
        candidate = ''.join(statement).strip()
        if candidate and sqlite3.complete_statement(candidate):
            yield candidate
            statement = []
    remainder = ''.join(statement).strip()
    if remainder:
        raise ValueError('Migration SQL ends with an incomplete statement.')


def migration_files():
    return sorted(MIGRATIONS_DIR.glob('[0-9][0-9][0-9]_*.sql'))


def ensure_migration_table(conn):
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS schema_migrations (
            version INTEGER PRIMARY KEY,
            name TEXT NOT NULL,
            checksum TEXT NOT NULL,
            applied_at TEXT NOT NULL DEFAULT (datetime('now'))
        )
        """
    )
    conn.commit()


def migration_metadata(path):
    version_text, _, name = path.stem.partition('_')
    if not version_text.isdigit() or not name:
        raise ValueError(f'Invalid migration filename: {path.name}')
    payload = path.read_bytes()
    return int(version_text), name, hashlib.sha256(payload).hexdigest(), payload.decode('utf-8')


def validate_database(conn):
    integrity = conn.execute('PRAGMA integrity_check').fetchone()[0]
    if integrity != 'ok':
        raise sqlite3.IntegrityError(f'Integrity check failed: {integrity}')
    violations = conn.execute('PRAGMA foreign_key_check').fetchall()
    if violations:
        raise sqlite3.IntegrityError(
            f'Foreign-key check failed with {len(violations)} violation(s).'
        )


def run_migrations(db_path=DEFAULT_DB_PATH, *, quiet=False):
    db_path = Path(db_path)
    conn = sqlite3.connect(db_path, timeout=30)
    conn.row_factory = sqlite3.Row
    try:
        conn.execute('PRAGMA foreign_keys = ON')
        ensure_migration_table(conn)
        applied = {
            row['version']: row
            for row in conn.execute(
                'SELECT version, name, checksum, applied_at FROM schema_migrations'
            )
        }
        completed = []
        for path in migration_files():
            version, name, checksum, sql_text = migration_metadata(path)
            existing = applied.get(version)
            if existing:
                if existing['checksum'] != checksum or existing['name'] != name:
                    raise RuntimeError(
                        f'Migration {version:03d} was modified after being applied.'
                    )
                if not quiet:
                    print(f'{version:03d} {name}: already applied')
                continue

            conn.execute('PRAGMA foreign_keys = OFF')
            conn.execute('BEGIN IMMEDIATE')
            try:
                for statement in split_statements(sql_text):
                    conn.execute(statement)
                conn.execute(
                    """
                    INSERT INTO schema_migrations (version, name, checksum)
                    VALUES (?, ?, ?)
                    """,
                    (version, name, checksum),
                )
                violations = conn.execute('PRAGMA foreign_key_check').fetchall()
                if violations:
                    raise sqlite3.IntegrityError(
                        f'Migration {version:03d} creates '
                        f'{len(violations)} foreign-key violation(s).'
                    )
                conn.commit()
            except Exception:
                conn.rollback()
                raise
            finally:
                conn.execute('PRAGMA foreign_keys = ON')

            completed.append(version)
            if not quiet:
                print(f'{version:03d} {name}: applied')

        validate_database(conn)
        return completed
    finally:
        conn.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--db', type=Path, default=DEFAULT_DB_PATH)
    args = parser.parse_args()
    completed = run_migrations(args.db)
    print(f'Database valid: {args.db}')
    print(f'New migrations applied: {len(completed)}')


if __name__ == '__main__':
    main()
