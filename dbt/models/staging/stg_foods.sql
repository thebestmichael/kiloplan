-- One row per food, with nutrients per 100 g.
select
    id as food_id,
    source,
    fdc_id,
    name as food_name,
    category,
    kcal as kcal_per_100g,
    protein_g as protein_g_per_100g,
    carbs_g as carbs_g_per_100g,
    fat_g as fat_g_per_100g,
    fiber_g as fiber_g_per_100g
from {{ source('raw', 'foods') }}
