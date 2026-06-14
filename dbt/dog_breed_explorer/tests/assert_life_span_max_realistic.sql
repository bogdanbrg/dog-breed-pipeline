-- Assert that life_span_max is within a realistic range (1-30 years).
-- Values outside this range indicate a parsing error in the REGEXP_EXTRACT_ALL logic
-- or bad data from the Dog API.
-- Returns rows that violate the range (test fails if any rows returned).

select
    breed_id,
    life_span_max
from {{ ref('stg_breeds') }}
where life_span_max is not null
  and (life_span_max < 1 or life_span_max > 30)
