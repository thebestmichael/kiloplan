"""baseline

Revision ID: 0001
Revises:
"""

import sqlalchemy as sa
from alembic import op

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.create_table(
        "lifters",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name"),
    )
    op.create_table(
        "uploads",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("lifter_id", sa.Integer(), nullable=False),
        sa.Column("filename", sa.String(), nullable=False),
        sa.Column("uploaded_at", sa.DateTime(), nullable=False),
        sa.Column("skipped_sheets", sa.JSON(), nullable=False),
        sa.ForeignKeyConstraint(["lifter_id"], ["lifters.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "blocks",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("upload_id", sa.Integer(), nullable=False),
        sa.Column("sheet_name", sa.String(), nullable=False),
        sa.Column("block_index", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["upload_id"], ["uploads.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "weeks",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("block_id", sa.Integer(), nullable=False),
        sa.Column("week_number", sa.Integer(), nullable=True),
        sa.Column("label", sa.String(), nullable=False),
        sa.Column("start_date", sa.Date(), nullable=True),
        sa.Column("end_date", sa.Date(), nullable=True),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["block_id"], ["blocks.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "notes",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("week_id", sa.Integer(), nullable=False),
        sa.Column("day_label", sa.String(), nullable=False),
        sa.Column("text", sa.String(), nullable=False),
        sa.Column("sheet_cell", sa.String(), nullable=False),
        sa.ForeignKeyConstraint(["week_id"], ["weeks.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "program_rows",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("week_id", sa.Integer(), nullable=False),
        sa.Column("day_label", sa.String(), nullable=False),
        sa.Column("day_order", sa.Integer(), nullable=False),
        sa.Column("row_order", sa.Integer(), nullable=False),
        sa.Column("movement_raw", sa.String(), nullable=False),
        sa.Column("lift", sa.String(), nullable=False),
        sa.Column("variation", sa.String(), nullable=False),
        sa.Column("sets", sa.Integer(), nullable=True),
        sa.Column("reps", sa.Integer(), nullable=True),
        sa.Column("reps_raw", sa.String(), nullable=False),
        sa.Column("load_kg", sa.Double(), nullable=True),
        sa.Column("load_raw", sa.String(), nullable=False),
        sa.Column("assumed_kg", sa.Boolean(), nullable=False),
        sa.Column("rpe", sa.Double(), nullable=True),
        sa.Column("rpe_below_5", sa.Boolean(), nullable=False),
        sa.Column("intensity_raw", sa.String(), nullable=False),
        sa.Column("target_load_raw", sa.String(), nullable=False),
        sa.Column("sheet_cell", sa.String(), nullable=False),
        sa.ForeignKeyConstraint(["week_id"], ["weeks.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("program_rows", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_program_rows_lift"), ["lift"], unique=False)

    op.create_table(
        "issues",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("upload_id", sa.Integer(), nullable=False),
        sa.Column("program_row_id", sa.Integer(), nullable=True),
        sa.Column("sheet", sa.String(), nullable=False),
        sa.Column("cell", sa.String(), nullable=False),
        sa.Column("message", sa.String(), nullable=False),
        sa.ForeignKeyConstraint(["program_row_id"], ["program_rows.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["upload_id"], ["uploads.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    op.drop_table("issues")
    with op.batch_alter_table("program_rows", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_program_rows_lift"))

    op.drop_table("program_rows")
    op.drop_table("notes")
    op.drop_table("weeks")
    op.drop_table("blocks")
    op.drop_table("uploads")
    op.drop_table("lifters")
