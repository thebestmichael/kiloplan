-- One row per training week, with the block and lifter it belongs to.
select
    weeks.id as week_id,
    uploads.lifter_id,
    blocks.id as block_id,
    blocks.block_index,
    blocks.sheet_name,
    cast(weeks.week_number as integer) as week_number,
    weeks.label as week_label,
    cast(weeks.start_date as date) as week_start,
    cast(weeks.end_date as date) as week_end,
    weeks.sequence as week_sequence
from {{ source('raw', 'weeks') }} as weeks
inner join {{ source('raw', 'blocks') }} as blocks on weeks.block_id = blocks.id
inner join {{ source('raw', 'uploads') }} as uploads on blocks.upload_id = uploads.id
