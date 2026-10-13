-- One row per program line: a movement done for sets x reps, RPE of the last set.
select
    id as program_row_id,
    week_id,
    day_label,
    day_order,
    row_order,
    movement_raw as movement,
    lift,
    variation,
    cast(sets as integer) as sets,
    cast(reps as integer) as reps,
    load_kg,
    rpe,
    rpe_below_5,
    assumed_kg
from {{ source('raw', 'program_rows') }}
