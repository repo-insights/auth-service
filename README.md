# RepoInsight — Auth Service

Production-ready authentication and user management service for RepoInsight.

---

## Features

- **Google SSO** (OAuth2 PKCE flow)
- **Email / Password** signup with email verification
- **JWT access tokens** (60 min) with strict payload structure
- **Refresh tokens** (12 h) — httpOnly cookie + D1 persistence
- **Token rotation** — old refresh token revoked on every use
- **Forced logout** via `token_version` increment
- **S2S tokens** for service-to-service auth
- **Multi-tenant** schema — full tenant isolation enforced in every query
- **Team structure** — many-to-many user ↔ team mapping
- **Plan tiers** — `tier_1 / tier_2 / tier_3` with dynamic permissions in JWT
- **Rate limiting** — D1-backed per-IP counters on login / signup
- **Soft deletes** — users are never hard-deleted

---

## Tech Stack

| Layer | Technology |
|---|---|
| Framework | FastAPI + Pydantic v2 |
| Primary DB | libSQL / Turso today, D1-binding ready |
| Auth State | D1-backed blacklist, refresh-token, and rate-limit state |
| Auth | python-jose (JWT) · passlib/bcrypt |
| HTTP client | httpx (Google OAuth) |
| Email | SMTP (SendGrid-compatible) |

---

## Project Structure

```
repoinsight-auth/
├── app/
│   ├── api/
│   │   └── v1/
│   │       ├── endpoints/
│   │       │   ├── auth.py          # /auth/* — login, signup, OAuth, tokens
│   │       │   ├── users.py         # /users/* — user CRUD + profile
│   │       │   ├── tenants.py       # /tenants/me, /teams/*
│   │       │   └── plans.py         # /plans/*, /plans/subscription
│   │       └── router.py
│   ├── core/
│   │   ├── config.py                # Pydantic Settings — env-driven
│   │   ├── dependencies.py          # FastAPI DI: current_user, rate_limit, tenant guard
│   │   └── security.py             # JWT, bcrypt, token helpers
│   ├── db/
│   │   └── database.py             # DB abstraction for libsql or Cloudflare D1 binding
│   ├── middleware/
│   │   ├── worker_bindings.py      # Request-scoped Cloudflare D1 binding adapter
│   │   ├── logging.py              # Structured request logging
│   │   └── exceptions.py           # Global error handler
│   ├── schemas/
│   │   └── schemas.py              # All Pydantic request/response models
│   ├── services/
│   │   ├── auth_service.py         # Core auth orchestration
│   │   ├── auth_state_service.py   # D1-backed auth blacklist + rate limit state
│   │   ├── user_service.py         # User CRUD
│   │   ├── tenant_service.py       # Tenant + subscription CRUD
│   │   ├── token_service.py        # Refresh + email-verification token lifecycle
│   │   ├── email_service.py        # SMTP sender
│   │   └── google_oauth_service.py # Google token exchange + userinfo
│   └── main.py                     # App factory + lifespan
├── migrations/
│   ├── 001_initial_schema.sql      # Base D1-compatible SQLite schema
│   └── 002_auth_runtime_state.sql  # D1-backed blacklist + rate-limit tables
├── scripts/
│   ├── migrate.py                  # Local/libsql migration runner
│   └── migrate_d1.sh               # Cloudflare D1 migration wrapper
├── tests/
│   ├── conftest.py
│   ├── unit/
│   │   ├── test_security.py
│   │   └── test_schemas.py
│   └── integration/               # Add httpx TestClient tests here
├── Dockerfile
├── docker-compose.yml
├── requirements.txt
├── worker.py
├── wrangler.toml
└── .env.example
```

---

## Quick Start

```bash
# 1. Clone and configure
cp .env.example .env
# Fill in your values in .env
# If local SSL verification fails, prefer a CA bundle:
# TURSO_DATABASE_TLS=true
# TURSO_SSL_CERT_FILE=/absolute/path/to/ca.pem
#
# Temporary local-only workaround:
# TURSO_DATABASE_TLS=false

# 2. Run migrations
python3 scripts/migrate.py

# 3. Start the service
uvicorn app.main:app --reload

# Docs available at http://localhost:8000/docs (development only)
```

For local/server deployments, keep `DB_BACKEND=libsql`.
For a Cloudflare Workers migration, switch to `DB_BACKEND=d1_binding` and provide the Worker binding named by `D1_BINDING_NAME`.

## Local Testing

Use this flow before deploying anything to Cloudflare:

```bash
# 1. Create and activate a virtualenv if needed
python3 -m venv .venv
source .venv/bin/activate

# 2. Install dependencies
pip install -r requirements.txt

# 3. Configure .env
# DB_BACKEND=libsql
# TURSO_DATABASE_URL=libsql://<your-turso-or-libsql-endpoint>
# TURSO_AUTH_TOKEN=<your-token>

# 4. Apply migrations
python3 scripts/migrate.py

# 5. Start the API
uvicorn app.main:app --reload
```

Then verify these locally:

1. `GET /health`
2. `POST /api/v1/auth/signup`
3. `POST /api/v1/auth/login/{tenant_slug}`
4. `POST /api/v1/auth/refresh`
5. `POST /api/v1/auth/logout`
6. `POST /api/v1/auth/logout-all`
7. Repeat login until rate limiting triggers

