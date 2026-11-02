#!/usr/bin/env python3
"""Safely sync the creator Google Sheet into the local SQLite database.

The sheet is treated as an additive source: new creators are inserted and
existing creators only receive values that are currently missing. Boolean
milestones can move from false to true, but never backwards during a sync.
"""

import csv
import os
import sqlite3
import tempfile
import urllib.request
from datetime import datetime, timezone
from pathlib import Path


DB_PATH = Path(os.environ.get('AFS_DB_PATH', '/home/gan/Projects/AFS/database/afs.db'))
SHEET_EXPORT_URL = 'https://docs.google.com/spreadsheets/d/1OOJeNbQy6i0f5HAQ0jIA6J8_Gj47NcZ9DFDbmrBO7hY/export?format=csv&gid=1258396539'
REQUIRED_HEADERS = {
    'no', 'username', 'no_wa', 'catatan', 'oke?', 'Invite', 'Deal',
    'Req Sampel', 'Kirim', 'VT1', 'VT 2', 'VT 3', 'VT 4', 'VT 5', 'VT Winn',
}
BOOL_FIELDS = {
    'fit_checked': 'oke?',
    'invited': 'Invite',
    'deal_confirmed': 'Deal',
    'sample_requested': 'Req Sampel',
    'sample_shipped': 'Kirim',
}
VT_COLUMNS = ['VT1', 'VT 2', 'VT 3', 'VT 4', 'VT 5', 'VT Winn']


def normalize_bool(value):
    if value is None:
        return 0
    if isinstance(value, bool):
        return 1 if value else 0
    return 1 if str(value).strip().lower() in {'true', '1', 'yes', 'y', 'on'} else 0


def normalize_username(value):
    return str(value or '').strip().lower()


def ensure_default_user(conn):
    row = conn.execute(
        "SELECT id FROM users WHERE email = 'system@local.afs' LIMIT 1"
    ).fetchone()
    if row:
        return row[0]

    cursor = conn.execute(
        "INSERT INTO users (name, email) VALUES (?, ?)",
        ('System', 'system@local.afs'),
    )
    return cursor.lastrowid


def get_affiliator_id(conn, username):
    row = conn.execute(
        """
        SELECT a.id
        FROM affiliator_handles ah
        INNER JOIN affiliators a ON a.id = ah.affiliator_id
        WHERE ah.platform = 'tiktok_shop'
          AND LOWER(TRIM(ah.handle)) = LOWER(TRIM(?))
        ORDER BY a.id
        LIMIT 1
        """,
        (username,),
    ).fetchone()
    if row:
        return row[0]

    row = conn.execute(
        """
        SELECT id
        FROM affiliators
        WHERE LOWER(TRIM(name)) = LOWER(TRIM(?))
        ORDER BY id
        LIMIT 1
        """,
        (username,),
    ).fetchone()
    return row[0] if row else None


def ensure_tiktok_handle(conn, affiliator_id, username):
    profile_url = f'https://www.tiktok.com/@{username}'
    row = conn.execute(
        """
        SELECT id, profile_url
        FROM affiliator_handles
        WHERE affiliator_id = ? AND platform = 'tiktok_shop'
        ORDER BY id
        LIMIT 1
        """,
        (affiliator_id,),
    ).fetchone()
    if row:
        if not str(row[1] or '').strip():
            conn.execute(
                "UPDATE affiliator_handles SET profile_url = ? WHERE id = ?",
                (profile_url, row[0]),
            )
            return True
        return False

    conn.execute(
        """
        INSERT INTO affiliator_handles (affiliator_id, platform, handle, profile_url)
        VALUES (?, 'tiktok_shop', ?, ?)
        """,
        (affiliator_id, username, profile_url),
    )
    return True


def upsert_affiliator(conn, creator, default_user_id):
    username = creator['username']
    aff_id = get_affiliator_id(conn, username)
    today = datetime.now(timezone.utc).strftime('%Y-%m-%d')

    if aff_id is None:
        cursor = conn.execute(
            """
            INSERT INTO affiliators (
                name, brand, primary_platform, pic_user_id, stage, stage_since,
                source, joined_at, notes, contact_status, phone,
                fit_checked, invited, deal_confirmed,
                sample_requested, sample_shipped, vt_posted,
                created_at, updated_at
            )
            VALUES (?, ?, 'tiktok_shop', ?, 'new', ?, 'manual_outreach', ?, ?,
                    'contacted', ?, ?, ?, ?, ?, ?, ?, datetime('now'), datetime('now'))
            """,
            (
                username,
                'manual',
                default_user_id,
                today,
                today,
                creator['notes'],
                creator['phone'],
                creator['fit_checked'],
                creator['invited'],
                creator['deal_confirmed'],
                creator['sample_requested'],
                creator['sample_shipped'],
                creator['vt_posted'],
            ),
        )
        aff_id = cursor.lastrowid
        ensure_tiktok_handle(conn, aff_id, username)
        return 'inserted', []

    current = conn.execute(
        """
        SELECT phone, notes, fit_checked, invited, deal_confirmed,
               sample_requested, sample_shipped, vt_posted
        FROM affiliators
        WHERE id = ?
        """,
        (aff_id,),
    ).fetchone()
    columns = [
        'phone', 'notes', 'fit_checked', 'invited', 'deal_confirmed',
        'sample_requested', 'sample_shipped', 'vt_posted',
    ]
    existing = dict(zip(columns, current))
    updates = {}

    for field in ('phone', 'notes'):
        if not str(existing[field] or '').strip() and creator[field]:
            updates[field] = creator[field]

    for field in (*BOOL_FIELDS.keys(), 'vt_posted'):
        if not normalize_bool(existing[field]) and creator[field]:
            updates[field] = 1

    if updates:
        assignments = ', '.join(f'{field} = ?' for field in updates)
        values = [*updates.values(), aff_id]
        conn.execute(
            f"UPDATE affiliators SET {assignments}, updated_at = datetime('now') WHERE id = ?",
            values,
        )

    handle_updated = ensure_tiktok_handle(conn, aff_id, username)
    if handle_updated and not updates:
        return 'updated', ['profile_url']
    return ('updated', list(updates)) if updates else ('unchanged', [])


