select daily_macros_id
from {{ ref('fct_daily_macros') }}
where kcal < 0 or protein_g < 0 or carbs_g < 0 or fat_g < 0
