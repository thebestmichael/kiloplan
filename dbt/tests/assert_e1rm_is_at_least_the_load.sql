-- An estimated one-rep max can never be below the weight that was lifted.
select program_row_id, load_kg, e1rm_kg
from {{ ref('int_training_sets') }}
where e1rm_kg < load_kg - 0.001
