#!/usr/bin/env python3
"""Validate and atomically import TikTok Shop video analytics XLSX exports."""

import argparse
import calendar
import hashlib
import json
import re
import sqlite3
import sys
from datetime import date, datetime
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from pathlib import Path
from xml.etree import ElementTree as ET
from zipfile import BadZipFile, ZipFile

try:
    from .migrate import run_migrations
except ImportError:
    from migrate import run_migrations


APP_DIR = Path(__file__).resolve().parent.parent
DEFAULT_DB_PATH = APP_DIR / 'database' / 'afs.db'
XML_NS = {'m': 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}
USERNAME_RE = re.compile(r'^[A-Za-z0-9._]{1,64}$')
ID_RE = re.compile(r'^\d+$')
VIDEO_URL_RE = re.compile(
    r'^https://www\.tiktok\.com/@([^/]+)/video/(\d+)(?:[/?].*)?$',
    re.IGNORECASE,
)
PLACEHOLDERS = {'', '-', '--', 'n/a', 'null'}

HEADERS = [
    'Video title',
    'Video ID',
    'Post date',
    'Video link',
    'Creator name',
    'Product ID',
    'GMV dari video afiliasi',
    'Pesanan dari video',
    'AOV',
    'Produk yang terjual melalui video',
    'Pengembalian dana',
    'Produk yang dikembalikan dananya',
    'Suka',
    'Komentar',
    'Dibagikan',
    'Impresi produk di video',
    'Klik produk di video',
    'Persentase menonton hingga selesai',
    'Tayangan video',
    'CTR',
    'GPM Video',
    'Interaksi',
    'Rata-rata GMV per pembeli',
    'Perkiraan komisi',
]


def column_index(cell_reference):
    match = re.match(r'[A-Z]+', cell_reference or '')
    if match is None:
        raise ValueError(f'Invalid XLSX cell reference: {cell_reference}')
    result = 0
    for character in match.group():
        result = result * 26 + ord(character) - 64
    return result - 1


def cell_value(cell):
    if cell.attrib.get('t') == 'inlineStr':
        return ''.join(node.text or '' for node in cell.findall('.//m:t', XML_NS))
    value = cell.find('m:v', XML_NS)
    return '' if value is None else value.text or ''


def worksheet_rows(xlsx_path):
    try:
        with ZipFile(xlsx_path) as archive:
            root = ET.fromstring(archive.read('xl/worksheets/sheet1.xml'))
    except (BadZipFile, KeyError, ET.ParseError) as error:
        raise ValueError(f'XLSX tidak dapat dibaca: {error}') from error

    rows = []
    for row_element in root.findall('.//m:sheetData/m:row', XML_NS):
        values = [''] * len(HEADERS)
        for cell in row_element.findall('m:c', XML_NS):
            index = column_index(cell.attrib.get('r'))
            if index < len(values):
                values[index] = cell_value(cell).strip()
        rows.append((int(row_element.attrib.get('r', len(rows) + 1)), values))
    return rows


def is_placeholder(value):
    return str(value or '').strip().lower() in PLACEHOLDERS


def parse_money(value, field):
    text = str(value or '').strip()
    if is_placeholder(text):
        raise ValueError(f'{field} kosong')
    negative = text.startswith('-')
    digits = re.sub(r'[^0-9]', '', text)
    if not digits:
        raise ValueError(f'{field} bukan nominal valid: {text}')
    result = int(digits) * (-1 if negative else 1)
    if result < 0:
        raise ValueError(f'{field} tidak boleh negatif: {text}')
    return result


def parse_count(value, field):
    text = str(value or '').strip()
    if is_placeholder(text):
        raise ValueError(f'{field} kosong')
    normalized = text.replace('.', '').replace(',', '')
    if not normalized.isdigit():
        raise ValueError(f'{field} bukan bilangan bulat: {text}')
    return int(normalized)


def parse_percent_bps(value, field):
    text = str(value or '').strip()
    if is_placeholder(text):
        raise ValueError(f'{field} kosong')
    try:
        percent = Decimal(text.rstrip('%').replace(',', '.'))
    except InvalidOperation as error:
        raise ValueError(f'{field} bukan persentase valid: {text}') from error
    if percent < 0:
        raise ValueError(f'{field} tidak boleh negatif: {text}')
    return int((percent * 100).quantize(Decimal('1'), rounding=ROUND_HALF_UP))


