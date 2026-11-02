#!/usr/bin/env python3
"""Serve the AFS static app and its local SQLite API."""

import json
import os
import re
import secrets
import sqlite3
import sys
from datetime import date, datetime
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse


APP_DIR = Path(__file__).resolve().parent.parent
DB_PATH = Path(os.environ.get('AFS_DB_PATH', APP_DIR / 'database' / 'afs.db'))
HOST = os.environ.get('AFS_HOST', '127.0.0.1')
PORT = int(os.environ.get('AFS_PORT', '8000'))
MAX_BODY_BYTES = 5 * 1024 * 1024
USERNAME_RE = re.compile(r'^[A-Za-z0-9._]{1,64}$')
TRACKER_FIELDS = {
    'oke', 'invite', 'deal', 'req_sampel', 'kirim',
    'vt1', 'vt2', 'vt3', 'vt4', 'vt5', 'vt_winn',
}
TRACKER_TO_AFFILIATOR = {
    'oke': 'fit_checked',
    'invite': 'invited',
    'deal': 'deal_confirmed',
    'req_sampel': 'sample_requested',
    'kirim': 'sample_shipped',
}


def connect_db():
    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute('PRAGMA foreign_keys = ON')
    return conn


def init_db():
    schema_path = APP_DIR / 'database' / 'schema.sql'
    with connect_db() as conn:
        conn.executescript(schema_path.read_text(encoding='utf-8'))
        conn.execute(
            """
            INSERT OR IGNORE INTO creator_tracker_statuses (
                affiliator_id, oke, invite, deal, req_sampel, kirim,
                vt1, vt2, vt3, vt4, vt5, vt_winn
            )
            SELECT ah.affiliator_id,
                   MAX(COALESCE(sr.oke, 0)),
                   MAX(COALESCE(sr.invite, 0)),
                   MAX(COALESCE(sr.deal, 0)),
                   MAX(COALESCE(sr.req_sampel, 0)),
                   MAX(COALESCE(sr.kirim, 0)),
                   MAX(COALESCE(sr.vt1, 0)),
                   MAX(COALESCE(sr.vt2, 0)),
                   MAX(COALESCE(sr.vt3, 0)),
                   MAX(COALESCE(sr.vt4, 0)),
                   MAX(COALESCE(sr.vt5, 0)),
                   MAX(COALESCE(sr.vt_winn, 0))
            FROM sheet_rows sr
            INNER JOIN affiliator_handles ah
                ON ah.platform = 'tiktok_shop'
               AND LOWER(TRIM(ah.handle)) = LOWER(TRIM(sr.username))
            WHERE TRIM(COALESCE(sr.username, '')) <> ''
            GROUP BY ah.affiliator_id
            """
        )


def clean_text(value, limit):
    text = str(value or '').strip()
    return text[:limit] or None


def normalize_username(value):
    username = str(value or '').strip()
    username = re.sub(r'^https?://(?:www\.)?tiktok\.com/@', '', username, flags=re.I)
    username = username.split('?', 1)[0].split('/', 1)[0].strip().lstrip('@')
    if not USERNAME_RE.fullmatch(username):
        return None, None
    return username, username.lower()


def validate_date(value):
    text = str(value or '').strip()
    try:
        return date.fromisoformat(text).isoformat()
    except ValueError as error:
        raise ValueError('Tanggal masuk harus berformat YYYY-MM-DD.') from error


def ensure_default_user(conn):
    row = conn.execute(
        "SELECT id FROM users WHERE email = 'system@local.afs' LIMIT 1"
    ).fetchone()
    if row:
        return row['id']
    return conn.execute(
        "INSERT INTO users (name, email) VALUES ('System', 'system@local.afs')"
    ).lastrowid


def find_affiliator(conn, username):
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
    return row['id'] if row else None


