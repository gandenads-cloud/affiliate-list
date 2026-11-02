-- Prepare normalized video analytics storage and enforce import-safe uniqueness.

-- Remove duplicate case variants only when they already belong to the same creator.
DELETE FROM affiliator_handles AS duplicate
WHERE EXISTS (
    SELECT 1
    FROM affiliator_handles AS canonical
    WHERE canonical.platform = duplicate.platform
      AND LOWER(TRIM(canonical.handle)) = LOWER(TRIM(duplicate.handle))
      AND canonical.affiliator_id = duplicate.affiliator_id
      AND canonical.id < duplicate.id
);

DROP INDEX IF EXISTS idx_affiliator_handles_normalized_handle;
CREATE UNIQUE INDEX idx_affiliator_handles_normalized_handle
    ON affiliator_handles(platform, LOWER(TRIM(handle)));

CREATE UNIQUE INDEX IF NOT EXISTS idx_creator_product_statuses_unique
    ON creator_product_statuses(affiliator_id, LOWER(TRIM(product)))
    WHERE product IS NOT NULL AND TRIM(product) <> '';

-- Rebuild vts so videos with unavailable source dates can use NULL live_at.
CREATE TABLE vts_new (
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

INSERT INTO vts_new (
    id, affiliator_id, platform, url, title_or_caption, live_at,
    has_boost, boost_code, boost_checked_at, views, likes, comments,
    shares, gmv, commission, metrics_updated_at, counts_to_agreement,
    data_source, notes, created_at, updated_at, agreement_id,
    platform_video_id
)
SELECT id, affiliator_id, platform, url, title_or_caption, live_at,
       has_boost, boost_code, boost_checked_at, views, likes, comments,
       shares, gmv, commission, metrics_updated_at, counts_to_agreement,
       data_source, notes, created_at, updated_at, agreement_id,
       platform_video_id
FROM vts;

DROP TABLE vts;
ALTER TABLE vts_new RENAME TO vts;

CREATE INDEX idx_vts_affiliator_id ON vts(affiliator_id);
CREATE INDEX idx_vts_platform ON vts(platform);

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

PRAGMA user_version = 1;
