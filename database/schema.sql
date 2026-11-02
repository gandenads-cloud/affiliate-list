PRAGMA journal_mode = WAL;
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    email TEXT UNIQUE,
    created_at TEXT DEFAULT (datetime('now'))
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
    live_at TEXT NOT NULL,
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
