-- ============================================================
-- RepoInsight Auth Service — D1 Schema
-- Compatible with Cloudflare D1 (SQLite dialect)
-- ============================================================

PRAGMA journal_mode = WAL;
PRAGMA foreign_keys = ON;

-- ─────────────────────────────────────────
-- TENANTS
-- ─────────────────────────────────────────
CREATE TABLE IF NOT EXISTS tenants (
    id          TEXT PRIMARY KEY,                     -- UUID v4
    name        TEXT NOT NULL,
    slug        TEXT NOT NULL UNIQUE,                 -- URL-safe identifier
    is_active   INTEGER NOT NULL DEFAULT 1,           -- 0 = suspended
    created_at  TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    updated_at  TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
);

CREATE INDEX IF NOT EXISTS idx_tenants_slug ON tenants(slug);

-- ─────────────────────────────────────────
-- PLANS
-- ─────────────────────────────────────────
CREATE TABLE IF NOT EXISTS plans (
    id           TEXT PRIMARY KEY,                    -- UUID v4
    name         TEXT NOT NULL UNIQUE,                -- tier_1 | tier_2 | tier_3
    display_name TEXT NOT NULL,
    permissions  TEXT NOT NULL,                       -- JSON array e.g. '["read_repo","ask_ai"]'
    max_repos    INTEGER NOT NULL DEFAULT 1,
    max_members  INTEGER NOT NULL DEFAULT 1,
    is_active    INTEGER NOT NULL DEFAULT 1,
    created_at   TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
);

INSERT OR IGNORE INTO plans (id, name, display_name, permissions, max_repos, max_members)
VALUES
    ('plan_tier1', 'tier_1', 'Starter',      '["read_repo"]',                          1,  1),
    ('plan_tier2', 'tier_2', 'Professional', '["read_repo","ask_ai"]',                 5,  5),
    ('plan_tier3', 'tier_3', 'Enterprise',   '["read_repo","ask_ai","multi_repo"]',   999, 999);

-- ─────────────────────────────────────────
-- USERS
-- ─────────────────────────────────────────
CREATE TABLE IF NOT EXISTS users (
    id                TEXT PRIMARY KEY,               -- UUID v4
    tenant_id         TEXT NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    email             TEXT NOT NULL,
    name              TEXT NOT NULL DEFAULT '',
    password_hash     TEXT,                           -- NULL for Google SSO-only users
    avatar_url        TEXT,
    role              TEXT NOT NULL DEFAULT 'user',   -- user | admin
    auth_provider     TEXT NOT NULL DEFAULT 'email',  -- email | google
    google_id         TEXT,                           -- Google sub claim
    is_email_verified INTEGER NOT NULL DEFAULT 0,
    is_active         INTEGER NOT NULL DEFAULT 1,
    token_version     INTEGER NOT NULL DEFAULT 1,     -- increment to force logout
    razorpay_customer_id TEXT,
    created_at        TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    updated_at        TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    deleted_at        TEXT                            -- soft delete
);

-- One email per tenant (allow same email across different tenants)
CREATE UNIQUE INDEX IF NOT EXISTS idx_users_email_tenant ON users(email, tenant_id) WHERE deleted_at IS NULL;
CREATE UNIQUE INDEX IF NOT EXISTS idx_users_google_id    ON users(google_id) WHERE google_id IS NOT NULL;
CREATE INDEX        IF NOT EXISTS idx_users_tenant_id    ON users(tenant_id);
CREATE INDEX        IF NOT EXISTS idx_users_email        ON users(email);

-- ─────────────────────────────────────────
-- SUBSCRIPTIONS
-- ─────────────────────────────────────────
CREATE TABLE IF NOT EXISTS subscriptions (
    id                  TEXT PRIMARY KEY,             -- UUID v4
    tenant_id           TEXT NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    plan_id             TEXT NOT NULL REFERENCES plans(id),
    status              TEXT NOT NULL DEFAULT 'active', -- active | cancelled | past_due | trialing
    razorpay_sub_id     TEXT,
    current_period_start TEXT,
    current_period_end   TEXT,
    created_at          TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    updated_at          TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
);

CREATE INDEX IF NOT EXISTS idx_subscriptions_tenant_id ON subscriptions(tenant_id);

-- ─────────────────────────────────────────
-- TEAMS
-- ─────────────────────────────────────────
CREATE TABLE IF NOT EXISTS teams (
    id          TEXT PRIMARY KEY,                     -- UUID v4
    tenant_id   TEXT NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    name        TEXT NOT NULL,
    description TEXT,
    created_by  TEXT NOT NULL REFERENCES users(id),
    is_active   INTEGER NOT NULL DEFAULT 1,
    created_at  TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    updated_at  TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
);

CREATE INDEX IF NOT EXISTS idx_teams_tenant_id ON teams(tenant_id);

-- ─────────────────────────────────────────
-- USER_TEAMS  (many-to-many)
-- ─────────────────────────────────────────
CREATE TABLE IF NOT EXISTS user_teams (
    id         TEXT PRIMARY KEY,                      -- UUID v4
    user_id    TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    team_id    TEXT NOT NULL REFERENCES teams(id) ON DELETE CASCADE,
    role       TEXT NOT NULL DEFAULT 'member',        -- member | lead
    joined_at  TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_user_teams_unique ON user_teams(user_id, team_id);
CREATE INDEX        IF NOT EXISTS idx_user_teams_team   ON user_teams(team_id);

-- ─────────────────────────────────────────
-- REFRESH TOKENS
-- ─────────────────────────────────────────
CREATE TABLE IF NOT EXISTS refresh_tokens (
    id            TEXT PRIMARY KEY,                   -- UUID v4 (also the jti)
    user_id       TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    token_hash    TEXT NOT NULL UNIQUE,               -- SHA-256 of the raw token
    token_version INTEGER NOT NULL,                   -- snapshot of user.token_version
    expires_at    TEXT NOT NULL,
    revoked       INTEGER NOT NULL DEFAULT 0,
    revoked_at    TEXT,
    ip_address    TEXT,
    user_agent    TEXT,
    created_at    TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
);

CREATE INDEX IF NOT EXISTS idx_refresh_tokens_user_id    ON refresh_tokens(user_id);
CREATE INDEX IF NOT EXISTS idx_refresh_tokens_token_hash ON refresh_tokens(token_hash);
CREATE INDEX IF NOT EXISTS idx_refresh_tokens_expires    ON refresh_tokens(expires_at);

-- ─────────────────────────────────────────
-- EMAIL VERIFICATIONS
-- ─────────────────────────────────────────
CREATE TABLE IF NOT EXISTS email_verifications (
    id         TEXT PRIMARY KEY,                      -- UUID v4
    user_id    TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    token_hash TEXT NOT NULL UNIQUE,                  -- SHA-256 of raw token
    expires_at TEXT NOT NULL,
    used       INTEGER NOT NULL DEFAULT 0,
    used_at    TEXT,
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
);

CREATE INDEX IF NOT EXISTS idx_email_verif_user_id    ON email_verifications(user_id);
CREATE INDEX IF NOT EXISTS idx_email_verif_token_hash ON email_verifications(token_hash);
