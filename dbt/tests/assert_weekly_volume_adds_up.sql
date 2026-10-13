-- The weekly table must hold exactly the volume of the sets it was built from.
with sets as (
    select sum(volume_kg) as volume_kg from {{ ref('int_training_sets') }}
),

weekly as (
    select sum(volume_kg) as volume_kg from {{ ref('fct_weekly_volume') }}
)

select sets.volume_kg, weekly.volume_kg as weekly_volume_kg
from sets
cross join weekly
where abs(coalesce(sets.volume_kg, 0) - coalesce(weekly.volume_kg, 0)) > 0.001
