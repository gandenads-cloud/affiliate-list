#!/usr/bin/env python3
"""Synchronize an official sample-shipment batch to CSV and SQLite."""

import argparse
import csv
import json
import os
import re
import shutil
import sqlite3
import tempfile
from datetime import date
from pathlib import Path


APP_DIR = Path(__file__).resolve().parent.parent
DEFAULT_DB_PATH = APP_DIR / 'database' / 'afs.db'
DEFAULT_CSV_PATH = APP_DIR / 'username_produk.csv'
USERNAME_RE = re.compile(r'^[A-Za-z0-9._]{1,64}$')
PHONE_RE = re.compile(r'^\d{8,15}$')
PRODUCTS = {
    'LEGA': 'Tetulung LEGA 50gr Sabun Batang Kulit Alergi Sensitif Gentle Bar Soap Sudah BPOM',
    'VITA': 'Paket 1 Vitacream - Salep Herbal Alami Bantu Atasi Tubuh Gatal, Eksim dan Jamur',
}
STATUS = 'Dalam Pengiriman'


def load_items(path):
    payload = json.loads(path.read_text(encoding='utf-8'))
    if not isinstance(payload, list) or not payload:
        raise ValueError('Input harus berupa list JSON yang tidak kosong.')

    items = []
    seen = set()
    for position, raw in enumerate(payload, start=1):
        if not isinstance(raw, dict):
            raise ValueError(f'Item {position} bukan object JSON.')
        username = str(raw.get('username') or '').strip().lstrip('@')
        phone = re.sub(r'\D', '', str(raw.get('phone') or ''))
        product_key = str(raw.get('product') or '').strip().upper()
        note = str(raw.get('note') or '').strip() or None
        if not USERNAME_RE.fullmatch(username):
            raise ValueError(f'Username item {position} tidak valid: {username}')
        if not PHONE_RE.fullmatch(phone):
            raise ValueError(f'Nomor WA item {position} tidak valid: {phone}')
        if product_key not in PRODUCTS:
            raise ValueError(f'Produk item {position} tidak dikenal: {product_key}')
        pair = (username.lower(), PRODUCTS[product_key].lower())
        if pair in seen:
            raise ValueError(f'Duplikat input username + produk: {username} + {product_key}')
        seen.add(pair)
        items.append({
            'username': username,
            'username_normalized': username.lower(),
            'phone': phone,
            'product_key': product_key,
            'product': PRODUCTS[product_key],
            'note': note,
        })
    return items


def read_csv_rows(csv_path):
    with open(csv_path, 'r', encoding='utf-8-sig', newline='') as source:
        reader = csv.DictReader(source)
        if reader.fieldnames != ['username', 'produk', 'status']:
            raise ValueError('Header username_produk.csv tidak sesuai.')
        rows = list(reader)
    pairs = {}
    for index, row in enumerate(rows):
        pair = (row['username'].strip().lower(), row['produk'].strip().lower())
        if pair in pairs:
            raise ValueError(
                f'Duplikat existing username + produk pada CSV: {row["username"]}'
            )
        pairs[pair] = index
    return rows, pairs


def plan_csv(csv_path, items, official_status_update):
    rows, pairs = read_csv_rows(csv_path)
    appended = 0
    updated = 0
    skipped = 0
    for item in items:
        pair = (item['username_normalized'], item['product'].lower())
        existing_index = pairs.get(pair)
        if existing_index is None:
            pairs[pair] = len(rows)
            rows.append({
                'username': item['username'],
                'produk': item['product'],
                'status': STATUS,
            })
            appended += 1
        elif official_status_update and rows[existing_index]['status'] != STATUS:
            rows[existing_index]['status'] = STATUS
            updated += 1
        else:
            skipped += 1
    return rows, {'csv_appended': appended, 'csv_updated': updated, 'csv_skipped': skipped}


def inspect_db(conn, items):
    existing_creators = 0
    existing_pairs = 0
    for item in items:
        creator = conn.execute(
            """
            SELECT affiliator_id
            FROM affiliator_handles
            WHERE platform = 'tiktok_shop'
              AND LOWER(TRIM(handle)) = ?
            """,
            (item['username_normalized'],),
        ).fetchone()
        if not creator:
            continue
        existing_creators += 1
        existing_pairs += int(bool(conn.execute(
            """
            SELECT 1
            FROM creator_product_statuses
            WHERE affiliator_id = ? AND LOWER(TRIM(product)) = LOWER(TRIM(?))
            LIMIT 1
            """,
            (creator[0], item['product']),
        ).fetchone()))
    return {
        'creators_existing': existing_creators,
        'creators_new': len(items) - existing_creators,
        'db_pairs_existing': existing_pairs,
        'db_pairs_new': len(items) - existing_pairs,
    }


