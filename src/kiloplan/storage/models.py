"""Tables for uploaded programs and the sets a lifter performed. All loads are in kg."""

from datetime import UTC, date, datetime

from sqlalchemy import JSON, ForeignKey, String
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


# where a performed set came from
COACH_SHEET = "coach_sheet"
APP = "app"
# how exactly `performed_on` is known: the coach sheet only dates its weeks
DAY = "day"
WEEK = "week"


class Lifter(Base):
    __tablename__ = "lifters"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100), unique=True)

    uploads: Mapped[list["Upload"]] = relationship(
        back_populates="lifter", cascade="all, delete-orphan"
    )


class Upload(Base):
    __tablename__ = "uploads"

    id: Mapped[int] = mapped_column(primary_key=True)
    lifter_id: Mapped[int] = mapped_column(ForeignKey("lifters.id", ondelete="CASCADE"))
    filename: Mapped[str]
    uploaded_at: Mapped[datetime] = mapped_column(default=lambda: datetime.now(UTC))
    skipped_sheets: Mapped[list[str]] = mapped_column(JSON, default=list)

    lifter: Mapped[Lifter] = relationship(back_populates="uploads")
    blocks: Mapped[list["Block"]] = relationship(
        back_populates="upload", cascade="all, delete-orphan", order_by="Block.block_index"
    )
    issues: Mapped[list["ProgramIssue"]] = relationship(
        back_populates="upload", cascade="all, delete-orphan", order_by="ProgramIssue.id"
    )


class Block(Base):
    """One Week 1 -> N run of training. `block_index` counts a lifter's blocks from the oldest."""

    __tablename__ = "blocks"

    id: Mapped[int] = mapped_column(primary_key=True)
    upload_id: Mapped[int] = mapped_column(ForeignKey("uploads.id", ondelete="CASCADE"))
    sheet_name: Mapped[str]
    block_index: Mapped[int]

    upload: Mapped[Upload] = relationship(back_populates="blocks")
    weeks: Mapped[list["Week"]] = relationship(
        back_populates="block", cascade="all, delete-orphan", order_by="Week.sequence"
    )


class Week(Base):
    """`sequence` counts a lifter's weeks from the oldest, across blocks."""

    __tablename__ = "weeks"

    id: Mapped[int] = mapped_column(primary_key=True)
    block_id: Mapped[int] = mapped_column(ForeignKey("blocks.id", ondelete="CASCADE"))
    week_number: Mapped[int | None]
    label: Mapped[str]
    start_date: Mapped[date | None]
    end_date: Mapped[date | None]
    sequence: Mapped[int]

    block: Mapped[Block] = relationship(back_populates="weeks")
    rows: Mapped[list["ProgramRow"]] = relationship(
        back_populates="week", cascade="all, delete-orphan", order_by="ProgramRow.row_order"
    )
    notes: Mapped[list["Note"]] = relationship(
        back_populates="week", cascade="all, delete-orphan", order_by="Note.id"
    )


class ProgramRow(Base):
    """One line of the program: a movement done for `sets` x `reps`, RPE of the last set."""

    __tablename__ = "program_rows"

    id: Mapped[int] = mapped_column(primary_key=True)
    week_id: Mapped[int] = mapped_column(ForeignKey("weeks.id", ondelete="CASCADE"))
    day_label: Mapped[str]
    day_order: Mapped[int]
    row_order: Mapped[int]
    movement_raw: Mapped[str]
    lift: Mapped[str] = mapped_column(index=True)
    variation: Mapped[str]
    sets: Mapped[int | None]
    reps: Mapped[int | None]
    reps_raw: Mapped[str]
    load_kg: Mapped[float | None]
    load_raw: Mapped[str]
    assumed_kg: Mapped[bool]
    rpe: Mapped[float | None]
    rpe_below_5: Mapped[bool]
    intensity_raw: Mapped[str]
    target_load_raw: Mapped[str]
    sheet_cell: Mapped[str]

    week: Mapped[Week] = relationship(back_populates="rows")
    issues: Mapped[list["ProgramIssue"]] = relationship(back_populates="row")


class Note(Base):
    __tablename__ = "notes"

    id: Mapped[int] = mapped_column(primary_key=True)
    week_id: Mapped[int] = mapped_column(ForeignKey("weeks.id", ondelete="CASCADE"))
    day_label: Mapped[str]
    text: Mapped[str]
    sheet_cell: Mapped[str]

    week: Mapped[Week] = relationship(back_populates="notes")


class ProgramIssue(Base):
    """Something the parser corrected or could not read, tied to its row when it has one."""

    __tablename__ = "issues"

    id: Mapped[int] = mapped_column(primary_key=True)
    upload_id: Mapped[int] = mapped_column(ForeignKey("uploads.id", ondelete="CASCADE"))
    program_row_id: Mapped[int | None] = mapped_column(
        ForeignKey("program_rows.id", ondelete="CASCADE")
    )
    sheet: Mapped[str]
    cell: Mapped[str]
    message: Mapped[str]

    upload: Mapped[Upload] = relationship(back_populates="issues")
    row: Mapped[ProgramRow | None] = relationship(back_populates="issues")


class PerformedSet(Base):
    """What a lifter actually lifted: `sets` x `reps` at `load_kg`, RPE of the last set.

    Program rows hold the prescription; this is the log the assistant reads. Sets
    imported from a coach sheet keep a link to their program row and take the week's
    start date. Sets logged in the app have their own date and no program row.
    """

    __tablename__ = "performed_sets"

    id: Mapped[int] = mapped_column(primary_key=True)
    lifter_id: Mapped[int] = mapped_column(ForeignKey("lifters.id", ondelete="CASCADE"), index=True)
    program_row_id: Mapped[int | None] = mapped_column(
        ForeignKey("program_rows.id", ondelete="SET NULL")
    )
    source: Mapped[str]
    performed_on: Mapped[date | None]
    date_precision: Mapped[str]
    movement_raw: Mapped[str]
    lift: Mapped[str] = mapped_column(index=True)
    variation: Mapped[str]
    sets: Mapped[int | None]
    reps: Mapped[int | None]
    load_kg: Mapped[float]
    rpe: Mapped[float | None]
    rpe_below_5: Mapped[bool] = mapped_column(default=False)

    lifter: Mapped[Lifter] = relationship()
    program_row: Mapped[ProgramRow | None] = relationship()
