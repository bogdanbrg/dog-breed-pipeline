-- This test fails if any breed has a minimum life span
-- greater than its maximum life span.
-- dbt expects 0 rows returned for a passing test.

select
    breed_id,
    life_span_min,
    life_span_max
from {{ ref('fact_weight_life_span') }}
where life_span_min > life_span_max