"""Add private uploaded file metadata."""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0002_file_assets"
down_revision: Union[str, None] = "0001_initial_schema"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "file_assets",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("original_filename", sa.String(length=255), nullable=False),
        sa.Column("storage_filename", sa.String(length=80), nullable=False),
        sa.Column("media_type", sa.String(length=160), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column("extracted_text", sa.Text(), server_default="", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], ondelete="CASCADE",
            name="fk_file_assets_user_id_users"
        ),
        sa.PrimaryKeyConstraint("id", name="pk_file_assets"),
        sa.UniqueConstraint("storage_filename", name="uq_file_assets_storage_filename"),
    )
    op.create_index("ix_file_assets_user_id", "file_assets", ["user_id"], unique=False)
    op.create_index("ix_file_assets_sha256", "file_assets", ["sha256"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_file_assets_sha256", table_name="file_assets")
    op.drop_index("ix_file_assets_user_id", table_name="file_assets")
    op.drop_table("file_assets")
