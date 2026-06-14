-- Assert that stg_breeds has between 600 and 700 rows.
-- Fewer than 600 suggests the API returned incomplete data.
-- More than 700 suggests unexpected duplicates slipped through.
-- Returns a row (test fails) if the count is outside the expected range.

select count(*) as row_count
from {{ ref('stg_breeds') }}
having count(*) < 600 or count(*) > 700
