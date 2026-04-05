ALTER TABLE tenants ADD COLUMN email_suffix TEXT;

CREATE INDEX IF NOT EXISTS idx_tenants_email_suffix ON tenants(email_suffix);

ALTER TABLE users ADD COLUMN workspace_access_status TEXT NOT NULL DEFAULT 'pending';
ALTER TABLE users ADD COLUMN approved_by TEXT REFERENCES users(id);
ALTER TABLE users ADD COLUMN approved_at TEXT;

UPDATE users
SET workspace_access_status = 'approved',
    approved_at = COALESCE(approved_at, updated_at)
WHERE deleted_at IS NULL;

DROP INDEX IF EXISTS idx_users_email_tenant;
CREATE UNIQUE INDEX IF NOT EXISTS idx_users_email_global ON users(email) WHERE deleted_at IS NULL;
CREATE INDEX IF NOT EXISTS idx_users_workspace_access_status ON users(workspace_access_status);