def create_affiliator(conn, row, entry_date, default_user_id):
    username = row['username']
    cursor = conn.execute(
        """
        INSERT INTO affiliators (
            name, primary_platform, pic_user_id, stage, stage_since, source,
            joined_at, notes, contact_status, phone, created_at, updated_at
        ) VALUES (?, 'tiktok_shop', ?, 'new', ?, 'creator_list_page', ?, ?,
                  'contacted', ?, datetime('now'), datetime('now'))
        """,
        (
            row['creator_name'] or username,
            default_user_id,
            entry_date,
            entry_date,
            row['notes'],
            row['phone'],
        ),
    )
    affiliator_id = cursor.lastrowid
    conn.execute(
        """
        INSERT INTO affiliator_handles (
            affiliator_id, platform, handle, profile_url
        ) VALUES (?, 'tiktok_shop', ?, ?)
        """,
        (affiliator_id, username, f'https://www.tiktok.com/@{username}'),
    )
    return affiliator_id


def complete_affiliator(conn, affiliator_id, row):
    current = conn.execute(
        'SELECT name, phone, notes FROM affiliators WHERE id = ?',
        (affiliator_id,),
    ).fetchone()
    updates = {}
    current_name = str(current['name'] or '').strip()
    if (
        row['creator_name']
        and current_name.lower() == row['username_normalized']
        and current_name != row['creator_name']
    ):
        updates['name'] = row['creator_name']
    if not str(current['phone'] or '').strip() and row['phone']:
        updates['phone'] = row['phone']
    if not str(current['notes'] or '').strip() and row['notes']:
        updates['notes'] = row['notes']
    if not updates:
        return []

    assignments = ', '.join(f'{field} = ?' for field in updates)
    conn.execute(
        f"UPDATE affiliators SET {assignments}, updated_at = datetime('now') WHERE id = ?",
        [*updates.values(), affiliator_id],
    )
    return list(updates)


def normalize_rows(raw_rows):
    rows = []
    invalid = []
    seen = set()
    duplicate_input = 0
    for position, raw in enumerate(raw_rows, start=1):
        if not isinstance(raw, dict):
            invalid.append({'row': position, 'value': '', 'reason': 'Format baris tidak valid'})
            continue
        username, normalized = normalize_username(raw.get('username'))
        if username is None:
            invalid.append({
                'row': position,
                'value': str(raw.get('username') or ''),
                'reason': 'Username kosong atau mengandung karakter tidak valid',
            })
            continue
        if normalized in seen:
            duplicate_input += 1
            continue
        seen.add(normalized)
        rows.append({
            'username': username,
            'username_normalized': normalized,
            'creator_name': clean_text(raw.get('creator_name'), 250),
            'phone': clean_text(raw.get('phone'), 80),
            'notes': clean_text(raw.get('notes'), 2000),
        })
    return rows, invalid, duplicate_input


