from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # App
    app_name: str = "repoinsight-auth"
    app_env: str = "development"
    debug: bool = False
    secret_key: str

    # JWT
    jwt_secret_key: str
    jwt_algorithm: str = "HS256"
    jwt_access_token_expire_minutes: int = 60
    jwt_refresh_token_expire_hours: int = 12
    jwt_issuer: str = "repoinsight-auth"
    jwt_audience: str = "repoinsight-api"

    # S2S
    s2s_secret_key: str
    s2s_token_expire_minutes: int = 10

    # Cloudflare D1 / Turso
    d1_database_url: str = ""
    d1_auth_token: str = ""
    d1_database_tls: bool = True
    d1_ssl_cert_file: str | None = None
    db_backend: str = "libsql"
    d1_binding_name: str = "DB"

    # Google OAuth
    google_client_id: str
    google_client_secret: str
    google_redirect_uri: str

    # Email
    smtp_host: str
    smtp_port: int = 587
    smtp_user: str
    smtp_password: str
    email_from: str
    email_from_name: str = "RepoInsight"

    # Frontend
    frontend_url: str = "http://localhost:3000"

    # Rate limiting
    rate_limit_login: str = "5/minute"
    rate_limit_signup: str = "3/minute"


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