def ensure_default_user(conn):
    row = conn.execute(
        "SELECT id FROM users WHERE email = 'system@local.afs' LIMIT 1"
    ).fetchone()
    if row:
        return row[0]
    return conn.execute(
        "INSERT INTO users (name, email) VALUES ('System', 'system@local.afs')"
    ).lastrowid


def get_or_create_creator(conn, item, shipment_date, default_user_id):
    row = conn.execute(
        """
        SELECT affiliator_id
        FROM affiliator_handles
        WHERE platform = 'tiktok_shop'
          AND LOWER(TRIM(handle)) = ?
        """,
        (item['username_normalized'],),
    ).fetchone()
    if row:
        return row[0], False

    affiliator_id = conn.execute(
        """
        INSERT INTO affiliators (
            name, primary_platform, pic_user_id, stage, stage_since, source,
            joined_at, contact_status, phone, sample_requested,
            sample_shipped, created_at, updated_at
        ) VALUES (?, 'tiktok_shop', ?, 'sample_shipped', ?,
                  'sample_shipment_import', ?, 'contacted', ?, 1, 1,
                  datetime('now'), datetime('now'))
        """,
        (
            item['username'], default_user_id, shipment_date,
            shipment_date, item['phone'],
        ),
    ).lastrowid
    conn.execute(
        """
        INSERT INTO affiliator_handles (
            affiliator_id, platform, handle, profile_url
        ) VALUES (?, 'tiktok_shop', ?, ?)
        """,
        (
            affiliator_id,
            item['username'],
            f"https://www.tiktok.com/@{item['username']}",
        ),
    )
    return affiliator_id, True


def append_note(current, note):
    current = str(current or '').strip()
    if not note or note.lower() in current.lower():
        return current or None
    return f'{current}\n{note}' if current else note


def update_creator(conn, affiliator_id, item, shipment_date):
    current = conn.execute(
        'SELECT notes, sample_shipped FROM affiliators WHERE id = ?',
        (affiliator_id,),
    ).fetchone()
    notes = append_note(current['notes'], item['note'])
    conn.execute(
        """
        UPDATE affiliators
        SET phone = ?, notes = ?, stage = 'sample_shipped', stage_since = ?,
            sample_requested = 1, sample_shipped = 1,
            updated_at = datetime('now')
        WHERE id = ?
        """,
        (item['phone'], notes, shipment_date, affiliator_id),
    )
    conn.execute(
        """
        UPDATE creator_list_entries
        SET phone = ?, notes = ?
        WHERE affiliator_id = ?
        """,
        (item['phone'], notes, affiliator_id),
    )
    conn.execute(
        """
        INSERT OR IGNORE INTO creator_tracker_statuses (
            affiliator_id, oke, invite, deal, req_sampel, kirim,
            vt1, vt2, vt3, vt4, vt5, vt_winn
        )
        SELECT id, fit_checked, invited, deal_confirmed, 1, 1,
               vt_posted, 0, 0, 0, 0, 0
        FROM affiliators WHERE id = ?
        """,
        (affiliator_id,),
    )
    conn.execute(
        """
        UPDATE creator_tracker_statuses
        SET req_sampel = 1, kirim = 1, updated_at = datetime('now')
        WHERE affiliator_id = ?
        """,
        (affiliator_id,),
    )
    return int(bool(current['sample_shipped']))


def upsert_product_status(
    conn, affiliator_id, item, batch_id, official_status_update
):
    existing = conn.execute(
        """
        SELECT id, status
        FROM creator_product_statuses
        WHERE affiliator_id = ? AND LOWER(TRIM(product)) = LOWER(TRIM(?))
        LIMIT 1
        """,
        (affiliator_id, item['product']),
    ).fetchone()
    if existing:
        if official_status_update:
            conn.execute(
                """
                UPDATE creator_product_statuses
                SET status = ?, source_batch_id = ?, updated_at = datetime('now')
                WHERE id = ?
                """,
                (STATUS, batch_id, existing['id']),
            )
            return 'updated'
        return 'skipped'
    conn.execute(
        """
        INSERT INTO creator_product_statuses (
            affiliator_id, product, status, source_batch_id
        ) VALUES (?, ?, ?, ?)
        """,
        (affiliator_id, item['product'], STATUS, batch_id),
    )
    return 'inserted'


