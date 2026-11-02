#!/usr/bin/env python3
"""Sync the workbook's `All Creator` tab into the local AFS database."""

import csv
import os
import sqlite3
import tempfile
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

from sync_sheet_to_db import ensure_default_user, normalize_username


DB_PATH = Path(os.environ.get('AFS_DB_PATH', '/home/gan/Projects/AFS/database/afs.db'))
ALL_CREATOR_EXPORT_URL = (
    'https://docs.google.com/spreadsheets/d/'
    '1OOJeNbQy6i0f5HAQ0jIA6J8_Gj47NcZ9DFDbmrBO7hY/'
    'gviz/tq?tqx=out:csv&sheet=All%20Creator'
)
REQUIRED_HEADERS = {
    'Handle', 'Nama Kreator', 'Pengikut', 'GMV Total (Rp)', 'Penjualan',
    'Jumlah Video', 'Views Konten', 'Jml Produk', 'Segmen', 'Produk',
    'Periode', 'Link TikTok',
}


def parse_integer(value):
    text = str(value or '').strip().replace(',', '')
    if not text:
        return None
    try:
        return int(text)
    except ValueError:
        return int(float(text))


def fetch_csv(url):
    with tempfile.NamedTemporaryFile(prefix='afs_all_creator_', suffix='.csv', delete=False) as tmp:
        tmp_path = Path(tmp.name)
    urllib.request.urlretrieve(url, tmp_path)
    return tmp_path


def read_rows(csv_path):
    with open(csv_path, 'r', encoding='utf-8-sig', newline='') as csv_file:
        reader = csv.DictReader(csv_file)
        headers = set(reader.fieldnames or [])
        missing_headers = sorted(REQUIRED_HEADERS - headers)
        if missing_headers:
            raise ValueError(f'Missing All Creator columns: {", ".join(missing_headers)}')
        return list(reader)


def normalize_row(row):
    return {
        'handle': str(row.get('Handle') or '').strip(),
        'creator_name': str(row.get('Nama Kreator') or '').strip() or None,
        'followers': parse_integer(row.get('Pengikut')),
        'gmv_total': parse_integer(row.get('GMV Total (Rp)')),
        'sales': parse_integer(row.get('Penjualan')),
        'video_count': parse_integer(row.get('Jumlah Video')),
        'content_views': parse_integer(row.get('Views Konten')),
        'product_count': parse_integer(row.get('Jml Produk')),
        'segment': str(row.get('Segmen') or '').strip() or None,
        'product': str(row.get('Produk') or '').strip() or None,
        'period': str(row.get('Periode') or '').strip() or None,
        'profile_url': str(row.get('Link TikTok') or '').strip() or None,
    }


def merge_rows(rows):
    creators = {}
    duplicate_rows = 0
    empty_handles = 0
    for raw_row in rows:
        row = normalize_row(raw_row)
        key = normalize_username(row['handle'])
        if not key:
            empty_handles += 1
            continue
        if key not in creators:
            creators[key] = row
            continue

        duplicate_rows += 1
        current = creators[key]
        for field, value in row.items():
            if field != 'handle' and current[field] is None and value is not None:
                current[field] = value

    return list(creators.values()), duplicate_rows, empty_handles


def ensure_schema(conn):
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS all_creator_rows (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source_row_no INTEGER,
            handle TEXT NOT NULL,
            creator_name TEXT,
            followers INTEGER,
            gmv_total INTEGER,
            sales INTEGER,
            video_count INTEGER,
            content_views INTEGER,
            product_count INTEGER,
            segment TEXT,
            product TEXT,
            period TEXT,
            profile_url TEXT,
            imported_at TEXT DEFAULT (datetime('now'))
        )
        """
    )
    conn.execute(
        'CREATE INDEX IF NOT EXISTS idx_all_creator_rows_handle ON all_creator_rows(handle)'
    )
    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_affiliator_handles_normalized_handle
        ON affiliator_handles(platform, LOWER(TRIM(handle)))
        """
    )


def get_affiliator_id_by_handle(conn, handle):
    row = conn.execute(
        """
        SELECT affiliator_id
        FROM affiliator_handles
        WHERE platform = 'tiktok_shop'
          AND LOWER(TRIM(handle)) = LOWER(TRIM(?))
        ORDER BY id
        LIMIT 1
        """,
        (handle,),
    ).fetchone()
    if row:
        return row[0]

    # Support legacy rows that have the username in `name` but no TikTok handle.
    row = conn.execute(
        """
        SELECT a.id
        FROM affiliators a
        WHERE LOWER(TRIM(a.name)) = LOWER(TRIM(?))
          AND NOT EXISTS (
              SELECT 1
              FROM affiliator_handles ah
              WHERE ah.affiliator_id = a.id AND ah.platform = 'tiktok_shop'
          )
        ORDER BY a.id
        LIMIT 1
        """,
        (handle,),
    ).fetchone()
    return row[0] if row else None


