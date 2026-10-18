"""Read-only financial dashboard with authenticated, fixed-operation control."""
from datetime import timezone

import streamlit as st

from dashboard import data, charts
from dashboard.pipeline_controls import render as pipeline_controls


def amount(value,currency):
    if value is None:
        return "—"
    places=max(2,-value.as_tuple().exponent)
    return f"{currency} {value:,.{places}f}"


def main():
    st.set_page_config(page_title="Shopify Sales Analytics | DatumSphere",page_icon="📊",layout="wide")
    st.markdown("""<style>
    .block-container {padding-top:2rem;max-width:1480px;}
    [data-testid="stMetric"] {background:white;border-radius:12px;padding:18px;}
    [data-testid="stMetricLabel"] {color:#64748B;}
    [data-testid="stMetricValue"] {font-size:1.9rem;}
    h1 {letter-spacing:-0.035em;}
    </style>""",unsafe_allow_html=True)
    st.caption("DATUMSPHERE  /  COMMERCE INTELLIGENCE")
    st.title("Shopify Sales Analytics")
    st.write("Merchandise performance, with a clear view of sales and reversals.")
    with st.sidebar:
        st.header("Explore your data")
        label=st.selectbox("Dataset",["Live Shopify","Synthetic Demo"],key="dataset")
        synthetic=label=="Synthetic Demo"
        st.divider()
        pipeline_controls()
    st.info("Validation boundary: synthetic scenarios validate the models; live figures come from the Shopify API. Neither is Shopify-report reconciliation.",icon="ℹ️")
    try:
        available=[r for r in data.catalog() if r["is_synthetic"]==synthetic]
        if not available:
            st.info("No financial data is available for this dataset yet.")
            return
        stores=sorted({r["store_domain"] for r in available})
        with st.sidebar:
            store=st.selectbox("Store",stores,key="store_"+label)
            source_rows=[r for r in available if r["store_domain"]==store]
            currencies=sorted({r["currency_code"] for r in source_rows if r["currency_code"]})
            if not currencies:
                st.error("This source has incomplete currency or date information. Financial reporting is unavailable.")
                return
            currency=st.selectbox("Currency",currencies,key="currency_"+label+store)
            ranges=[r for r in source_rows if r["currency_code"]==currency and r["first_date"] and r["last_date"]]
            if not ranges:
                st.error("Reporting dates are missing or unsupported. Ask the operator to review financial data quality.")
                return
            start=min(r["first_date"] for r in ranges)
            end=max(r["last_date"] for r in ranges)
            dates=st.date_input("Reporting dates",value=(start,end),min_value=start,max_value=end,
                                key="dates_"+label+store+currency,format="YYYY-MM-DD")
            if len(dates)!=2:
                st.info("Choose both the start and end of the reporting range.")
                return
            st.caption("Dates use the shop timezone recorded by the financial models. Currencies are never converted.")
        filters=data.Filters(synthetic,store,currency,dates[0],dates[1])
        result=data.load(filters)
    except data.DashboardUnavailable as exc:
        st.warning(str(exc))
        return
    stamp=result["last_successful_ingestion_at"]
    last=stamp.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M UTC") if stamp else "Not recorded"
    st.caption(f"Source: {label} · {store}  |  {currency}  |  {dates[0]} to {dates[1]}")
    st.caption("Last successful ingestion in this publication: "+last+"  ·  Read-only PostgreSQL / dbt output")
    if result.get("published_at"):
        st.caption(f"Validated publication: {result['published_at']} · Pipeline run: {result['publication_run_id']}")
    if result["status"]=="unsupported":
        st.error("Financial reporting is paused for this selection. Unsupported or incomplete financial records were detected; totals and charts are withheld to avoid partial or misleading figures.")
    columns=st.columns(4)
    for column,key,title in zip(columns,data.METRICS,("Gross Sales","Discounts","Returns","Net Sales")):
        column.metric(title,amount(result["kpis"][key],currency),border=True)
    st.caption("Returns are discounted, pre-tax merchandise reversals shown as positive deductions. Net sales excludes taxes, shipping, fees and gift-card issuance.")
    if result["status"]=="empty":
        st.info("No financial events fall within this date range. Missing values are not treated as zero.")
        return
    if result["status"]!="ready":
        return
    with st.container(border=True):
        st.subheader("Sales over time")
        st.caption("Gross and net sales on store-local agreement dates. Later reversals can produce negative net sales.")
        st.plotly_chart(charts.daily_trend(result["daily"],currency),use_container_width=True,key="daily_sales")
    left,right=st.columns([1,1.25])
    with left,st.container(border=True):
        st.subheader("Returns by date")
        st.caption("Financial merchandise reversals; not payment refunds or physical return counts.")
        st.plotly_chart(charts.returns_trend(result["daily"],currency),use_container_width=True,key="returns")
    with right,st.container(border=True):
        st.subheader("Top products by net sales")
        st.caption("Up to 10 products in the same dataset, currency and date range. Custom / unlinked products remain included.")
        st.plotly_chart(charts.top_products(result["products"],currency),use_container_width=True,key="products")
    with st.expander("Financial definitions and validation"):
        st.write("KPIs aggregate tested dbt model columns; the dashboard does not redefine Shopify financial metrics. Test orders are excluded. Synthetic and live figures are kept separate.")
        st.write("Gross sales − discounts − returns = net merchandise sales. Refund audit records are not added to sale events. Product titles reflect the current catalog or the model's missing-catalog fallback.")
        st.write("The demo store currently verifies order #1001 against API data. Partial-return and discount scenarios are fixture-validated. No Shopify Analytics export or ShopifyQL report reconciliation has been performed.")
        st.caption("The financial snapshot is published only after dbt build/tests succeed. This is model validation, not Shopify report reconciliation.")
        st.caption("Project contract: docs/FINANCIALS.md. No remote access is enabled.")


if __name__=="__main__":
    main()