## Cloudflare Prep

The repo now includes:

- `worker.py` as the Workers entrypoint
- `wrangler.toml` as the base Wrangler config
- `scripts/migrate_d1.sh` for D1 migrations via Wrangler

Before Cloudflare deployment, replace `database_id` in `wrangler.toml` and confirm the D1 binding name matches `D1_BINDING_NAME`.

---

## Vercel Deployment

This FastAPI app can also run on Vercel using the Python runtime.

Files included for Vercel:

- `api/index.py` as the Vercel entrypoint
- `vercel.json` to route all requests to the FastAPI app

Recommended setup:

1. Push this repo to GitHub.
2. Import the repo into Vercel.
3. Set the framework preset to `Other`.
4. Keep the root directory as the repo root.
5. Add the same environment variables you use locally.

Important environment variables for Vercel:

- `DB_BACKEND=libsql`
- `TURSO_DATABASE_URL=libsql://...`
- `TURSO_AUTH_TOKEN=...`
- `JWT_SECRET_KEY=...`
- `SECRET_KEY=...`
- `S2S_SECRET_KEY=...`
- `GOOGLE_CLIENT_ID=...`
- `GOOGLE_CLIENT_SECRET=...`
- `GOOGLE_REDIRECT_URI=https://<your-vercel-domain>/api/v1/auth/google/callback`
- `FRONTEND_URL=https://<your-frontend-domain>`

Notes:

- Vercel is serverless, so database initialization is also done lazily on first use.
- Keep docs disabled in production by leaving `DEBUG=false`.
- If you use cookies for refresh tokens across domains, make sure your frontend and API domains/cookie settings match your production flow.

---

## API Reference

### Auth

| Method | Path | Description |
|---|---|---|
| `POST` | `/api/v1/auth/signup` | Create account + tenant |
| `POST` | `/api/v1/auth/verify-email` | Verify email with token |
| `POST` | `/api/v1/auth/resend-verification` | Resend verification email |
| `POST` | `/api/v1/auth/login/{tenant_slug}` | Email/password login |
| `GET`  | `/api/v1/auth/google` | Redirect to Google OAuth |
| `GET`  | `/api/v1/auth/google/callback` | Google OAuth callback |
| `POST` | `/api/v1/auth/refresh` | Rotate refresh token |
| `POST` | `/api/v1/auth/logout` | Revoke current session |
| `POST` | `/api/v1/auth/logout-all` | Revoke all sessions (bump token_version) |
| `POST` | `/api/v1/auth/s2s/token` | Issue S2S JWT |

### Users

| Method | Path | Description |
|---|---|---|
| `GET`    | `/api/v1/users/me` | Get current user |
| `PATCH`  | `/api/v1/users/me` | Update profile |
| `DELETE` | `/api/v1/users/me` | Soft-delete account |
| `GET`    | `/api/v1/users/{id}` | Get user by ID *(admin)* |
| `GET`    | `/api/v1/users/` | List tenant users *(admin)* |
| `DELETE` | `/api/v1/users/{id}` | Soft-delete user *(admin)* |

### Tenants & Teams

| Method | Path | Description |
|---|---|---|
| `GET`    | `/api/v1/tenants/me` | Get current tenant |
| `POST`   | `/api/v1/teams/` | Create team |
| `GET`    | `/api/v1/teams/` | List teams |
| `GET`    | `/api/v1/teams/{id}` | Get team |
| `POST`   | `/api/v1/teams/{id}/members` | Add member *(admin)* |
| `DELETE` | `/api/v1/teams/{id}/members/{user_id}` | Remove member *(admin)* |

### Plans

| Method | Path | Description |
|---|---|---|
| `GET` | `/api/v1/plans/` | List all plans |
| `GET` | `/api/v1/plans/subscription` | Get tenant's active subscription |

---

## JWT Payload

```json
{
  "sub": "user_id",
  "email": "user@email.com",
  "name": "User Name",
  "tenant_id": "tenant_id",
  "team_id": "team_id",
  "role": "user | admin",
  "plan": "tier_1 | tier_2 | tier_3",
  "customer_id": "razorpay_customer_id",
  "permissions": ["read_repo", "ask_ai"],
  "token_version": 1,
  "iat": 1710000000,
  "exp": 1710003600,
  "iss": "repoinsight-auth",
  "aud": "repoinsight-api",
  "jti": "uuid-for-blacklisting"
}
```

---

## Security Design

### Token Version (Forced Logout)
Every JWT carries `token_version`. On every authenticated request, the service checks this against the DB value. Calling `POST /auth/logout-all` increments `token_version` in the DB, instantly invalidating all outstanding JWTs — no token-hunting required.

### Refresh Token Rotation
Each refresh produces a new token and immediately revokes the old one in D1. A replayed old refresh token will be rejected (revoked flag in D1).

### Tenant Isolation
`assert_same_tenant()` is called on every cross-resource access. Users can never see data from a different tenant — enforced at the service layer, not just the query layer.

### Rate Limiting
D1-backed counters per IP: 5 login attempts / minute, 3 signups / minute.

---

## Running Tests

```bash
pip install pytest pytest-asyncio
pytest tests/unit/ -v
```
