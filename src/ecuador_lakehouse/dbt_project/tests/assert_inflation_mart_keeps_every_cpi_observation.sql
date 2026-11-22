-- Reconciliation guard: every general and division CPI observation must reach the
-- inflation mart, otherwise the mom and yoy series silently drop a price point.
with observations as (

    select
        fact.price_area_key,
        fact.cpi_item_key,
        fact.period_date
    from {{ ref('fct_cpi_index') }} as fact
    inner join {{ ref('dim_cpi_item') }} as items
        on items.cpi_item_key = fact.cpi_item_key
    where items.level in ('general', 'division')

)

select
    observations.price_area_key,
    observations.cpi_item_key,
    observations.period_date
from observations
left join {{ ref('mart_inflation_monthly') }} as mart
    on mart.price_area_key = observations.price_area_key
   and mart.cpi_item_key = observations.cpi_item_key
   and mart.period_date = observations.period_date
where mart.period_date is null
