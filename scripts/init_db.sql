-- scripts/init_db.sql
-- Executed by PostgreSQL on first container startup.
-- Creates the pgcrypto extension needed for gen_random_uuid().

CREATE EXTENSION IF NOT EXISTS "pgcrypto";
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