def fetch_csv(url):
    with tempfile.NamedTemporaryFile(prefix='afs_google_sheet_', suffix='.csv', delete=False) as tmp:
        tmp_path = Path(tmp.name)
    urllib.request.urlretrieve(url, tmp_path)
    return tmp_path


def read_sheet(csv_path):
    with open(csv_path, 'r', encoding='utf-8-sig', newline='') as csv_file:
        reader = csv.DictReader(csv_file)
        headers = set(reader.fieldnames or [])
        missing_headers = sorted(REQUIRED_HEADERS - headers)
        if missing_headers:
            raise ValueError(f'Missing required sheet columns: {", ".join(missing_headers)}')
        return list(reader)


def merge_creator_rows(rows):
    creators = {}
    duplicate_rows = 0
    for row in rows:
        username = str(row.get('username') or '').strip()
        key = normalize_username(username)
        if not key:
            continue

        incoming = {
            'username': username,
            'phone': str(row.get('no_wa') or '').strip() or None,
            'notes': str(row.get('catatan') or '').strip() or None,
            **{field: normalize_bool(row.get(column)) for field, column in BOOL_FIELDS.items()},
            'vt_posted': int(any(normalize_bool(row.get(column)) for column in VT_COLUMNS)),
        }
        if key not in creators:
            creators[key] = incoming
            continue

        duplicate_rows += 1
        current = creators[key]
        for field in ('phone', 'notes'):
            if not current[field] and incoming[field]:
                current[field] = incoming[field]
        for field in (*BOOL_FIELDS.keys(), 'vt_posted'):
            current[field] = int(bool(current[field] or incoming[field]))

    return list(creators.values()), duplicate_rows


def replace_raw_sheet_snapshot(conn, rows):
    conn.execute('DELETE FROM sheet_rows')
    for row_index, row in enumerate(rows, start=1):
        conn.execute(
            """
            INSERT INTO sheet_rows (
                source_row_no, no, username, no_wa, catatan,
                oke, invite, deal, req_sampel, kirim,
                vt1, vt2, vt3, vt4, vt5, vt_winn
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                row_index,
                row.get('no'),
                str(row.get('username') or '').strip(),
                str(row.get('no_wa') or '').strip() or None,
                str(row.get('catatan') or '').strip() or None,
                normalize_bool(row.get('oke?')),
                normalize_bool(row.get('Invite')),
                normalize_bool(row.get('Deal')),
                normalize_bool(row.get('Req Sampel')),
                normalize_bool(row.get('Kirim')),
                normalize_bool(row.get('VT1')),
                normalize_bool(row.get('VT 2')),
                normalize_bool(row.get('VT 3')),
                normalize_bool(row.get('VT 4')),
                normalize_bool(row.get('VT 5')),
                normalize_bool(row.get('VT Winn')),
            ),
        )


def import_sheet(csv_path=None):
    downloaded_path = None
    if csv_path is None:
        downloaded_path = fetch_csv(SHEET_EXPORT_URL)
        csv_path = downloaded_path

    try:
        rows = read_sheet(csv_path)
        creators, duplicate_rows = merge_creator_rows(rows)
        stats = {
            'sheet_rows': len(rows),
            'unique_usernames': len(creators),
            'duplicate_username_rows': duplicate_rows,
            'empty_username_rows': sum(not normalize_username(row.get('username')) for row in rows),
            'inserted': 0,
            'updated': 0,
            'unchanged': 0,
            'updated_fields': {},
        }

        conn = sqlite3.connect(DB_PATH)
        try:
            conn.execute('PRAGMA foreign_keys = ON')
            conn.execute('BEGIN IMMEDIATE')
            default_user_id = ensure_default_user(conn)
            replace_raw_sheet_snapshot(conn, rows)

            for creator in creators:
                action, updated_fields = upsert_affiliator(conn, creator, default_user_id)
                stats[action] += 1
                for field in updated_fields:
                    stats['updated_fields'][field] = stats['updated_fields'].get(field, 0) + 1

            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

        return stats
    finally:
        if downloaded_path is not None:
            downloaded_path.unlink(missing_ok=True)


if __name__ == '__main__':
    result = import_sheet(os.environ.get('AFS_SHEET_CSV'))
    print(f"Sheet rows saved: {result['sheet_rows']}")
    print(f"Unique usernames: {result['unique_usernames']}")
    print(f"Duplicate username rows merged: {result['duplicate_username_rows']}")
    print(f"Rows with empty username: {result['empty_username_rows']}")
    print(f"New creators inserted: {result['inserted']}")
    print(f"Existing creators completed: {result['updated']}")
    print(f"Existing creators unchanged: {result['unchanged']}")
    if result['updated_fields']:
        details = ', '.join(
            f'{field}={count}' for field, count in sorted(result['updated_fields'].items())
        )
        print(f'Completed fields: {details}')
