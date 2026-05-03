# 🔐 AuthService — Production-Grade FastAPI Authentication Microservice

A complete, production-ready authentication microservice built with FastAPI, PostgreSQL, Redis, and Docker. Implements email/password and Google OAuth 2.0 login with JWT (RSA asymmetric), refresh token rotation, RBAC, scope-based authorization, rate limiting, and structured logging.

---

## 📐 Architecture

```
auth-service/
├── app/
│   ├── main.py                      # App factory, middleware, lifespan hooks
│   ├── api/
│   │   ├── dependencies.py          # FastAPI injectable deps (auth, RBAC, scopes)
│   │   ├── middleware/
│   │   │   ├── exception_handler.py # Global error → JSON response mapping
│   │   │   ├── rate_limiter.py      # Redis sliding-window rate limiter
│   │   │   └── logging.py           # Structured request/response logging
│   │   └── v1/
│   │       ├── router.py            # Aggregates all v1 routers
│   │       └── endpoints/
│   │           ├── auth.py          # /auth/* endpoints
│   │           └── users.py         # /users/* endpoints
│   ├── core/
│   │   ├── config.py                # Pydantic settings from env vars
│   │   ├── database.py              # Async SQLAlchemy engine + session dep
│   │   ├── exceptions.py            # Domain exception hierarchy
│   │   ├── logging.py               # Structlog configuration
│   │   ├── redis.py                 # Async Redis client + key builders
│   │   └── security.py             # JWT (RSA) + Argon2 password hashing
│   ├── models/
│   │   ├── user.py                  # User ORM model (UUID PK, RBAC, OAuth)
│   │   └── refresh_token.py         # RefreshToken ORM model (multi-device)
│   ├── repositories/
│   │   ├── user_repository.py       # User CRUD + account lock logic
│   │   └── token_repository.py      # Refresh token lifecycle + rotation
│   ├── schemas/
│   │   └── auth.py                  # Pydantic request/response schemas
│   ├── services/
│   │   ├── auth_service.py          # Business logic: signup, login, refresh, logout
│   │   └── google_oauth_service.py  # Google ID token verification
│   └── utils/
│       ├── email.py                 # Email validation helpers
│       └── pagination.py            # Generic paginated response
├── alembic/                         # Database migrations
│   ├── env.py                       # Async-aware Alembic environment
│   ├── script.py.mako               # Migration template
│   └── versions/
│       └── 0001_initial_schema.py   # Initial users + refresh_tokens tables
├── tests/
│   ├── conftest.py                  # Shared fixtures (in-memory SQLite, mocked Redis)
│   ├── unit/
│   │   ├── test_security.py         # JWT + password hashing tests
│   │   ├── test_repositories.py     # Repository layer tests
│   │   └── test_auth_service.py     # Service layer tests (mocked deps)
│   └── integration/
│       └── test_auth_endpoints.py   # Full HTTP endpoint tests
├── scripts/
│   ├── generate_keys.sh             # RSA-4096 key pair generation
│   └── init_db.sql                  # PostgreSQL extensions bootstrap
├── Dockerfile                       # Multi-stage production image
├── docker-compose.yml               # App + PostgreSQL + Redis
├── alembic.ini                      # Alembic configuration
├── requirements.txt
├── pytest.ini
├── Makefile                         # Developer convenience commands
└── .env.example                     # Environment variable template
```

---

## 🚀 Quick Start

### Prerequisites
- Docker & Docker Compose
- `openssl` (for key generation)
- `make` (optional but recommended)

### 1. Clone & configure environment

```bash
git clone <repo-url>
cd auth-service

# Copy env template
make env
# OR: cp .env.example .env
# Then edit .env with your values (especially GOOGLE_CLIENT_ID for OAuth)
```

### 2. Generate RSA key pair (required for JWT)

```bash
make keys
# OR: bash scripts/generate_keys.sh
```

This creates `./keys/private.pem` and `./keys/public.pem`.

### 3. Start all services

```bash
make up
# OR: docker compose up --build -d
```

This starts:
- **FastAPI app** on `http://localhost:8000`
- **PostgreSQL** on `localhost:5432`
- **Redis** on `localhost:6379`

Alembic migrations run automatically on startup.

### 4. Verify it's running

```bash
curl http://localhost:8000/health
# {"status": "ok", "service": "AuthService"}

# Interactive API docs (development only)
open http://localhost:8000/docs
```

---

## 📡 API Endpoints

### Authentication

| Method | Path | Description | Auth Required |
|--------|------|-------------|---------------|
| `POST` | `/v1/auth/signup` | Register with email + password | No |
| `POST` | `/v1/auth/login` | Login with email + password | No |
| `POST` | `/v1/auth/google` | Login / register via Google OAuth | No |
| `POST` | `/v1/auth/refresh` | Rotate refresh token | No (uses refresh token) |
| `POST` | `/v1/auth/logout` | Revoke current session | No (uses refresh token) |
| `POST` | `/v1/auth/logout-all` | Revoke all sessions | Yes (Bearer) |

### Users

| Method | Path | Description | Auth Required |
|--------|------|-------------|---------------|
| `GET` | `/v1/users/me` | Get own profile | Yes (Bearer) |
| `GET` | `/v1/users/{id}` | Get user by ID | Yes (Bearer, admin role) |

---

## 🔑 Auth Flow Examples

### Signup
```bash
curl -X POST http://localhost:8000/v1/auth/signup \
  -H "Content-Type: application/json" \
  -d '{"email": "user@example.com", "password": "MyPass1!"}'
```

