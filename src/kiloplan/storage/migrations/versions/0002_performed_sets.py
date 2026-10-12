"""performed sets

Revision ID: 0002
Revises: 0001
"""

import sqlalchemy as sa
from alembic import op

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.create_table(
        "performed_sets",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("lifter_id", sa.Integer(), nullable=False),
        sa.Column("program_row_id", sa.Integer(), nullable=True),
        sa.Column("source", sa.String(), nullable=False),
        sa.Column("performed_on", sa.Date(), nullable=True),
        sa.Column("date_precision", sa.String(), nullable=False),
        sa.Column("movement_raw", sa.String(), nullable=False),
        sa.Column("lift", sa.String(), nullable=False),
        sa.Column("variation", sa.String(), nullable=False),
        sa.Column("sets", sa.Integer(), nullable=True),
        sa.Column("reps", sa.Integer(), nullable=True),
        sa.Column("load_kg", sa.Double(), nullable=False),
        sa.Column("rpe", sa.Double(), nullable=True),
        sa.Column("rpe_below_5", sa.Boolean(), nullable=False),
        sa.ForeignKeyConstraint(["lifter_id"], ["lifters.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["program_row_id"], ["program_rows.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("performed_sets", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_performed_sets_lift"), ["lift"], unique=False)
        batch_op.create_index(
            batch_op.f("ix_performed_sets_lifter_id"), ["lifter_id"], unique=False
        )
    # programs stored before this table existed: copy each row that has an actual load
    op.execute(
        """
        INSERT INTO performed_sets (
            lifter_id, program_row_id, source, performed_on, date_precision, movement_raw,
            lift, variation, sets, reps, load_kg, rpe, rpe_below_5
        )
        SELECT
            uploads.lifter_id, program_rows.id, 'coach_sheet', weeks.start_date, 'week',
            program_rows.movement_raw, program_rows.lift, program_rows.variation,
            program_rows.sets, program_rows.reps, program_rows.load_kg, program_rows.rpe,
            program_rows.rpe_below_5
        FROM program_rows
        JOIN weeks ON weeks.id = program_rows.week_id
        JOIN blocks ON blocks.id = weeks.block_id
        JOIN uploads ON uploads.id = blocks.upload_id
        WHERE program_rows.load_kg IS NOT NULL
        """
    )


def downgrade() -> None:
    with op.batch_alter_table("performed_sets", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_performed_sets_lifter_id"))
        batch_op.drop_index(batch_op.f("ix_performed_sets_lift"))

    op.drop_table("performed_sets")