def parse_post_date(value):
    text = str(value or '').strip()
    if is_placeholder(text):
        return None
    for date_format in ('%m/%d/%Y %H:%M', '%m/%d/%Y %H:%M:%S'):
        try:
            return datetime.strptime(text, date_format).strftime('%Y-%m-%d %H:%M:%S')
        except ValueError:
            continue
    raise ValueError(f'Post date tidak valid: {text}')


def normalize_row(source_row_no, values):
    raw = dict(zip(HEADERS, values))
    video_id = raw['Video ID'].strip()
    if not ID_RE.fullmatch(video_id):
        raise ValueError(f'Video ID tidak valid: {video_id}')

    creator = raw['Creator name'].strip().lstrip('@')
    if not USERNAME_RE.fullmatch(creator):
        raise ValueError(f'Creator name tidak valid: {creator}')

    video_url = raw['Video link'].strip()
    url_match = VIDEO_URL_RE.fullmatch(video_url)
    if url_match is None:
        raise ValueError(f'Video link tidak valid: {video_url}')
    if url_match.group(1).lower() != creator.lower():
        raise ValueError('Creator name tidak cocok dengan username pada Video link')
    if url_match.group(2) != video_id:
        raise ValueError('Video ID tidak cocok dengan ID pada Video link')

    product_ids = []
    for product_id in raw['Product ID'].split(','):
        product_id = product_id.strip()
        if not ID_RE.fullmatch(product_id):
            raise ValueError(f'Product ID tidak valid: {product_id}')
        if product_id not in product_ids:
            product_ids.append(product_id)
    if not product_ids:
        raise ValueError('Product ID kosong')

    title = raw['Video title'].strip()
    if is_placeholder(title):
        title = None

    normalized = {
        'source_row_no': source_row_no,
        'video_id': video_id,
        'live_at': parse_post_date(raw['Post date']),
        'url': video_url,
        'creator': creator,
        'creator_normalized': creator.lower(),
        'title': title,
        'product_ids': product_ids,
        'gmv_idr': parse_money(raw['GMV dari video afiliasi'], 'GMV'),
        'orders': parse_count(raw['Pesanan dari video'], 'Pesanan'),
        'aov_idr': parse_money(raw['AOV'], 'AOV'),
        'units_sold': parse_count(
            raw['Produk yang terjual melalui video'], 'Produk terjual'
        ),
        'refund_idr': parse_money(raw['Pengembalian dana'], 'Pengembalian dana'),
        'units_refunded': parse_count(
            raw['Produk yang dikembalikan dananya'], 'Produk direfund'
        ),
        'likes': parse_count(raw['Suka'], 'Suka'),
        'comments': parse_count(raw['Komentar'], 'Komentar'),
        'shares': parse_count(raw['Dibagikan'], 'Dibagikan'),
        'product_impressions': parse_count(
            raw['Impresi produk di video'], 'Impresi produk'
        ),
        'product_clicks': parse_count(raw['Klik produk di video'], 'Klik produk'),
        'completion_rate_bps': parse_percent_bps(
            raw['Persentase menonton hingga selesai'], 'Completion rate'
        ),
        'views': parse_count(raw['Tayangan video'], 'Tayangan video'),
        'ctr_bps': parse_percent_bps(raw['CTR'], 'CTR'),
        'gpm_idr': parse_money(raw['GPM Video'], 'GPM Video'),
        'interaction_rate_bps': parse_percent_bps(raw['Interaksi'], 'Interaksi'),
        'average_gmv_per_buyer_idr': parse_money(
            raw['Rata-rata GMV per pembeli'], 'Rata-rata GMV per pembeli'
        ),
        'estimated_commission_idr': parse_money(
            raw['Perkiraan komisi'], 'Perkiraan komisi'
        ),
        'source_raw_json': json.dumps(
            raw, ensure_ascii=False, separators=(',', ':'), sort_keys=True
        ),
    }
    return normalized


