"""Add GitHub integration and repository sync tables

Revision ID: 0002_github_repository_sync
Revises: 0001_initial_schema
Create Date: 2026-05-03 00:00:00.000000
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0002_github_repository_sync"
down_revision: Union[str, None] = "0001_initial_schema"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "github_connections",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("provider", sa.String(50), nullable=False, server_default="github"),
        sa.Column("github_login", sa.String(255), nullable=True),
        sa.Column("github_user_id", sa.String(255), nullable=True),
        sa.Column("installation_id", sa.String(255), nullable=True),
        sa.Column("access_token", sa.String(255), nullable=True),
        sa.Column("scopes", sa.JSON(), nullable=False),
        sa.Column("connected_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_synced_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("sync_status", sa.String(50), nullable=False, server_default="never_synced"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.UniqueConstraint("user_id", "provider", name="uq_github_connections_user_provider"),
    )
    op.create_index("ix_github_connections_user_id", "github_connections", ["user_id"])

    op.create_table(
        "repositories",
        sa.Column("id", sa.String(255), primary_key=True),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("provider", sa.String(50), nullable=False, server_default="github"),
        sa.Column("provider_repo_id", sa.String(255), nullable=True),
        sa.Column("owner", sa.String(255), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("full_name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("visibility", sa.String(50), nullable=False),
        sa.Column("branch", sa.String(255), nullable=True),
        sa.Column("language", sa.String(255), nullable=True),
        sa.Column("stars", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("forks", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_updated", sa.DateTime(timezone=True), nullable=True),
        sa.Column("sync_status", sa.String(50), nullable=False, server_default="synced"),
        sa.Column("tree_sha", sa.String(255), nullable=True),
        sa.Column("indexed_file_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "default_analysis_status",
            sa.String(50),
            nullable=False,
            server_default="pending",
        ),
        sa.Column("is_deleted", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.UniqueConstraint(
            "user_id",
            "provider",
            "provider_repo_id",
            name="uq_repositories_user_provider_repo",
        ),
    )
    op.create_index("ix_repositories_user_id", "repositories", ["user_id"])

    op.create_table(
        "repository_sync_jobs",
        sa.Column("id", sa.String(255), primary_key=True),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("status", sa.String(50), nullable=False),
        sa.Column("source", sa.String(50), nullable=False),
        sa.Column("total_repositories", sa.Integer(), nullable=True),
        sa.Column("synced_repositories", sa.Integer(), nullable=True),
        sa.Column("failed_repositories", sa.Integer(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
    )
    op.create_index("ix_repository_sync_jobs_user_id", "repository_sync_jobs", ["user_id"])


def downgrade() -> None:
    op.drop_table("repository_sync_jobs")
    op.drop_table("repositories")
    op.drop_table("github_connections")
