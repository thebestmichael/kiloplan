-- Best estimated one-rep max per lifter, week, lift and variation.
select
    cast(lifter_id as varchar) || '-' || cast(week_id as varchar) || '-' || lift || '-' || variation
        as weekly_e1rm_id,
    lifter_id,
    week_id,
    block_index,
    week_number,
    week_sequence,
    week_start,
    lift,
    variation,
    max(e1rm_kg) as best_e1rm_kg,
    count(*) as sets_with_rpe
from {{ ref('int_training_sets') }}
where e1rm_kg is not null
group by lifter_id, week_id, block_index, week_number, week_sequence, week_start, lift, variation