def read_export(xlsx_path):
    rows = worksheet_rows(xlsx_path)
    if len(rows) < 3:
        raise ValueError('XLSX tidak memiliki header, deskripsi, dan data.')
    actual_headers = rows[0][1]
    if actual_headers != HEADERS:
        missing = sorted(set(HEADERS) - set(actual_headers))
        extra = sorted(set(actual_headers) - set(HEADERS))
        raise ValueError(
            'Header XLSX tidak sesuai. '
            f'Missing={missing or "-"}; extra={extra or "-"}'
        )

    normalized_rows = []
    errors = []
    seen_video_ids = set()
    for source_row_no, values in rows[2:]:
        if not any(values):
            continue
        try:
            row = normalize_row(source_row_no, values)
            if row['video_id'] in seen_video_ids:
                raise ValueError(f"Video ID duplikat dalam file: {row['video_id']}")
            seen_video_ids.add(row['video_id'])
            normalized_rows.append(row)
        except ValueError as error:
            errors.append({
                'source_row_no': source_row_no,
                'message': str(error),
                'raw': dict(zip(HEADERS, values)),
            })
    return normalized_rows, errors


def file_sha256(path):
    digest = hashlib.sha256()
    with open(path, 'rb') as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def report_period(value):
    match = re.fullmatch(r'(\d{4})-(\d{2})', value or '')
    if match is None:
        raise ValueError('Periode harus berformat YYYY-MM.')
    year, month = map(int, match.groups())
    if not 1 <= month <= 12:
        raise ValueError('Bulan pada periode tidak valid.')
    last_day = calendar.monthrange(year, month)[1]
    return date(year, month, 1).isoformat(), date(year, month, last_day).isoformat()


