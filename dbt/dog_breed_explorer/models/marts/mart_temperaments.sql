with base as (

    select * from {{ ref('mart_breeds') }}

),

split as (

    -- Split the comma-separated temperament string into individual rows.
    -- e.g. "Friendly, Intelligent, Loyal" becomes 3 rows, one per temperament.
    select
        breed_id,
        breed_name,
        breed_group,
        size_class,
        trim(temperament_tag)   as temperament
    from base,
    unnest(split(temperament, ',')) as temperament_tag

    -- exclude breeds with no temperament data
    where temperament is not null

)

select * from split