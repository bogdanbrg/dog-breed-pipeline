with stg as (

    select * from {{ ref('stg_breeds') }}

),

final as (

    select
        breed_id,
        life_span_min,
        life_span_max,
        round((life_span_min + life_span_max) / 2, 1)  as life_span_avg,
        weight_kg_min,
        weight_kg_max,
        round((weight_kg_min + weight_kg_max) / 2, 1)  as weight_kg_avg,
        height_cm_min,
        height_cm_max,
        round((height_cm_min + height_cm_max) / 2, 1)  as height_cm_avg,
        ingested_date

    from stg

)

select * from final