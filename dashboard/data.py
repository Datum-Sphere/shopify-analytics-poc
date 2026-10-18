"""Parameterized, SELECT-only queries. Financial definitions remain in dbt."""
import os
from dataclasses import dataclass
from datetime import date

import psycopg
from psycopg import IsolationLevel
from psycopg.rows import dict_row


class DashboardUnavailable(Exception):
    """Sanitized connection/query failure safe to show in the UI."""


@dataclass(frozen=True)
class Filters:
    synthetic: bool
    store: str
    currency: str
    start: date
    end: date

    def __post_init__(self):
        if self.start > self.end:
            raise ValueError("Start date must not follow end date")
        if not self.store or not self.currency:
            raise ValueError("Choose a data source and currency")

    @property
    def params(self):
        return (self.synthetic,self.store,self.currency,self.start,self.end)


def connect():
    # No fallback to POSTGRES_USER or application/Shopify credentials.
    connection = psycopg.connect(
        host=os.environ["DASHBOARD_DB_HOST"],port=int(os.environ.get("DASHBOARD_DB_PORT","5432")),
        dbname=os.environ["DASHBOARD_DB_NAME"],user="shopify_dashboard",
        password=os.environ["DASHBOARD_DB_PASSWORD"],connect_timeout=5,
        options="-c statement_timeout=10000 -c default_transaction_read_only=on",row_factory=dict_row)
    connection.read_only = True
    connection.isolation_level = IsolationLevel.REPEATABLE_READ
    return connection


CATALOG_SQL = """
with available as (
 select store_domain,is_synthetic,currency_code,reporting_date from analytics.mart_daily_sales
 union all
 select store_domain,is_synthetic,currency_code,reporting_date from analytics.dashboard_financial_issues
)
select store_domain,is_synthetic,currency_code,min(reporting_date) as first_date,max(reporting_date) as last_date
from available group by store_domain,is_synthetic,currency_code
order by store_domain,currency_code nulls last
"""
WHERE = "is_synthetic=%s and store_domain=%s and currency_code=%s and reporting_date between %s and %s"
DAILY_SQL = "SELECT reporting_date,gross_sales,discounts,returns_amount,net_sales,unsupported_event_count FROM analytics.mart_daily_sales WHERE " + WHERE + " ORDER BY reporting_date"
KPI_SQL = """
select count(*) as day_count,
 case when bool_and(unsupported_event_count=0 and gross_sales is not null and discounts is not null and returns_amount is not null and net_sales is not null)
      then sum(gross_sales) end as gross_sales,
 case when bool_and(unsupported_event_count=0 and gross_sales is not null and discounts is not null and returns_amount is not null and net_sales is not null)
      then sum(discounts) end as discounts,
 case when bool_and(unsupported_event_count=0 and gross_sales is not null and discounts is not null and returns_amount is not null and net_sales is not null)
      then sum(returns_amount) end as returns_amount,
 case when bool_and(unsupported_event_count=0 and gross_sales is not null and discounts is not null and returns_amount is not null and net_sales is not null)
      then sum(net_sales) end as net_sales
from analytics.mart_daily_sales WHERE """ + WHERE
PRODUCTS_SQL = """
with product_totals as (
 select product_key,case when bool_and(coalesce(is_supported,false) and net_sales is not null)
                         then sum(net_sales) end as net_sales
 from analytics.fct_sales_events WHERE """ + WHERE + """ and is_test=false
 group by product_key
)
select coalesce(t.product_key,'__custom__') as product_key,
       coalesce(nullif(d.title,''),'Custom / unlinked product') as title,t.net_sales
from product_totals t
left join analytics.dim_product d on t.product_key=d.product_key
order by t.net_sales desc nulls last,product_key
"""
ISSUES_SQL = """
select count(*) as issue_count from analytics.dashboard_financial_issues
where is_synthetic=%s and store_domain=%s and (currency_code=%s or currency_code is null)
  and (reporting_date between %s and %s or reporting_date is null)
"""
METADATA_SQL = """
select last_successful_ingestion_at from analytics.dashboard_ingestion_status
where is_synthetic=%s and store_domain=%s
"""
METRICS = ("gross_sales","discounts","returns_amount","net_sales")


def catalog(connection_factory=connect):
    try:
        with connection_factory() as connection:
            return connection.execute(CATALOG_SQL).fetchall()
    except Exception:
        raise DashboardUnavailable("Analytics is not ready. Ask the project operator to complete the documented database and dbt setup.") from None


def load(filters, connection_factory=connect):
    try:
        with connection_factory() as connection:
            daily=connection.execute(DAILY_SQL,filters.params).fetchall()
            kpis=connection.execute(KPI_SQL,filters.params).fetchone()
            products=connection.execute(PRODUCTS_SQL,filters.params).fetchall()
            issues=connection.execute(ISSUES_SQL,filters.params).fetchone()["issue_count"]
            meta=connection.execute(METADATA_SQL,(filters.synthetic,filters.store)).fetchone()
        blocked=(issues>0 or any(row["unsupported_event_count"] or any(row[k] is None for k in METRICS) for row in daily)
                 or any(p["net_sales"] is None for p in products)
                 or (kpis["day_count"]>0 and any(kpis[k] is None for k in METRICS)))
        status="unsupported" if blocked else "empty" if not daily else "ready"
        # Never expose partial valid sums as complete totals in a blocked range.
        if status!="ready":
            kpis={**kpis,**dict.fromkeys(METRICS)}
            daily=[]
            products=[]
        return {"status":status,"kpis":kpis,"daily":daily,"products":products,
                "issue_count":issues,"last_successful_ingestion_at":meta["last_successful_ingestion_at"] if meta else None}
    except DashboardUnavailable:
        raise
    except Exception:
        raise DashboardUnavailable("Analytics data could not be read. Ask the project operator to check the read-only connection and model readiness.") from None