def log_activity(
    conn, affiliator_id, default_user_id, item, shipment_date, batch_id,
    was_shipped,
):
    note = json.dumps(
        {'date': shipment_date, 'product': item['product']},
        ensure_ascii=False,
        sort_keys=True,
    )
    exists = conn.execute(
        """
        SELECT 1 FROM activity_logs
        WHERE affiliator_id = ? AND type = 'sample_shipped'
          AND batch_id = ? AND note = ?
        LIMIT 1
        """,
        (affiliator_id, batch_id, note),
    ).fetchone()
    if exists:
        return False
    conn.execute(
        """
        INSERT INTO activity_logs (
            affiliator_id, user_id, type, from_value, to_value, note, batch_id
        ) VALUES (?, ?, 'sample_shipped', ?, '1', ?, ?)
        """,
        (affiliator_id, default_user_id, str(was_shipped), note, batch_id),
    )
    return True


def write_csv_temp(csv_path, rows):
    file_descriptor, temp_name = tempfile.mkstemp(
        prefix=f'.{csv_path.name}.', suffix='.tmp', dir=csv_path.parent
    )
    try:
        with os.fdopen(file_descriptor, 'w', encoding='utf-8', newline='') as target:
            writer = csv.DictWriter(
                target,
                fieldnames=['username', 'produk', 'status'],
                lineterminator='\r\n',
            )
            writer.writeheader()
            writer.writerows(rows)
            target.flush()
            os.fsync(target.fileno())
        os.chmod(temp_name, csv_path.stat().st_mode)
        return Path(temp_name)
    except Exception:
        Path(temp_name).unlink(missing_ok=True)
        raise


def apply_batch(
    conn, csv_path, backup_path, rows, items, shipment_date, batch_id,
    official_status_update,
):
    temp_csv = write_csv_temp(csv_path, rows)
    summary = {
        'creators_created': 0,
        'product_statuses_inserted': 0,
        'product_statuses_updated': 0,
        'product_statuses_skipped': 0,
        'activity_logs_inserted': 0,
    }
    csv_replaced = False
    conn.execute('BEGIN IMMEDIATE')
    try:
        default_user_id = ensure_default_user(conn)
        for item in items:
            affiliator_id, created = get_or_create_creator(
                conn, item, shipment_date, default_user_id
            )
            summary['creators_created'] += int(created)
            was_shipped = update_creator(conn, affiliator_id, item, shipment_date)
            action = upsert_product_status(
                conn, affiliator_id, item, batch_id, official_status_update
            )
            summary[f'product_statuses_{action}'] += 1
            summary['activity_logs_inserted'] += int(log_activity(
                conn, affiliator_id, default_user_id, item, shipment_date,
                batch_id, was_shipped,
            ))

        os.replace(temp_csv, csv_path)
        csv_replaced = True
        conn.commit()
        return summary
    except Exception:
        conn.rollback()
        if csv_replaced:
            shutil.copy2(backup_path, csv_path)
        else:
            temp_csv.unlink(missing_ok=True)
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('input_json', type=Path)
    parser.add_argument('--date', required=True, dest='shipment_date')
    parser.add_argument('--batch-id', required=True)
    parser.add_argument('--db', type=Path, default=DEFAULT_DB_PATH)
    parser.add_argument('--csv', type=Path, default=DEFAULT_CSV_PATH)
    parser.add_argument('--backup-csv', type=Path)
    parser.add_argument('--official-status-update', action='store_true')
    parser.add_argument('--apply', action='store_true')
    args = parser.parse_args()

    shipment_date = date.fromisoformat(args.shipment_date).isoformat()
    items = load_items(args.input_json)
    csv_rows, csv_summary = plan_csv(
        args.csv, items, args.official_status_update
    )
    conn = sqlite3.connect(args.db, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute('PRAGMA foreign_keys = ON')
    try:
        summary = {
            'mode': 'apply' if args.apply else 'dry-run',
            'shipment_date': shipment_date,
            'batch_id': args.batch_id,
            'received': len(items),
            **csv_summary,
            **inspect_db(conn, items),
        }
        if args.apply:
            if args.backup_csv is None or not args.backup_csv.is_file():
                raise ValueError('--backup-csv wajib menunjuk backup CSV yang valid.')
            summary.update(apply_batch(
                conn, args.csv, args.backup_csv, csv_rows, items,
                shipment_date, args.batch_id, args.official_status_update,
            ))
        print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))
    finally:
        conn.close()


if __name__ == '__main__':
    main()