def replace_raw_snapshot(conn, rows):
    conn.execute('DELETE FROM all_creator_rows')
    conn.executemany(
        """
        INSERT INTO all_creator_rows (
            source_row_no, handle, creator_name, followers, gmv_total, sales,
            video_count, content_views, product_count, segment, product,
            period, profile_url
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [
            (
                row_number,
                row['handle'],
                row['creator_name'],
                row['followers'],
                row['gmv_total'],
                row['sales'],
                row['video_count'],
                row['content_views'],
                row['product_count'],
                row['segment'],
                row['product'],
                row['period'],
                row['profile_url'],
            )
            for row_number, row in enumerate((normalize_row(row) for row in rows), start=1)
            if row['handle']
        ],
    )


def insert_creator(conn, creator, default_user_id):
    today = datetime.now(timezone.utc).strftime('%Y-%m-%d')
    cursor = conn.execute(
        """
        INSERT INTO affiliators (
            name, primary_platform, tier, pic_user_id, stage, stage_since,
            source, joined_at, contact_status, created_at, updated_at
        ) VALUES (?, 'tiktok_shop', ?, ?, 'new', ?, 'all_creator_sheet', ?,
                  'contacted', datetime('now'), datetime('now'))
        """,
        (
            creator['creator_name'] or creator['handle'],
            creator['segment'],
            default_user_id,
            today,
            today,
        ),
    )
    affiliator_id = cursor.lastrowid
    conn.execute(
        """
        INSERT INTO affiliator_handles (
            affiliator_id, platform, handle, profile_url, followers,
            followers_checked_at
        ) VALUES (?, 'tiktok_shop', ?, ?, ?, ?)
        """,
        (
            affiliator_id,
            creator['handle'],
            creator['profile_url'],
            creator['followers'],
            today if creator['followers'] is not None else None,
        ),
    )


def complete_creator(conn, affiliator_id, creator):
    updated_fields = []
    current = conn.execute(
        'SELECT name, tier FROM affiliators WHERE id = ?',
        (affiliator_id,),
    ).fetchone()
    affiliator_updates = {}
    current_name = str(current[0] or '').strip()
    creator_name = str(creator['creator_name'] or '').strip()
    if creator_name and (
        not current_name
        or normalize_username(current_name) == normalize_username(creator['handle'])
    ) and current_name != creator_name:
        affiliator_updates['name'] = creator_name
    if not str(current[1] or '').strip() and creator['segment']:
        affiliator_updates['tier'] = creator['segment']

    if affiliator_updates:
        assignments = ', '.join(f'{field} = ?' for field in affiliator_updates)
        conn.execute(
            f"UPDATE affiliators SET {assignments}, updated_at = datetime('now') WHERE id = ?",
            [*affiliator_updates.values(), affiliator_id],
        )
        updated_fields.extend(affiliator_updates)

    handle_row = conn.execute(
        """
        SELECT id, profile_url, followers
        FROM affiliator_handles
        WHERE affiliator_id = ? AND platform = 'tiktok_shop'
        ORDER BY id
        LIMIT 1
        """,
        (affiliator_id,),
    ).fetchone()
    today = datetime.now(timezone.utc).strftime('%Y-%m-%d')
    if handle_row is None:
        conn.execute(
            """
            INSERT INTO affiliator_handles (
                affiliator_id, platform, handle, profile_url, followers,
                followers_checked_at
            ) VALUES (?, 'tiktok_shop', ?, ?, ?, ?)
            """,
            (
                affiliator_id,
                creator['handle'],
                creator['profile_url'],
                creator['followers'],
                today if creator['followers'] is not None else None,
            ),
        )
        updated_fields.append('tiktok_handle')
        return updated_fields

    handle_updates = {}
    if not str(handle_row[1] or '').strip() and creator['profile_url']:
        handle_updates['profile_url'] = creator['profile_url']
    if handle_row[2] is None and creator['followers'] is not None:
        handle_updates['followers'] = creator['followers']
        handle_updates['followers_checked_at'] = today
    if handle_updates:
        assignments = ', '.join(f'{field} = ?' for field in handle_updates)
        conn.execute(
            f'UPDATE affiliator_handles SET {assignments} WHERE id = ?',
            [*handle_updates.values(), handle_row[0]],
        )
        updated_fields.extend(handle_updates)

    return updated_fields


def import_all_creators(csv_path=None):
    downloaded_path = None
    if csv_path is None:
        downloaded_path = fetch_csv(ALL_CREATOR_EXPORT_URL)
        csv_path = downloaded_path

    try:
        rows = read_rows(csv_path)
        creators, duplicate_rows, empty_handles = merge_rows(rows)
        stats = {
            'sheet_rows': len(rows),
            'unique_handles': len(creators),
            'duplicate_rows': duplicate_rows,
            'empty_handles': empty_handles,
            'inserted': 0,
            'updated': 0,
            'unchanged': 0,
            'updated_fields': {},
        }

        conn = sqlite3.connect(DB_PATH)
        try:
            conn.execute('PRAGMA foreign_keys = ON')
            conn.execute('BEGIN IMMEDIATE')
            ensure_schema(conn)
            replace_raw_snapshot(conn, rows)
            default_user_id = ensure_default_user(conn)

            for creator in creators:
                affiliator_id = get_affiliator_id_by_handle(conn, creator['handle'])
                if affiliator_id is None:
                    insert_creator(conn, creator, default_user_id)
                    stats['inserted'] += 1
                    continue

                updated_fields = complete_creator(conn, affiliator_id, creator)
                if updated_fields:
                    stats['updated'] += 1
                    for field in updated_fields:
                        stats['updated_fields'][field] = (
                            stats['updated_fields'].get(field, 0) + 1
                        )
                else:
                    stats['unchanged'] += 1

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
    result = import_all_creators(os.environ.get('AFS_ALL_CREATOR_CSV'))
    print(f"All Creator rows saved: {result['sheet_rows']}")
    print(f"Unique handles: {result['unique_handles']}")
    print(f"Duplicate handle rows merged: {result['duplicate_rows']}")
    print(f"Rows with empty handle: {result['empty_handles']}")
    print(f"New creators inserted: {result['inserted']}")
    print(f"Existing creators completed: {result['updated']}")
    print(f"Existing creators unchanged: {result['unchanged']}")
    if result['updated_fields']:
        details = ', '.join(
            f'{field}={count}' for field, count in sorted(result['updated_fields'].items())
        )
        print(f'Completed fields: {details}')
