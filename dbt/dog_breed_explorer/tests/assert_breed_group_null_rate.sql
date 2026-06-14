-- Assert that no more than 50% of breeds have a null breed_group.
-- A high null rate suggests the API has changed its response structure.
-- Returns a row (test fails) if the null rate exceeds 50%.

select
    countif(breed_group is null) as null_count,
    count(*) as total_count,
    round(countif(breed_group is null) / count(*), 2) as null_rate
from {{ ref('stg_breeds') }}
having round(countif(breed_group is null) / count(*), 2) > 0.50
