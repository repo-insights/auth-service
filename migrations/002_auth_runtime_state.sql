-- ============================================================
-- Auth runtime state for Workers-friendly deployments
-- Removes the hard Redis requirement for blacklist/rate-limit state.
-- ============================================================

CREATE TABLE IF NOT EXISTS access_token_blacklist (
    jti        TEXT PRIMARY KEY,
    expires_at TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
);

CREATE INDEX IF NOT EXISTS idx_access_token_blacklist_expires
    ON access_token_blacklist(expires_at);

CREATE TABLE IF NOT EXISTS rate_limit_counters (
    prefix            TEXT NOT NULL,
    identifier        TEXT NOT NULL,
    count             INTEGER NOT NULL DEFAULT 0,
    window_started_at TEXT NOT NULL,
    updated_at        TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    PRIMARY KEY (prefix, identifier)
);

CREATE INDEX IF NOT EXISTS idx_rate_limit_counters_updated
    ON rate_limit_counters(updated_at);
