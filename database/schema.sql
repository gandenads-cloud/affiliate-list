PRAGMA journal_mode = WAL;
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    email TEXT UNIQUE,
    created_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS schema_migrations (
    version INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    checksum TEXT NOT NULL,
    applied_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS affiliators (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    brand TEXT,
    primary_platform TEXT NOT NULL DEFAULT 'tiktok_shop',
    tier TEXT,
    content_categories TEXT,
    phone TEXT,
    email TEXT,
    shipping_address TEXT,
    recipient_name TEXT,
    pic_user_id INTEGER NOT NULL,
    stage TEXT NOT NULL,
    stage_since TEXT,
    followup_at TEXT,
    followup_note TEXT,
    source TEXT NOT NULL DEFAULT 'manual_outreach',
    joined_at TEXT NOT NULL,
    notes TEXT,
    created_at TEXT DEFAULT (datetime('now')),
    updated_at TEXT DEFAULT (datetime('now')),
    contact_list TEXT,
    manager TEXT,
    contact_status TEXT NOT NULL DEFAULT 'contacted',
    fit_checked INTEGER NOT NULL DEFAULT 0,
    invited INTEGER NOT NULL DEFAULT 0,
    deal_confirmed INTEGER NOT NULL DEFAULT 0,
    sample_requested INTEGER NOT NULL DEFAULT 0,
    sample_shipped INTEGER NOT NULL DEFAULT 0,
    sample_received INTEGER NOT NULL DEFAULT 0,
    vt_posted INTEGER NOT NULL DEFAULT 0,
    FOREIGN KEY (pic_user_id) REFERENCES users(id)
);

CREATE TABLE IF NOT EXISTS affiliator_handles (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    affiliator_id INTEGER NOT NULL,
    platform TEXT NOT NULL,
    platform_id TEXT,
    handle TEXT NOT NULL,
    profile_url TEXT,
    followers INTEGER,
    followers_checked_at TEXT,
    UNIQUE(platform, handle),
    UNIQUE(platform, platform_id),
    FOREIGN KEY (affiliator_id) REFERENCES affiliators(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS agreements (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    affiliator_id INTEGER NOT NULL,
    deal_date TEXT,
    fee_type TEXT,
    fee_amount REAL,
    commission_rate_percent REAL,
    required_vts INTEGER,
    valid_from TEXT,
    valid_until TEXT,
    proof_url TEXT,
    status TEXT,
    notes TEXT,
    created_at TEXT DEFAULT (datetime('now')),
    updated_at TEXT DEFAULT (datetime('now')),
    FOREIGN KEY (affiliator_id) REFERENCES affiliators(id)
);

CREATE TABLE IF NOT EXISTS vts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    affiliator_id INTEGER NOT NULL,
    platform TEXT NOT NULL,
    url TEXT NOT NULL UNIQUE,
    title_or_caption TEXT,
    live_at TEXT,
    has_boost INTEGER NOT NULL DEFAULT 0,
    boost_code TEXT,
    boost_checked_at TEXT,
    views INTEGER,
    likes INTEGER,
    comments INTEGER,
    shares INTEGER,
    gmv INTEGER,
    commission INTEGER,
    metrics_updated_at TEXT,
    counts_to_agreement INTEGER NOT NULL DEFAULT 0,
    data_source TEXT NOT NULL DEFAULT 'manual',
    notes TEXT,
    created_at TEXT DEFAULT (datetime('now')),
    updated_at TEXT DEFAULT (datetime('now')),
    agreement_id INTEGER,
    platform_video_id TEXT,
    UNIQUE(platform, platform_video_id),
    FOREIGN KEY (affiliator_id) REFERENCES affiliators(id) ON DELETE CASCADE,
    FOREIGN KEY (agreement_id) REFERENCES agreements(id)
);

CREATE TABLE IF NOT EXISTS activity_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    affiliator_id INTEGER,
    user_id INTEGER,
    type TEXT,
    from_value TEXT,
    to_value TEXT,
    note TEXT,
    created_at TEXT DEFAULT (datetime('now')),
    batch_id TEXT,
    FOREIGN KEY (affiliator_id) REFERENCES affiliators(id),
    FOREIGN KEY (user_id) REFERENCES users(id)
);

CREATE TABLE IF NOT EXISTS creator_product_statuses (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    affiliator_id INTEGER NOT NULL,
    product TEXT,
    status TEXT,
    source_batch_id TEXT,
    created_at TEXT DEFAULT (datetime('now')),
    updated_at TEXT DEFAULT (datetime('now')),
    FOREIGN KEY (affiliator_id) REFERENCES affiliators(id)
);

CREATE TABLE IF NOT EXISTS settings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    key TEXT NOT NULL UNIQUE,
    value TEXT,
    updated_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS sheet_rows (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_row_no INTEGER,
    no TEXT,
    username TEXT,
    no_wa TEXT,
    catatan TEXT,
    oke BOOLEAN,
    invite BOOLEAN,
    deal BOOLEAN,
    req_sampel BOOLEAN,
    kirim BOOLEAN,
    vt1 BOOLEAN,
    vt2 BOOLEAN,
    vt3 BOOLEAN,
    vt4 BOOLEAN,
    vt5 BOOLEAN,
    vt_winn BOOLEAN,
    imported_at TEXT DEFAULT (datetime('now'))
);

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
);

