-- Squat, bench and deadlift lines that were actually done (a load, sets and reps),
-- with their volume and, where an RPE was logged, an estimated one-rep max.
select
    program_rows.program_row_id,
    weeks.lifter_id,
    weeks.week_id,
    weeks.block_index,
    weeks.week_number,
    weeks.week_sequence,
    weeks.week_start,
    program_rows.lift,
    program_rows.variation,
    program_rows.sets,
    program_rows.reps,
    program_rows.load_kg,
    program_rows.rpe,
    program_rows.sets * program_rows.reps * program_rows.load_kg as volume_kg,
    case
        when program_rows.rpe is not null
            then {{ e1rm_hybrid('program_rows.load_kg', 'program_rows.reps', 'program_rows.rpe') }}
    end as e1rm_kg
from {{ ref('stg_program_rows') }} as program_rows
inner join {{ ref('stg_weeks') }} as weeks on program_rows.week_id = weeks.week_id
where
    program_rows.lift != 'other'
    and program_rows.load_kg > 0
    and program_rows.sets > 0
    and program_rows.reps > 0
