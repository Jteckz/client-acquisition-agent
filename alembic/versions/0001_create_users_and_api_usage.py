"""Create users and api_usage tables.

Revision ID: 0001
Revises:
Create Date: 2026-09-21 00:00:00.000000
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

# revision identifiers, used by Alembic.
revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create the users table with UUID primary key and api_key."""
    op.create_table(
        "users",
        sa.Column(
            "id",
            UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("email", sa.Text(), nullable=False, unique=True),
        sa.Column("hashed_password", sa.Text(), nullable=False),
        sa.Column(
            "api_key",
            sa.Text(),
            nullable=False,
            unique=True,
        ),
        sa.Column(
            "plan", sa.Text(), nullable=False, server_default="free"
        ),
        sa.Column(
            "is_active",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("true"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )

    """Create the api_usage table for per-request token tracking."""
    op.create_table(
        "api_usage",
        sa.Column(
            "id", sa.BigInteger(), primary_key=True, autoincrement=True
        ),
        sa.Column(
            "user_id",
            UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("endpoint", sa.Text(), nullable=False),
        sa.Column(
            "tokens_used", sa.Integer(), nullable=False, server_default="0"
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )

    op.create_index("ix_api_usage_user_id", "api_usage", ["user_id"])
    op.create_index("ix_api_usage_created_at", "api_usage", ["created_at"])


def downgrade() -> None:
    """Drop the api_usage and users tables."""
    op.drop_table("api_usage")
    op.drop_table("users")