def inspect_database(conn, rows, source_hash):
    duplicate = conn.execute(
        """
        SELECT id, status, imported_at
        FROM video_import_batches
        WHERE source_sha256 = ?
        """,
        (source_hash,),
    ).fetchone()
    creator_handles = {
        row['normalized']: row['affiliator_id']
        for row in conn.execute(
            """
            SELECT LOWER(TRIM(handle)) AS normalized, affiliator_id
            FROM affiliator_handles
            WHERE platform = 'tiktok_shop'
            """
        )
    }
    existing_videos = {
        row[0]
        for row in conn.execute(
            """
            SELECT platform_video_id
            FROM vts
            WHERE platform = 'tiktok_shop' AND platform_video_id IS NOT NULL
            """
        )
    }
    existing_products = {
        row[0]
        for row in conn.execute(
            """
            SELECT platform_product_id
            FROM products
            WHERE platform = 'tiktok_shop'
            """
        )
    }
    creators = {row['creator_normalized'] for row in rows}
    videos = {row['video_id'] for row in rows}
    products = {product_id for row in rows for product_id in row['product_ids']}
    return {
        'duplicate_batch': dict(duplicate) if duplicate else None,
        'creators_total': len(creators),
        'creators_existing': len(creators & creator_handles.keys()),
        'creators_new': len(creators - creator_handles.keys()),
        'videos_total': len(videos),
        'videos_existing': len(videos & existing_videos),
        'videos_new': len(videos - existing_videos),
        'products_total': len(products),
        'products_existing': len(products & existing_products),
        'products_new': len(products - existing_products),
        'missing_dates': sum(row['live_at'] is None for row in rows),
        'missing_titles': sum(row['title'] is None for row in rows),
        'multi_product_videos': sum(len(row['product_ids']) > 1 for row in rows),
        'gmv_total_idr': sum(row['gmv_idr'] for row in rows),
        'orders_total': sum(row['orders'] for row in rows),
        'estimated_commission_total_idr': sum(
            row['estimated_commission_idr'] for row in rows
        ),
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


def get_or_create_creator(conn, row, default_user_id, imported_on):
    existing = conn.execute(
        """
        SELECT affiliator_id
        FROM affiliator_handles
        WHERE platform = 'tiktok_shop'
          AND LOWER(TRIM(handle)) = ?
        """,
        (row['creator_normalized'],),
    ).fetchone()
    if existing:
        return existing[0], False

    cursor = conn.execute(
        """
        INSERT INTO affiliators (
            name, primary_platform, pic_user_id, stage, stage_since,
            source, joined_at, contact_status, created_at, updated_at
        ) VALUES (?, 'tiktok_shop', ?, 'new', ?, 'video_analytics_xlsx', ?,
                  'contacted', datetime('now'), datetime('now'))
        """,
        (row['creator'], default_user_id, imported_on, imported_on),
    )
    affiliator_id = cursor.lastrowid
    conn.execute(
        """
        INSERT INTO affiliator_handles (
            affiliator_id, platform, handle, profile_url
        ) VALUES (?, 'tiktok_shop', ?, ?)
        """,
        (
            affiliator_id,
            row['creator'],
            f"https://www.tiktok.com/@{row['creator']}",
        ),
    )
    return affiliator_id, True


def upsert_video(conn, row, affiliator_id):
    existing = conn.execute(
        """
        SELECT id, affiliator_id
        FROM vts
        WHERE platform = 'tiktok_shop' AND platform_video_id = ?
        """,
        (row['video_id'],),
    ).fetchone()
    if existing and existing['affiliator_id'] != affiliator_id:
        raise ValueError(
            f"Video {row['video_id']} sudah terhubung ke creator lain."
        )

    if existing:
        conn.execute(
            """
            UPDATE vts
            SET url = ?,
                title_or_caption = COALESCE(?, title_or_caption),
                live_at = COALESCE(?, live_at),
                views = ?, likes = ?, comments = ?, shares = ?,
                gmv = ?, commission = ?, metrics_updated_at = datetime('now'),
                updated_at = datetime('now')
            WHERE id = ?
            """,
            (
                row['url'], row['title'], row['live_at'], row['views'],
                row['likes'], row['comments'], row['shares'], row['gmv_idr'],
                row['estimated_commission_idr'], existing['id'],
            ),
        )
        return existing['id'], False

    cursor = conn.execute(
        """
        INSERT INTO vts (
            affiliator_id, platform, url, title_or_caption, live_at,
            views, likes, comments, shares, gmv, commission,
            metrics_updated_at, data_source, platform_video_id
        ) VALUES (?, 'tiktok_shop', ?, ?, ?, ?, ?, ?, ?, ?, ?,
                  datetime('now'), 'tiktok_shop_video_export', ?)
        """,
        (
            affiliator_id, row['url'], row['title'], row['live_at'], row['views'],
            row['likes'], row['comments'], row['shares'], row['gmv_idr'],
            row['estimated_commission_idr'], row['video_id'],
        ),
    )
    return cursor.lastrowid, True


def get_or_create_product(conn, product_id):
    existing = conn.execute(
        """
        SELECT id
        FROM products
        WHERE platform = 'tiktok_shop' AND platform_product_id = ?
        """,
        (product_id,),
    ).fetchone()
    if existing:
        return existing[0], False
    cursor = conn.execute(
        """
        INSERT INTO products (platform, platform_product_id)
        VALUES ('tiktok_shop', ?)
        """,
        (product_id,),
    )
    return cursor.lastrowid, True


def insert_snapshot(conn, batch_id, video_id, row):
    conn.execute(
        """
        INSERT INTO video_metric_snapshots (
            video_id, import_batch_id, source_row_no, product_ids_json,
            gmv_idr, orders, aov_idr, units_sold, refund_idr,
            units_refunded, likes, comments, shares, product_impressions,
            product_clicks, completion_rate_bps, views, ctr_bps, gpm_idr,
            interaction_rate_bps, average_gmv_per_buyer_idr,
            estimated_commission_idr, source_raw_json
        ) VALUES (
            :video_id, :import_batch_id, :source_row_no, :product_ids_json,
            :gmv_idr, :orders, :aov_idr, :units_sold, :refund_idr,
            :units_refunded, :likes, :comments, :shares,
            :product_impressions, :product_clicks, :completion_rate_bps,
            :views, :ctr_bps, :gpm_idr, :interaction_rate_bps,
            :average_gmv_per_buyer_idr, :estimated_commission_idr,
            :source_raw_json
        )
        """,
        {
            **row,
            'video_id': video_id,
            'import_batch_id': batch_id,
            'product_ids_json': json.dumps(row['product_ids'], separators=(',', ':')),
        },
    )


def apply_import(conn, xlsx_path, source_hash, period_start, period_end, rows, plan):
    if plan['duplicate_batch']:
        return {
            **plan,
            'status': 'skipped_duplicate',
            'batch_id': plan['duplicate_batch']['id'],
        }

    imported_on = date.today().isoformat()
    conn.execute('BEGIN IMMEDIATE')
    try:
        duplicate = conn.execute(
            'SELECT id FROM video_import_batches WHERE source_sha256 = ?',
            (source_hash,),
        ).fetchone()
        if duplicate:
            conn.rollback()
            return {
                **plan,
                'status': 'skipped_duplicate',
                'batch_id': duplicate[0],
            }

        batch_id = conn.execute(
            """
            INSERT INTO video_import_batches (
                source_filename, source_sha256, report_period_start,
                report_period_end, row_count, status
            ) VALUES (?, ?, ?, ?, ?, 'running')
            """,
            (xlsx_path.name, source_hash, period_start, period_end, len(rows)),
        ).lastrowid

        default_user_id = ensure_default_user(conn)
        created_creators = 0
        created_videos = 0
        created_products = 0
        creator_cache = {}
        product_cache = {}

        for row in rows:
            creator_key = row['creator_normalized']
            if creator_key not in creator_cache:
                creator_cache[creator_key], created = get_or_create_creator(
                    conn, row, default_user_id, imported_on
                )
                created_creators += int(created)
            affiliator_id = creator_cache[creator_key]

            video_id, created = upsert_video(conn, row, affiliator_id)
            created_videos += int(created)

            for platform_product_id in row['product_ids']:
                if platform_product_id not in product_cache:
                    product_cache[platform_product_id], created = get_or_create_product(
                        conn, platform_product_id
                    )
                    created_products += int(created)
                product_id = product_cache[platform_product_id]
                conn.execute(
                    """
                    INSERT INTO video_products (
                        video_id, product_id, first_seen_batch_id,
                        last_seen_batch_id
                    ) VALUES (?, ?, ?, ?)
                    ON CONFLICT(video_id, product_id) DO UPDATE SET
                        last_seen_batch_id = excluded.last_seen_batch_id,
                        updated_at = datetime('now')
                    """,
                    (video_id, product_id, batch_id, batch_id),
                )

            insert_snapshot(conn, batch_id, video_id, row)

        result = {
            **plan,
            'status': 'completed',
            'batch_id': batch_id,
            'creators_created': created_creators,
            'videos_created': created_videos,
            'products_created': created_products,
            'snapshots_created': len(rows),
        }
        conn.execute(
            """
            UPDATE video_import_batches
            SET status = 'completed', summary_json = ?,
                completed_at = datetime('now')
            WHERE id = ?
            """,
            (json.dumps(result, ensure_ascii=False, sort_keys=True), batch_id),
        )
        conn.commit()
        return result
    except Exception:
        conn.rollback()
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('xlsx', type=Path)
    parser.add_argument('--period', required=True, help='Reporting period in YYYY-MM')
    parser.add_argument('--db', type=Path, default=DEFAULT_DB_PATH)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument('--dry-run', action='store_true', help='Validate without writing')
    mode.add_argument('--apply', action='store_true', help='Commit the import')
    args = parser.parse_args()

    if not args.xlsx.is_file():
        parser.error(f'File tidak ditemukan: {args.xlsx}')
    period_start, period_end = report_period(args.period)
    rows, errors = read_export(args.xlsx)
    source_hash = file_sha256(args.xlsx)

    run_migrations(args.db, quiet=True)
    conn = sqlite3.connect(args.db, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute('PRAGMA foreign_keys = ON')
    try:
        plan = inspect_database(conn, rows, source_hash)
        output = {
            'mode': 'apply' if args.apply else 'dry-run',
            'source_file': str(args.xlsx),
            'source_sha256': source_hash,
            'period_start': period_start,
            'period_end': period_end,
            'source_rows': len(rows) + len(errors),
            'valid_rows': len(rows),
            'invalid_rows': len(errors),
            **plan,
        }
        if errors:
            output['errors'] = errors[:20]
            print(json.dumps(output, ensure_ascii=False, indent=2, sort_keys=True))
            raise SystemExit(1)
        if args.apply:
            output.update(
                apply_import(
                    conn, args.xlsx, source_hash, period_start, period_end,
                    rows, plan,
                )
            )
        print(json.dumps(output, ensure_ascii=False, indent=2, sort_keys=True))
    finally:
        conn.close()


if __name__ == '__main__':
    try:
        main()
    except (ValueError, sqlite3.Error) as error:
        print(f'ERROR: {error}', file=sys.stderr)
        raise SystemExit(1)
