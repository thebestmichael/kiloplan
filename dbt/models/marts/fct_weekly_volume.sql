-- Training volume per lifter, week and lift.
select
    cast(lifter_id as varchar) || '-' || cast(week_id as varchar) || '-' || lift as weekly_volume_id,
    lifter_id,
    week_id,
    block_index,
    week_number,
    week_sequence,
    week_start,
    lift,
    sum(sets) as total_sets,
    sum(sets * reps) as total_reps,
    sum(volume_kg) as volume_kg,
    max(load_kg) as top_load_kg
from {{ ref('int_training_sets') }}
group by lifter_id, week_id, block_index, week_number, week_sequence, week_start, lift