def save_creator_list(payload):
    if not isinstance(payload, dict):
        raise ValueError('Payload harus berupa objek JSON.')
    entry_date = validate_date(payload.get('entry_date'))
    raw_rows = payload.get('rows')
    if not isinstance(raw_rows, list) or not raw_rows:
        raise ValueError('List creator masih kosong.')
    if len(raw_rows) > 20000:
        raise ValueError('Maksimal 20.000 creator dalam sekali simpan.')

    rows, invalid, duplicate_input = normalize_rows(raw_rows)
    stats = {
        'entry_date': entry_date,
        'received': len(raw_rows),
        'valid': len(rows),
        'saved': 0,
        'new_creators': 0,
        'completed_creators': 0,
        'duplicate_input': duplicate_input,
        'duplicate_existing': 0,
        'invalid': invalid,
        'completed_fields': {},
    }

    with connect_db() as conn:
        conn.execute('BEGIN IMMEDIATE')
        default_user_id = ensure_default_user(conn)
        for row in rows:
            duplicate = conn.execute(
                """
                SELECT 1
                FROM creator_list_entries
                WHERE username_normalized = ?
                LIMIT 1
                """,
                (row['username_normalized'],),
            ).fetchone()
            if duplicate:
                stats['duplicate_existing'] += 1
                continue

            affiliator_id = find_affiliator(conn, row['username'])
            if affiliator_id is None:
                affiliator_id = create_affiliator(conn, row, entry_date, default_user_id)
                stats['new_creators'] += 1
            else:
                completed = complete_affiliator(conn, affiliator_id, row)
                if completed:
                    stats['completed_creators'] += 1
                    for field in completed:
                        stats['completed_fields'][field] = (
                            stats['completed_fields'].get(field, 0) + 1
                        )

            conn.execute(
                """
                INSERT INTO creator_list_entries (
                    entry_date, username, username_normalized, creator_name,
                    phone, notes, affiliator_id
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    entry_date,
                    row['username'],
                    row['username_normalized'],
                    row['creator_name'],
                    row['phone'],
                    row['notes'],
                    affiliator_id,
                ),
            )
            stats['saved'] += 1

    return stats


def get_creator_list(query):
    entry_date = (query.get('date') or [''])[0].strip()
    if entry_date:
        entry_date = validate_date(entry_date)
    search = (query.get('q') or [''])[0].strip().lower()[:200]

    clauses = []
    params = []
    if entry_date:
        clauses.append('cle.entry_date = ?')
        params.append(entry_date)
    if search:
        clauses.append(
            """(
                LOWER(cle.username) LIKE ? OR LOWER(COALESCE(cle.creator_name, '')) LIKE ?
                OR LOWER(COALESCE(cle.phone, '')) LIKE ? OR LOWER(COALESCE(cle.notes, '')) LIKE ?
            )"""
        )
        needle = f'%{search}%'
        params.extend([needle] * 4)
    where_sql = f"WHERE {' AND '.join(clauses)}" if clauses else ''

    with connect_db() as conn:
        rows = conn.execute(
            f"""
            SELECT cle.id, cle.entry_date, cle.username,
                   COALESCE(cle.creator_name, a.name) AS creator_name,
                   COALESCE(cle.phone, a.phone) AS phone,
                   COALESCE(cle.notes, a.notes) AS notes,
                   cle.affiliator_id, cle.created_at
            FROM creator_list_entries cle
            INNER JOIN affiliators a ON a.id = cle.affiliator_id
            {where_sql}
            ORDER BY cle.entry_date DESC, cle.id DESC
            LIMIT 20000
            """,
            params,
        ).fetchall()
    return {'rows': [dict(row) for row in rows], 'count': len(rows)}


def get_entry_dates():
    with connect_db() as conn:
        rows = conn.execute(
            """
            SELECT entry_date, COUNT(*) AS count
            FROM creator_list_entries
            GROUP BY entry_date
            ORDER BY entry_date DESC
            """
        ).fetchall()
    return {'dates': [dict(row) for row in rows]}


def get_creator_tracker(query):
    scope = (query.get('scope') or ['entries'])[0].strip().lower()
    if scope not in {'entries', 'all'}:
        raise ValueError('Scope creator tidak valid.')
    search = (query.get('q') or [''])[0].strip().lower()[:200]
    entry_date = (query.get('date') or [''])[0].strip()
    if entry_date:
        entry_date = validate_date(entry_date)
    status_filter = (query.get('status') or [''])[0].strip().lower()
    allowed_statuses = {
        '', 'not_invited', 'invited', 'deal', 'sample_requested', 'shipped', 'vt_posted',
    }
    if status_filter not in allowed_statuses:
        raise ValueError('Filter status tidak valid.')
    try:
        limit = max(25, min(500, int((query.get('limit') or ['100'])[0])))
        offset = max(0, int((query.get('offset') or ['0'])[0]))
    except ValueError as error:
        raise ValueError('Pagination tidak valid.') from error

    oke_expr = 'COALESCE(cts.oke, a.fit_checked, 0)'
    invite_expr = 'COALESCE(cts.invite, a.invited, 0)'
    deal_expr = 'COALESCE(cts.deal, a.deal_confirmed, 0)'
    request_expr = 'COALESCE(cts.req_sampel, a.sample_requested, 0)'
    shipped_expr = 'COALESCE(cts.kirim, a.sample_shipped, 0)'
    vt1_expr = 'COALESCE(cts.vt1, a.vt_posted, 0)'
    vt_expr = (
        f'({vt1_expr} = 1 OR COALESCE(cts.vt2, 0) = 1 '
        'OR COALESCE(cts.vt3, 0) = 1 OR COALESCE(cts.vt4, 0) = 1 '
        'OR COALESCE(cts.vt5, 0) = 1 OR COALESCE(cts.vt_winn, 0) = 1)'
    )
    status_clauses = {
        'not_invited': f'{invite_expr} = 0',
        'invited': f'{invite_expr} = 1',
        'deal': f'{deal_expr} = 1',
        'sample_requested': f'{request_expr} = 1',
        'shipped': f'{shipped_expr} = 1',
        'vt_posted': vt_expr,
    }

    clauses = []
    params = []
    if scope == 'entries':
        clauses.append('cle.id IS NOT NULL')
    if entry_date:
        clauses.append('cle.entry_date = ?')
        params.append(entry_date)
    if search:
        escaped = search.replace('\\', '\\\\').replace('%', '\\%').replace('_', '\\_')
        needle = f'%{escaped}%'
        clauses.append(
            """(
                LOWER(ah.handle) LIKE ? ESCAPE '\\'
                OR LOWER(COALESCE(a.name, '')) LIKE ? ESCAPE '\\'
                OR LOWER(COALESCE(a.phone, cle.phone, '')) LIKE ? ESCAPE '\\'
                OR LOWER(COALESCE(a.notes, cle.notes, '')) LIKE ? ESCAPE '\\'
            )"""
        )
        params.extend([needle] * 4)
    if status_filter:
        clauses.append(status_clauses[status_filter])
    where_sql = f"WHERE {' AND '.join(clauses)}" if clauses else ''

    sql = f"""
        WITH primary_handle AS (
            SELECT affiliator_id, MIN(id) AS handle_id
            FROM affiliator_handles
            WHERE platform = 'tiktok_shop'
            GROUP BY affiliator_id
        )
        SELECT a.id AS affiliator_id,
               cle.entry_date,
               ah.handle AS username,
               a.name AS creator_name,
               COALESCE(NULLIF(a.phone, ''), cle.phone, '') AS no_wa,
               COALESCE(NULLIF(a.notes, ''), cle.notes, '') AS catatan,
               ah.profile_url,
               {oke_expr} AS oke,
               {invite_expr} AS invite,
               {deal_expr} AS deal,
               {request_expr} AS req_sampel,
               {shipped_expr} AS kirim,
               {vt1_expr} AS vt1,
               COALESCE(cts.vt2, 0) AS vt2,
               COALESCE(cts.vt3, 0) AS vt3,
               COALESCE(cts.vt4, 0) AS vt4,
               COALESCE(cts.vt5, 0) AS vt5,
               COALESCE(cts.vt_winn, 0) AS vt_winn,
               COUNT(*) OVER() AS _total_count,
               SUM(CASE WHEN {oke_expr} = 1 THEN 1 ELSE 0 END) OVER() AS _total_oke,
               SUM(CASE WHEN {invite_expr} = 1 THEN 1 ELSE 0 END) OVER() AS _total_invited,
               SUM(CASE WHEN {deal_expr} = 1 THEN 1 ELSE 0 END) OVER() AS _total_deal,
               SUM(CASE WHEN {request_expr} = 1 THEN 1 ELSE 0 END) OVER() AS _total_requested,
               SUM(CASE WHEN {shipped_expr} = 1 THEN 1 ELSE 0 END) OVER() AS _total_shipped,
               SUM(CASE WHEN {vt_expr} THEN 1 ELSE 0 END) OVER() AS _total_vt
        FROM affiliators a
        INNER JOIN primary_handle ph ON ph.affiliator_id = a.id
        INNER JOIN affiliator_handles ah ON ah.id = ph.handle_id
        LEFT JOIN creator_list_entries cle ON cle.affiliator_id = a.id
        LEFT JOIN creator_tracker_statuses cts ON cts.affiliator_id = a.id
        {where_sql}
        ORDER BY COALESCE(cle.entry_date, a.joined_at) DESC, LOWER(ah.handle), a.id
        LIMIT ? OFFSET ?
    """
    with connect_db() as conn:
        result_rows = conn.execute(sql, [*params, limit, offset]).fetchall()

    total = int(result_rows[0]['_total_count']) if result_rows else 0
    summary = {
        'oke': int(result_rows[0]['_total_oke'] or 0) if result_rows else 0,
        'invited': int(result_rows[0]['_total_invited'] or 0) if result_rows else 0,
        'deal': int(result_rows[0]['_total_deal'] or 0) if result_rows else 0,
        'sample_requested': int(result_rows[0]['_total_requested'] or 0) if result_rows else 0,
        'shipped': int(result_rows[0]['_total_shipped'] or 0) if result_rows else 0,
        'vt_posted': int(result_rows[0]['_total_vt'] or 0) if result_rows else 0,
    }
    rows = []
    for result_row in result_rows:
        row = dict(result_row)
        for key in [key for key in row if key.startswith('_')]:
            row.pop(key)
        rows.append(row)
    return {
        'rows': rows,
        'total': total,
        'limit': limit,
        'offset': offset,
        'page': (offset // limit) + 1,
        'pages': max(1, (total + limit - 1) // limit),
        'summary': summary,
    }


def update_creator_tracker(affiliator_id, payload):
    if not isinstance(payload, dict):
        raise ValueError('Payload update tidak valid.')
    field = str(payload.get('field') or '').strip()
    if field not in TRACKER_FIELDS | {'phone', 'notes'}:
        raise ValueError('Kolom yang ingin diubah tidak valid.')

    with connect_db() as conn:
        conn.execute('BEGIN IMMEDIATE')
        affiliator = conn.execute(
            """
            SELECT id, fit_checked, invited, deal_confirmed,
                   sample_requested, sample_shipped, vt_posted
            FROM affiliators
            WHERE id = ?
            """,
            (affiliator_id,),
        ).fetchone()
        if affiliator is None:
            raise ValueError('Creator tidak ditemukan.')

        if field in {'phone', 'notes'}:
            value = clean_text(payload.get('value'), 80 if field == 'phone' else 2000)
            conn.execute(
                f"UPDATE affiliators SET {field} = ?, updated_at = datetime('now') WHERE id = ?",
                (value, affiliator_id),
            )
            list_field = 'phone' if field == 'phone' else 'notes'
            conn.execute(
                f'UPDATE creator_list_entries SET {list_field} = ? WHERE affiliator_id = ?',
                (value, affiliator_id),
            )
            return {'affiliator_id': affiliator_id, 'field': field, 'value': value or ''}

        raw_value = payload.get('value')
        if isinstance(raw_value, bool):
            value = int(raw_value)
        elif isinstance(raw_value, int) and raw_value in (0, 1):
            value = int(raw_value)
        else:
            raise ValueError('Nilai checkbox tidak valid.')

        conn.execute(
            """
            INSERT OR IGNORE INTO creator_tracker_statuses (
                affiliator_id, oke, invite, deal, req_sampel, kirim,
                vt1, vt2, vt3, vt4, vt5, vt_winn
            ) VALUES (?, ?, ?, ?, ?, ?, ?, 0, 0, 0, 0, 0)
            """,
            (
                affiliator_id,
                affiliator['fit_checked'],
                affiliator['invited'],
                affiliator['deal_confirmed'],
                affiliator['sample_requested'],
                affiliator['sample_shipped'],
                affiliator['vt_posted'],
            ),
        )
        conn.execute(
            f"UPDATE creator_tracker_statuses SET {field} = ?, updated_at = datetime('now') WHERE affiliator_id = ?",
            (value, affiliator_id),
        )

        canonical_field = TRACKER_TO_AFFILIATOR.get(field)
        if canonical_field:
            conn.execute(
                f"UPDATE affiliators SET {canonical_field} = ?, updated_at = datetime('now') WHERE id = ?",
                (value, affiliator_id),
            )
        elif field.startswith('vt'):
            vt_row = conn.execute(
                """
                SELECT (vt1 OR vt2 OR vt3 OR vt4 OR vt5 OR vt_winn) AS posted
                FROM creator_tracker_statuses
                WHERE affiliator_id = ?
                """,
                (affiliator_id,),
            ).fetchone()
            conn.execute(
                "UPDATE affiliators SET vt_posted = ?, updated_at = datetime('now') WHERE id = ?",
                (int(bool(vt_row['posted'])), affiliator_id),
            )
        return {'affiliator_id': affiliator_id, 'field': field, 'value': value}


def normalize_vt_url(value):
    text = str(value or '').strip()
    if not text:
        raise ValueError('URL VT wajib diisi.')
    if len(text) > 2000:
        raise ValueError('URL VT terlalu panjang.')
    if not re.match(r'^https?://', text, flags=re.I):
        text = f'https://{text}'
    parsed = urlparse(text)
    hostname = (parsed.hostname or '').lower()
    if hostname != 'tiktok.com' and not hostname.endswith('.tiktok.com'):
        raise ValueError('URL VT harus berasal dari TikTok.')
    if not parsed.path or parsed.path == '/':
        raise ValueError('URL VT TikTok tidak lengkap.')
    clean_path = parsed.path.rstrip('/')
    normalized = f'https://{hostname}{clean_path}'.lower()
    display_url = f'https://{hostname}{clean_path}'
    return display_url, normalized


def get_submission_link(conn, token):
    token = str(token or '').strip()
    if not re.fullmatch(r'[A-Za-z0-9_-]{20,100}', token):
        return None
    return conn.execute(
        """
        SELECT csl.id, csl.affiliator_id, csl.token, a.name,
               ah.handle AS username
        FROM creator_submission_links csl
        INNER JOIN affiliators a ON a.id = csl.affiliator_id
        INNER JOIN affiliator_handles ah
            ON ah.affiliator_id = a.id AND ah.platform = 'tiktok_shop'
        WHERE csl.token = ? AND csl.active = 1
          AND (csl.expires_at IS NULL OR csl.expires_at > datetime('now'))
        ORDER BY ah.id
        LIMIT 1
        """,
        (token,),
    ).fetchone()


def ensure_creator_action_link(affiliator_id, payload):
    regenerate = bool(payload.get('regenerate')) if isinstance(payload, dict) else False
    with connect_db() as conn:
        conn.execute('BEGIN IMMEDIATE')
        creator = conn.execute(
            """
            SELECT a.id, a.name, ah.handle AS username
            FROM affiliators a
            INNER JOIN affiliator_handles ah
                ON ah.affiliator_id = a.id AND ah.platform = 'tiktok_shop'
            WHERE a.id = ?
            ORDER BY ah.id
            LIMIT 1
            """,
            (affiliator_id,),
        ).fetchone()
        if creator is None:
            raise ValueError('Creator tidak ditemukan.')
        if regenerate:
            conn.execute(
                'UPDATE creator_submission_links SET active = 0 WHERE affiliator_id = ? AND active = 1',
                (affiliator_id,),
            )
        link = conn.execute(
            """
            SELECT id, token, created_at, last_used_at
            FROM creator_submission_links
            WHERE affiliator_id = ? AND active = 1
            LIMIT 1
            """,
            (affiliator_id,),
        ).fetchone()
        if link is None:
            token = secrets.token_urlsafe(32)
            link_id = conn.execute(
                """
                INSERT INTO creator_submission_links (affiliator_id, token)
                VALUES (?, ?)
                """,
                (affiliator_id, token),
            ).lastrowid
            link = conn.execute(
                """
                SELECT id, token, created_at, last_used_at
                FROM creator_submission_links WHERE id = ?
                """,
                (link_id,),
            ).fetchone()
        submissions = conn.execute(
            """
            SELECT id, vt_url, spark_code, status, submitted_at,
                   reviewed_at, review_notes, approved_vt_id
            FROM creator_vt_submissions
            WHERE affiliator_id = ?
            ORDER BY submitted_at DESC, id DESC
            LIMIT 100
            """,
            (affiliator_id,),
        ).fetchall()
        return {
            'affiliator_id': affiliator_id,
            'creator_name': creator['name'],
            'username': creator['username'],
            'token': link['token'],
            'submission_path': f"/apps/creator-submit.html?token={link['token']}",
            'created_at': link['created_at'],
            'last_used_at': link['last_used_at'],
            'submissions': [dict(row) for row in submissions],
        }


def get_creator_submission_form(query):
    token = (query.get('token') or [''])[0]
    with connect_db() as conn:
        link = get_submission_link(conn, token)
        if link is None:
            raise ValueError('Link tidak valid, sudah diganti, atau sudah kedaluwarsa.')
        count = conn.execute(
            'SELECT COUNT(*) AS count FROM creator_vt_submissions WHERE affiliator_id = ?',
            (link['affiliator_id'],),
        ).fetchone()['count']
    return {
        'creator_name': link['name'],
        'username': link['username'],
        'submitted_count': count,
    }


def submit_creator_vt(payload):
    if not isinstance(payload, dict):
        raise ValueError('Data submission tidak valid.')
    token = payload.get('token')
    vt_url, normalized_url = normalize_vt_url(payload.get('vt_url'))
    spark_code = clean_text(payload.get('spark_code'), 500)

    with connect_db() as conn:
        conn.execute('BEGIN IMMEDIATE')
        link = get_submission_link(conn, token)
        if link is None:
            raise ValueError('Link tidak valid, sudah diganti, atau sudah kedaluwarsa.')
        existing = conn.execute(
            """
            SELECT id, affiliator_id, status
            FROM creator_vt_submissions
            WHERE vt_url_normalized = ?
            LIMIT 1
            """,
            (normalized_url,),
        ).fetchone()
        if existing and existing['affiliator_id'] != link['affiliator_id']:
            raise ValueError('URL VT ini sudah pernah dikirim oleh creator lain.')
        if existing:
            if existing['status'] == 'approved':
                raise ValueError('URL VT ini sudah disetujui dan tersimpan.')
            conn.execute(
                """
                UPDATE creator_vt_submissions
                SET spark_code = COALESCE(?, spark_code), status = 'pending',
                    submitted_at = datetime('now'), review_notes = NULL
                WHERE id = ?
                """,
                (spark_code, existing['id']),
            )
            submission_id = existing['id']
            updated = True
        else:
            submission_id = conn.execute(
                """
                INSERT INTO creator_vt_submissions (
                    affiliator_id, submission_link_id, vt_url,
                    vt_url_normalized, spark_code
                ) VALUES (?, ?, ?, ?, ?)
                """,
                (
                    link['affiliator_id'],
                    link['id'],
                    vt_url,
                    normalized_url,
                    spark_code,
                ),
            ).lastrowid
            updated = False
        conn.execute(
            "UPDATE creator_submission_links SET last_used_at = datetime('now') WHERE id = ?",
            (link['id'],),
        )
        return {
            'submission_id': submission_id,
            'updated': updated,
            'status': 'pending',
            'username': link['username'],
        }


class AFSRequestHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(APP_DIR), **kwargs)

    def send_json(self, payload, status=HTTPStatus.OK):
        body = json.dumps(payload, ensure_ascii=False).encode('utf-8')
        self.send_response(status)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Cache-Control', 'no-store')
        self.end_headers()
        self.wfile.write(body)

    def read_json(self):
        try:
            length = int(self.headers.get('Content-Length', '0'))
        except ValueError as error:
            raise ValueError('Content-Length tidak valid.') from error
        if length <= 0 or length > MAX_BODY_BYTES:
            raise ValueError('Ukuran data kosong atau terlalu besar.')
        try:
            return json.loads(self.rfile.read(length).decode('utf-8'))
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise ValueError('JSON tidak valid.') from error

    def do_GET(self):
        parsed = urlparse(self.path)
        try:
            if parsed.path == '/api/health':
                self.send_json({
                    'ok': True,
                    'api_version': 3,
                    'features': ['creator_list', 'creator_tracker', 'creator_vt_submission'],
                    'database': str(DB_PATH),
                })
                return
            if parsed.path == '/api/creator-submit':
                self.send_json(get_creator_submission_form(parse_qs(parsed.query)))
                return
            if parsed.path == '/api/creator-list/dates':
                self.send_json(get_entry_dates())
                return
            if parsed.path == '/api/creator-tracker':
                self.send_json(get_creator_tracker(parse_qs(parsed.query)))
                return
            if parsed.path == '/api/creator-list':
                self.send_json(get_creator_list(parse_qs(parsed.query)))
                return
        except ValueError as error:
            self.send_json({'ok': False, 'message': str(error)}, HTTPStatus.BAD_REQUEST)
            return
        except sqlite3.Error as error:
            self.send_json(
                {'ok': False, 'message': f'Database error: {error}'},
                HTTPStatus.INTERNAL_SERVER_ERROR,
            )
            return
        super().do_GET()

    def do_PATCH(self):
        parsed = urlparse(self.path)
        match = re.fullmatch(r'/api/creator-tracker/(\d+)', parsed.path)
        if match is None:
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        try:
            result = update_creator_tracker(int(match.group(1)), self.read_json())
            self.send_json({'ok': True, **result})
        except ValueError as error:
            self.send_json({'ok': False, 'message': str(error)}, HTTPStatus.BAD_REQUEST)
        except sqlite3.Error as error:
            self.send_json(
                {'ok': False, 'message': f'Database error: {error}'},
                HTTPStatus.INTERNAL_SERVER_ERROR,
            )

    def do_POST(self):
        parsed = urlparse(self.path)
        try:
            action_match = re.fullmatch(r'/api/creator-action/(\d+)', parsed.path)
            if action_match:
                result = ensure_creator_action_link(
                    int(action_match.group(1)), self.read_json()
                )
                self.send_json({'ok': True, **result})
                return
            if parsed.path == '/api/creator-submit':
                result = submit_creator_vt(self.read_json())
                self.send_json({'ok': True, **result}, HTTPStatus.CREATED)
                return
            if parsed.path == '/api/creator-list':
                result = save_creator_list(self.read_json())
                self.send_json({'ok': True, **result}, HTTPStatus.CREATED)
                return
            self.send_error(HTTPStatus.NOT_FOUND)
        except ValueError as error:
            self.send_json({'ok': False, 'message': str(error)}, HTTPStatus.BAD_REQUEST)
        except sqlite3.Error as error:
            self.send_json(
                {'ok': False, 'message': f'Database error: {error}'},
                HTTPStatus.INTERNAL_SERVER_ERROR,
            )

    def log_message(self, format_string, *args):
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        sys.stderr.write(f'[{timestamp}] {self.address_string()} {format_string % args}\n')


if __name__ == '__main__':
    init_db()
    if '--init-only' in sys.argv:
        print(f'Database initialized: {DB_PATH}')
        raise SystemExit(0)
    server = ThreadingHTTPServer((HOST, PORT), AFSRequestHandler)
    print(f'AFS app: http://{HOST}:{PORT}')
    print(f'Database: {DB_PATH}')
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