### Login
```bash
curl -X POST http://localhost:8000/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email": "user@example.com", "password": "MyPass1!"}'

# Response:
# {
#   "access_token": "<jwt>",
#   "refresh_token": "<jwt>",
#   "token_type": "Bearer",
#   "expires_in": 1800
# }
```

### Access Protected Route
```bash
curl http://localhost:8000/v1/users/me \
  -H "Authorization: Bearer <access_token>"
```

### Refresh Tokens
```bash
curl -X POST http://localhost:8000/v1/auth/refresh \
  -H "Content-Type: application/json" \
  -d '{"refresh_token": "<refresh_token>"}'
```

### Google OAuth
```bash
# 1. Get an ID token from Google on the client side (e.g., Google Sign-In button)
# 2. Send the ID token to this endpoint:
curl -X POST http://localhost:8000/v1/auth/google \
  -H "Content-Type: application/json" \
  -d '{"id_token": "<google_id_token>"}'
```

---

## 🔐 Security Design

### JWT Strategy
- **Algorithm**: RS256 (asymmetric RSA-4096)
- **Access token TTL**: 30 minutes
- **Refresh token TTL**: 24 hours (stored in PostgreSQL, hashed with SHA-256)
- **Rotation**: On every refresh, the old token is immediately invalidated and a new pair is issued
- **Reuse detection**: If a revoked refresh token is presented, ALL sessions for that user are immediately invalidated

### Password Security
- Hashed with **Argon2id** (memory-hard; bcrypt fallback for migration support)
- Password strength enforced at the schema layer (uppercase, lowercase, digit, special char, 8–128 chars)
- Timing-safe comparison against non-existent users (prevents user enumeration)

### Account Protection
- Failed login attempts tracked per user in the DB
- Account locked for 30 minutes after 5 consecutive failures (configurable)
- Lock status checked before password verification

### Rate Limiting
- **Default**: 60 requests/minute per IP
- **Sensitive endpoints** (login, signup, google): 5–10 requests/minute
- Implemented as a sliding-window counter in Redis
- Graceful degradation: if Redis is unavailable, requests are allowed through (logged)
- Rate limit headers returned on every response (`X-RateLimit-*`)

### RBAC & Scopes
```python
# Role guard
@router.get("/admin-only", dependencies=[Depends(require_role("admin"))])

# Scope guard
@router.delete("/resource", dependencies=[Depends(require_scopes("delete:resource"))])

# Combined
@router.patch("/resource",
    dependencies=[
        Depends(require_role("admin")),
        Depends(require_scopes("write:all")),
    ]
)
```

---

## 🧪 Running Tests

```bash
# All tests
make test

# Unit tests only (no I/O, fast)
make test-unit

# Integration tests (HTTP + in-memory SQLite)
make test-integration

# With coverage report
make test-cov
```

Tests use:
- **SQLite in-memory** — no real PostgreSQL needed
- **Mocked Redis** — no real Redis needed
- **httpx AsyncClient** — full ASGI request/response cycle

---

## ⚙️ Configuration Reference

| Variable | Default | Description |
|----------|---------|-------------|
| `APP_ENV` | `development` | `development` / `staging` / `production` |
| `DATABASE_URL` | — | PostgreSQL async DSN |
| `REDIS_HOST` | `localhost` | Redis hostname |
| `JWT_PRIVATE_KEY_PATH` | `./keys/private.pem` | Path to RSA private key |
| `JWT_PUBLIC_KEY_PATH` | `./keys/public.pem` | Path to RSA public key |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | `30` | Access token TTL |
| `REFRESH_TOKEN_EXPIRE_HOURS` | `24` | Refresh token TTL |
| `GOOGLE_CLIENT_ID` | — | Google OAuth Client ID |
| `MAX_LOGIN_ATTEMPTS` | `5` | Before account lock |
| `ACCOUNT_LOCK_MINUTES` | `30` | Lock duration |
| `RATE_LIMIT_PER_MINUTE` | `60` | Default rate limit per IP |
| `ALLOWED_ORIGINS` | `http://localhost:3000` | CORS allowed origins (comma-separated) |

In **production** (`APP_ENV=production`):
- `/docs`, `/redoc`, `/openapi.json` are disabled
- Log output is structured JSON

---

## 🗄️ Database Migrations

```bash
# Apply all pending migrations
make migrate

# Create a new migration after changing ORM models
make migrate-new MSG="add_phone_number_to_users"

# Rollback last migration
make migrate-down

# View history
make migrate-history
```

---

## 🔧 Developer Commands

```bash
make help          # Show all available targets
make keys          # Generate RSA key pair
make up            # Start Docker services
make down          # Stop Docker services
make logs          # Tail app logs
make shell         # Shell into app container
make migrate       # Run migrations
make test          # Run test suite
make lint          # Lint with ruff
make fmt           # Format with ruff + black
make typecheck     # mypy type checking
```

---

## 🚢 Production Checklist

- [ ] Set `APP_ENV=production`
- [ ] Use strong, unique `POSTGRES_PASSWORD`
- [ ] Set `REDIS_PASSWORD`
- [ ] Mount RSA keys from a secrets manager (not from disk)
- [ ] Set `ALLOWED_ORIGINS` to your actual frontend domain(s)
- [ ] Set `GOOGLE_CLIENT_ID` if using Google OAuth
- [ ] Enable TLS termination at the reverse proxy (nginx/Caddy/ALB)
- [ ] Configure log aggregation (Datadog, Loki, CloudWatch)
- [ ] Set up DB connection pooling (PgBouncer) for high traffic
- [ ] Add monitoring / alerting on the `/health` endpoint
- [ ] Rotate RSA keys periodically and support key versioning (`kid` in JWT header)
- [ ] Consider adding email verification flow (send token, confirm endpoint)
