-- Calories and macros eaten per lifter per day.
select
    cast(lifter_id as varchar) || '-' || cast(diary_date as varchar) as daily_macros_id,
    lifter_id,
    diary_date,
    sum(kcal) as kcal,
    sum(protein_g) as protein_g,
    sum(carbs_g) as carbs_g,
    sum(fat_g) as fat_g,
    count(*) as entries
from {{ ref('stg_diary_entries') }}
group by lifter_id, diary_date
