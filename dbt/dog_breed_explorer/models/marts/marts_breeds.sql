with dim as (

    select * from {{ ref('dim_breed') }}

),

fact as (

    select * from {{ ref('fact_weight_life_span') }}

),

final as (

    select
        dim.breed_id,
        dim.breed_name,
        dim.breed_group,
        dim.origin,
        dim.country_code,
        dim.temperament,
        dim.description,
        dim.bred_for,
        dim.perfect_for,
        dim.size_class,
        fact.life_span_min,
        fact.life_span_max,
        fact.life_span_avg,
        fact.weight_kg_min,
        fact.weight_kg_max,
        fact.weight_kg_avg,
        fact.height_cm_min,
        fact.height_cm_max,
        fact.height_cm_avg

    from dim
    inner join fact using (breed_id)

)

select * from final