CREATE TABLE IF NOT EXISTS creator_list_entries (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    entry_date TEXT NOT NULL,
    username TEXT NOT NULL,
    username_normalized TEXT NOT NULL,
    creator_name TEXT,
    phone TEXT,
    notes TEXT,
    affiliator_id INTEGER NOT NULL,
    created_at TEXT DEFAULT (datetime('now')),
    UNIQUE(username_normalized),
    FOREIGN KEY (affiliator_id) REFERENCES affiliators(id)
);

CREATE TABLE IF NOT EXISTS creator_tracker_statuses (
    affiliator_id INTEGER PRIMARY KEY,
    oke BOOLEAN NOT NULL DEFAULT 0,
    invite BOOLEAN NOT NULL DEFAULT 0,
    deal BOOLEAN NOT NULL DEFAULT 0,
    req_sampel BOOLEAN NOT NULL DEFAULT 0,
    kirim BOOLEAN NOT NULL DEFAULT 0,
    vt1 BOOLEAN NOT NULL DEFAULT 0,
    vt2 BOOLEAN NOT NULL DEFAULT 0,
    vt3 BOOLEAN NOT NULL DEFAULT 0,
    vt4 BOOLEAN NOT NULL DEFAULT 0,
    vt5 BOOLEAN NOT NULL DEFAULT 0,
    vt_winn BOOLEAN NOT NULL DEFAULT 0,
    updated_at TEXT DEFAULT (datetime('now')),
    FOREIGN KEY (affiliator_id) REFERENCES affiliators(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS creator_submission_links (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    affiliator_id INTEGER NOT NULL,
    token TEXT NOT NULL UNIQUE,
    active BOOLEAN NOT NULL DEFAULT 1,
    expires_at TEXT,
    created_at TEXT DEFAULT (datetime('now')),
    last_used_at TEXT,
    FOREIGN KEY (affiliator_id) REFERENCES affiliators(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS creator_vt_submissions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    affiliator_id INTEGER NOT NULL,
    submission_link_id INTEGER NOT NULL,
    vt_url TEXT NOT NULL,
    vt_url_normalized TEXT NOT NULL UNIQUE,
    spark_code TEXT,
    status TEXT NOT NULL DEFAULT 'pending'
        CHECK (status IN ('pending', 'approved', 'rejected')),
    submitted_at TEXT DEFAULT (datetime('now')),
    reviewed_at TEXT,
    review_notes TEXT,
    approved_vt_id INTEGER,
    FOREIGN KEY (affiliator_id) REFERENCES affiliators(id) ON DELETE CASCADE,
    FOREIGN KEY (submission_link_id) REFERENCES creator_submission_links(id),
    FOREIGN KEY (approved_vt_id) REFERENCES vts(id)
);

CREATE TABLE IF NOT EXISTS video_import_batches (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_filename TEXT NOT NULL,
    source_sha256 TEXT NOT NULL UNIQUE,
    report_period_start TEXT NOT NULL,
    report_period_end TEXT NOT NULL,
    source_timezone TEXT NOT NULL DEFAULT 'Asia/Jakarta',
    row_count INTEGER NOT NULL,
    status TEXT NOT NULL DEFAULT 'running'
        CHECK (status IN ('running', 'completed', 'failed')),
    summary_json TEXT,
    error_message TEXT,
    imported_at TEXT NOT NULL DEFAULT (datetime('now')),
    completed_at TEXT
);

CREATE TABLE IF NOT EXISTS products (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    platform TEXT NOT NULL,
    platform_product_id TEXT NOT NULL,
    name TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(platform, platform_product_id)
);

CREATE TABLE IF NOT EXISTS video_products (
    video_id INTEGER NOT NULL,
    product_id INTEGER NOT NULL,
    first_seen_batch_id INTEGER,
    last_seen_batch_id INTEGER,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    PRIMARY KEY (video_id, product_id),
    FOREIGN KEY (video_id) REFERENCES vts(id) ON DELETE CASCADE,
    FOREIGN KEY (product_id) REFERENCES products(id) ON DELETE CASCADE,
    FOREIGN KEY (first_seen_batch_id) REFERENCES video_import_batches(id)
        ON DELETE SET NULL,
    FOREIGN KEY (last_seen_batch_id) REFERENCES video_import_batches(id)
        ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS video_metric_snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    video_id INTEGER NOT NULL,
    import_batch_id INTEGER NOT NULL,
    source_row_no INTEGER NOT NULL,
    product_ids_json TEXT NOT NULL,
    gmv_idr INTEGER NOT NULL,
    orders INTEGER NOT NULL,
    aov_idr INTEGER NOT NULL,
    units_sold INTEGER NOT NULL,
    refund_idr INTEGER NOT NULL,
    units_refunded INTEGER NOT NULL,
    likes INTEGER NOT NULL,
    comments INTEGER NOT NULL,
    shares INTEGER NOT NULL,
    product_impressions INTEGER NOT NULL,
    product_clicks INTEGER NOT NULL,
    completion_rate_bps INTEGER NOT NULL,
    views INTEGER NOT NULL,
    ctr_bps INTEGER NOT NULL,
    gpm_idr INTEGER NOT NULL,
    interaction_rate_bps INTEGER NOT NULL,
    average_gmv_per_buyer_idr INTEGER NOT NULL,
    estimated_commission_idr INTEGER NOT NULL,
    source_raw_json TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(import_batch_id, video_id),
    FOREIGN KEY (video_id) REFERENCES vts(id) ON DELETE CASCADE,
    FOREIGN KEY (import_batch_id) REFERENCES video_import_batches(id)
        ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS video_import_errors (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    import_batch_id INTEGER,
    source_row_no INTEGER,
    error_code TEXT NOT NULL,
    error_message TEXT NOT NULL,
    source_raw_json TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (import_batch_id) REFERENCES video_import_batches(id)
        ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_affiliators_contact_status ON affiliators(contact_status);
CREATE INDEX IF NOT EXISTS idx_affiliator_handles_affiliator_id ON affiliator_handles(affiliator_id);
CREATE INDEX IF NOT EXISTS idx_affiliator_handles_normalized_handle
    ON affiliator_handles(platform, LOWER(TRIM(handle)));
CREATE INDEX IF NOT EXISTS idx_vts_affiliator_id ON vts(affiliator_id);
CREATE INDEX IF NOT EXISTS idx_vts_platform ON vts(platform);
CREATE INDEX IF NOT EXISTS idx_activity_logs_affiliator_id ON activity_logs(affiliator_id);
CREATE INDEX IF NOT EXISTS idx_sheet_rows_username ON sheet_rows(username);
CREATE INDEX IF NOT EXISTS idx_all_creator_rows_handle ON all_creator_rows(handle);
CREATE INDEX IF NOT EXISTS idx_creator_list_entries_date
    ON creator_list_entries(entry_date);
CREATE UNIQUE INDEX IF NOT EXISTS idx_creator_list_entries_unique_username
    ON creator_list_entries(username_normalized);
CREATE INDEX IF NOT EXISTS idx_creator_list_entries_affiliator
    ON creator_list_entries(affiliator_id);
CREATE INDEX IF NOT EXISTS idx_creator_tracker_updated
    ON creator_tracker_statuses(updated_at);
CREATE UNIQUE INDEX IF NOT EXISTS idx_creator_submission_links_active
    ON creator_submission_links(affiliator_id) WHERE active = 1;
CREATE INDEX IF NOT EXISTS idx_creator_submission_links_token
    ON creator_submission_links(token);
CREATE INDEX IF NOT EXISTS idx_creator_vt_submissions_affiliator
    ON creator_vt_submissions(affiliator_id, submitted_at DESC);
CREATE INDEX IF NOT EXISTS idx_creator_vt_submissions_status
    ON creator_vt_submissions(status);
CREATE UNIQUE INDEX IF NOT EXISTS idx_creator_product_statuses_unique
    ON creator_product_statuses(affiliator_id, LOWER(TRIM(product)))
    WHERE product IS NOT NULL AND TRIM(product) <> '';
CREATE INDEX IF NOT EXISTS idx_video_import_batches_period
    ON video_import_batches(report_period_start, report_period_end);
CREATE INDEX IF NOT EXISTS idx_video_products_product
    ON video_products(product_id, video_id);
CREATE INDEX IF NOT EXISTS idx_video_metric_snapshots_video
    ON video_metric_snapshots(video_id, import_batch_id);
CREATE INDEX IF NOT EXISTS idx_video_metric_snapshots_batch
    ON video_metric_snapshots(import_batch_id, source_row_no);
CREATE INDEX IF NOT EXISTS idx_video_import_errors_batch
    ON video_import_errors(import_batch_id, source_row_no);
