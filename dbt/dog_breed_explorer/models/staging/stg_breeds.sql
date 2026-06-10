with source as (

    -- Pull the latest load only for each breed.
    -- WRITE_APPEND means every scheduler run adds rows, so we deduplicate
    -- here by keeping the most recent ingested_date per breed id.
    select *
    from {{ source('bronze', 'dog_api_raw') }}
    qualify row_number() over (
        partition by id
        order by ingested_date desc
    ) = 1

),

renamed as (

    select
        -- identifiers
        cast(id as int64)                               as breed_id,
        cast(species_id as int64)                       as species_id,

        -- descriptors
        name                                            as breed_name,
        breed_group,
        origin,
        country_code,
        temperament,
        description,
        bred_for,
        perfect_for,
        reference_image_id,

        -- life span: extract all numbers, take min and max
        -- handles both "10 - 12 years" and any other format
        (
            select min(cast(n as int64))
            from unnest(regexp_extract_all(life_span, r'\d+')) as n
        )                                               as life_span_min,
        (
            select max(cast(n as int64))
            from unnest(regexp_extract_all(life_span, r'\d+')) as n
        )                                               as life_span_max,

        -- weight in kg (metric): extract all numbers, take min and max
        -- handles both "6-8" and "Male: 29-54; Female: 25-45"
        (
            select min(cast(n as int64))
            from unnest(regexp_extract_all(weight.metric, r'\d+')) as n
        )                                               as weight_kg_min,
        (
            select max(cast(n as int64))
            from unnest(regexp_extract_all(weight.metric, r'\d+')) as n
        )                                               as weight_kg_max,

        -- height in cm (metric): extract all numbers, take min and max
        -- handles both "38-46" and "Male: 45-53; Female: 43-53"
        (
            select min(cast(n as int64))
            from unnest(regexp_extract_all(height.metric, r'\d+')) as n
        )                                               as height_cm_min,
        (
            select max(cast(n as int64))
            from unnest(regexp_extract_all(height.metric, r'\d+')) as n
        )                                               as height_cm_max,

        -- pipeline metadata
        ingested_date

    from source

)

select * from renamed
