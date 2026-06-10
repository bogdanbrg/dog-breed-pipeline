with stg as (

    select * from {{ ref('stg_breeds') }}

),

final as (

    select
        breed_id,
        breed_name,
        breed_group,
        origin,
        country_code,
        temperament,
        description,
        bred_for,
        perfect_for,
        reference_image_id,

        -- derive a size class from max weight
        case
            when weight_kg_max <= 5  then 'Toy'
            when weight_kg_max <= 10 then 'Small'
            when weight_kg_max <= 25 then 'Medium'
            when weight_kg_max <= 45 then 'Large'
            when weight_kg_max > 45  then 'Giant'
            else 'Unknown'
        end                         as size_class

    from stg

)

select * from final