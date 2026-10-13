-- One row per food diary entry. Macros were fixed when the entry was logged.
select
    id as diary_entry_id,
    lifter_id,
    cast(day as date) as diary_date,
    meal,
    food_id,
    description,
    grams,
    kcal,
    protein_g,
    carbs_g,
    fat_g
from {{ source('raw', 'diary_entries') }}
