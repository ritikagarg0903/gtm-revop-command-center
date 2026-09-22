from __future__ import annotations

import importlib
import os
from pathlib import Path

import pandas as pd
import plotly.express as px
import streamlit as st

from src.gtm_operations import (
    REVIEW_REASONS,
    REVIEW_STATUSES,
    route_leads,
    score_prospects,
)
from src.metrics import filter_deals
from src.risk_scoring import add_risk_scores
from src.workflow import Workflow
from src.nurture_campaigns import campaign_records
from src.company_context import company_context


PROJECT_ROOT = Path(__file__).resolve().parent
DATA_DIR = PROJECT_ROOT / "data"
DEALS_PATH = DATA_DIR / "synthetic_deals.csv"
QUOTAS_PATH = DATA_DIR / "rep_quotas.csv"
LEADS_PATH = DATA_DIR / "synthetic_leads.csv"
PROSPECTS_PATH = DATA_DIR / "synthetic_prospects.csv"
REP_CAPACITY_PATH = DATA_DIR / "rep_capacity.csv"
DATA_SCHEMA_VERSION = 4


st.set_page_config(
    page_title="GTM & Revenue Operations Command Center",
    page_icon=":bar_chart:",
    layout="wide",
)

st.markdown(
    """
    <style>
        .block-container {
            padding-top: 0.85rem;
            padding-bottom: 1rem;
            max-width: 1500px;
        }
        [data-testid="stHeader"] { height: 2.25rem; }
        h1 { margin-top: 0; margin-bottom: 0.15rem; padding-top: 0.2rem; line-height: 1.3; }
        h2, h3 { margin-top: 0.4rem; margin-bottom: 0.2rem; }
        [data-testid="stMetric"] { padding-top: 0.15rem; padding-bottom: 0.15rem; }
        [data-testid="stCaptionContainer"] { margin-bottom: 0.25rem; }
        [data-testid="stCaptionContainer"] p { margin-bottom: 0; }
        .stTabs [data-baseweb="tab-list"] { gap: 0.35rem; }
        .stTabs [data-baseweb="tab"] { padding-top: 0.45rem; padding-bottom: 0.45rem; }
        .stTabs { margin-top: -0.35rem; }
        .modebar { display: none !important; }
    </style>
    """,
    unsafe_allow_html=True,
)


def money(value: float) -> str:
    if value >= 1_000_000:
        return f"${value / 1_000_000:.1f}M"
    if value >= 1_000:
        return f"${value / 1_000:.0f}K"
    return f"${value:,.0f}"


def current_quarter_label() -> str:
    today = pd.Timestamp.today()
    quarter = ((today.month - 1) // 3) + 1
    return f"{today.year} Q{quarter}"


@st.cache_data
def load_data(schema_version: int) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    _ = schema_version  # Changing this value invalidates cached synthetic data after schema updates.
    paths = [DEALS_PATH, QUOTAS_PATH, LEADS_PATH, PROSPECTS_PATH, REP_CAPACITY_PATH]
    data_factory = None
    if not all(path.exists() for path in paths):
        data_factory = importlib.reload(importlib.import_module("src.generate_data"))

    deals = pd.read_csv(DEALS_PATH) if DEALS_PATH.exists() else data_factory.generate_deals()
    quotas = pd.read_csv(QUOTAS_PATH) if QUOTAS_PATH.exists() else data_factory.generate_quotas()
    leads = pd.read_csv(LEADS_PATH) if LEADS_PATH.exists() else data_factory.generate_leads(deals)
    prospects = pd.read_csv(PROSPECTS_PATH) if PROSPECTS_PATH.exists() else data_factory.generate_prospects()
    rep_capacity = (
        pd.read_csv(REP_CAPACITY_PATH) if REP_CAPACITY_PATH.exists() else data_factory.generate_rep_capacity()
    )
    date_columns = ["created_date", "expected_close_date", "actual_close_date", "last_activity_date"]
    for column in date_columns:
        deals[column] = pd.to_datetime(deals[column], errors="coerce")

    lead_date_columns = [
        "lead_created_date",
        "mql_date",
        "sales_accepted_date",
        "first_sales_contact_at",
        "sql_date",
        "opportunity_date",
        "customer_date",
    ]
    for column in lead_date_columns:
        leads[column] = pd.to_datetime(leads[column], errors="coerce")
    leads["lead_quarter"] = leads["lead_created_date"].dt.year.astype(str) + " Q" + leads[
        "lead_created_date"
    ].dt.quarter.astype(str)
    prospects["source_updated_at"] = pd.to_datetime(prospects["source_updated_at"], errors="coerce")
    prospects["received_at"] = pd.to_datetime(prospects["received_at"], errors="coerce")

    deals = add_risk_scores(deals)
    return deals, quotas, leads, prospects, rep_capacity


def section_header(title: str, caption: str) -> None:
    if caption:
        st.caption(caption)


def bar_chart(
    df: pd.DataFrame,
    x: str,
    y: str,
    color: str | None = None,
    title: str | None = None,
    height: int = 390,
):
    fig = px.bar(df, x=x, y=y, color=color, title=title, text_auto=".2s")
    fig.update_layout(
        margin=dict(l=20, r=20, t=45, b=15),
        height=height,
        xaxis_title=friendly_column_name(x),
        yaxis_title=friendly_column_name(y),
        legend_title_text=friendly_column_name(color) if color else None,
    )
    return fig


def friendly_column_name(column: str) -> str:
    abbreviations = {
        "id": "ID",
        "mql": "MQL",
        "sql": "SQL",
        "sla": "SLA",
        "ai": "AI",
        "ci": "CI",
        "pct": "%",
        "crm": "CRM",
        "gtm": "GTM",
        "url": "URL",
    }
    lower_case_words = {"and", "at", "by", "for", "from", "in", "of", "on", "to"}
    words = []
    for index, part in enumerate(column.split("_")):
        lowered = part.lower()
        if lowered in abbreviations:
            words.append(abbreviations[lowered])
        elif index > 0 and lowered in lower_case_words:
            words.append(lowered)
        else:
            words.append(part.capitalize())
    return " ".join(words)


def friendly_dataframe(data: pd.DataFrame, **kwargs):
    overrides = kwargs.pop("column_config", {}) or {}
    defaults = {column: friendly_column_name(str(column)) for column in data.columns}
    kwargs["column_config"] = {**defaults, **overrides}
    return st.dataframe(data, **kwargs)


def friendly_data_editor(data: pd.DataFrame, **kwargs):
    overrides = kwargs.pop("column_config", {}) or {}
    defaults = {column: friendly_column_name(str(column)) for column in data.columns}
    kwargs["column_config"] = {**defaults, **overrides}
    return st.data_editor(data, **kwargs)


def show_chart(fig, **kwargs):
    config = kwargs.pop("config", {}) or {}
    config["displayModeBar"] = False
    return st.plotly_chart(fig, config=config, **kwargs)


deals, quotas, leads, prospects, rep_capacity = load_data(DATA_SCHEMA_VERSION)
prospects = company_context(prospects)

st.title("GTM & Revenue Operations Command Center")
st.caption(
    "Marketing performance, prospect readiness, lead routing, and nurture recovery."
)

with st.sidebar:
    st.header("Filters")
    quarters = sorted(deals["close_quarter"].dropna().unique())
    current_quarter = current_quarter_label()
    default_quarter = current_quarter if current_quarter in quarters else quarters[-1]
    selected_quarter = st.selectbox("Reporting quarter", quarters, index=quarters.index(default_quarter))

    selected_segments = st.multiselect("Segment", sorted(deals["segment"].unique()))

    st.divider()
    st.caption("Synthetic data. Quarter selects lead creation and opportunity close dates. Segment applies across all tabs. Operations and nurture recovery show the current prospect cohort, independent of quarter.")

filtered = filter_deals(deals, selected_quarter, selected_segments, [], [])
filtered_leads = leads[leads["lead_quarter"] == selected_quarter].copy()
if selected_segments:
    filtered_leads = filtered_leads[filtered_leads["segment"].isin(selected_segments)]

# Process the entire cohort before presentation filters so capacity and history stay stable.
all_scored = score_prospects(prospects, {"fit": 40, "intent": 30, "signal_data_confidence": 30})
workflow_input = prospects.merge(all_scored[["prospect_id", "total_score"]], on="prospect_id", how="left")
workflow_input["total_score"] = workflow_input["total_score"].fillna(0)
workflow = Workflow(os.environ.get("WORKFLOW_DB", str(DATA_DIR / "sample-workflow.sqlite")))
try:
    lifecycle = workflow.run(workflow_input, rep_capacity)
finally:
    workflow.close()
if selected_segments:
    prospects = prospects[prospects["segment"].isin(selected_segments)].copy()
    lifecycle = lifecycle[lifecycle["segment"].isin(selected_segments)].copy()
nurture_total = lifecycle.nurture_entry_date.notna().sum()
recovered = lifecycle.re_engagement_date.notna().sum()
recycling = {"nurture_total": int(nurture_total), "recovered": int(recovered),
             "recovery_rate": 100 * recovered / nurture_total if nurture_total else 0}
lead_to_mql_rate = filtered_leads["mql_date"].notna().mean() * 100 if len(filtered_leads) else None
# Explicit attribution convention for this synthetic marketing portfolio.
marketing_sources = ["Inbound", "Paid Search", "Events"]
marketing_pipeline = filtered.loc[
    filtered["acquisition_source"].isin(marketing_sources), "deal_amount"
].sum()

overview_view, enrichment_view, scoring_view, routing_view, recycling_view = st.tabs(
    ["Overview", "Prospecting & Enrichment", "Scoring & Review", "Lead Routing", "Nurture Campaigns"]
)

with overview_view:
    st.caption("The essentials: lead volume, qualification, marketing contribution, and nurture recovery.")
    a, b, c, d = st.columns(4)
    a.metric("Leads Generated", f"{len(filtered_leads):,}",
             help="Leads created in the reporting quarter and selected segments.")
    b.metric("Lead-to-MQL Conversion", f"{lead_to_mql_rate:.1f}%" if lead_to_mql_rate is not None else "—",
             help="Leads with an MQL milestone divided by all leads created in the selected quarter.")
    c.metric("Marketing-Sourced Pipeline", money(marketing_pipeline),
             help="Total opportunity value from Inbound, Paid Search, and Events with a close date in the reporting quarter, across all deal stages. Outbound, Partners, and Referrals are excluded.")
    d.metric("Nurture-to-SQL Recovery", f"{recycling['recovery_rate']:.1f}%" if recycling['nurture_total'] else "—",
             help=f"{recycling['recovered']} recovered SQLs / {recycling['nurture_total']} nurture entrants in the current prospect cohort; independent of quarter.")
    a.caption("New leads created during the selected quarter.")
    b.caption("Percentage of those leads that became marketing-qualified (MQLs).")
    c.caption("Opportunity value from Inbound, Paid Search, and Events, across all deal stages—not booked revenue.")
    d.caption("Percentage of nurtured leads that became sales-qualified (SQLs).")
    st.caption("Lead metrics use the selected creation quarter; pipeline uses the selected close quarter. Nurture recovery reflects the current prospect cohort.")

with routing_view:
    st.subheader("Lead ownership")
    owned = lifecycle.assigned_rep.ne("")
    awaiting = lifecycle.lifecycle_stage.eq("MQL") & ~owned & ~lifecycle.blocked
    a, b = st.columns(2)
    a.metric("Assigned Leads", int(owned.sum()))
    b.metric("Awaiting Owner", int(awaiting.sum()))
    friendly_dataframe(lifecycle[["prospect_id", "account_name", "segment", "territory", "lifecycle_stage", "assigned_rep", "next_action"]], hide_index=True, use_container_width=True)
    with st.expander("Rep capacity and availability"):
        friendly_dataframe(rep_capacity, hide_index=True, use_container_width=True)

with enrichment_view:
    st.info(
        "**Process:** This workflow takes raw company and contact records from prospecting providers, "
        "standardizes email and domain fields, validates their quality, identifies duplicates, "
        "and produces clean records that are ready for CRM delivery."
    )
    stale_cutoff = pd.Timestamp.now() - pd.Timedelta(days=30)
    enrich1, enrich2, enrich3, enrich4 = st.columns(4)
    enrich1.metric("Canonical Prospects", f"{len(prospects):,}")
    enrich2.metric("Valid Email Rate", f"{prospects['email_valid'].mean() * 100:.1f}%")
    enrich3.metric("Duplicates Blocked", f"{prospects['is_duplicate'].sum():,}")
    enrich4.metric("Records Older Than 30 Days", f"{(prospects['source_updated_at'] < stale_cutoff).sum():,}")

    provider_quality = prospects.groupby("source_provider", as_index=False).agg(
        records=("prospect_id", "count"),
        valid_email_rate=("email_valid", "mean"),
        valid_domain_rate=("domain_valid", "mean"),
        duplicate_rate=("is_duplicate", "mean"),
    )
    for column in ["valid_email_rate", "valid_domain_rate", "duplicate_rate"]:
        provider_quality[column] = (provider_quality[column] * 100).round(1)
    st.markdown("**Provider Data Quality**")
    friendly_dataframe(
        provider_quality,
        use_container_width=True,
        hide_index=True,
        column_config={column: st.column_config.NumberColumn(friendly_column_name(column), format="%.1f%%") for column in [
            "valid_email_rate", "valid_domain_rate", "duplicate_rate"
        ]},
    )

    st.markdown("**Validated and Enriched Prospects Ready for CRM**")
    enrichment_display = prospects[
        ~prospects["is_duplicate"] & prospects["email_valid"] & prospects["domain_valid"]
    ].copy()
    friendly_dataframe(
        enrichment_display[
            [
                "prospect_id",
                "account_name",
                "canonical_domain",
                "contact_name",
                "job_title",
                "canonical_email",
                "segment",
                "territory",
                "employee_count",
                "website_visits_30d",
                "content_engagements_30d",
                "pricing_page_views_30d",
                "source_provider",
                "industry",
                "company_description",
                "target_customers",
                "business_model",
                "headquarters",
                "suggested_outreach",
                "source_updated_at",
            ]
        ].head(100),
        use_container_width=True,
        hide_index=True,
        column_config={
            "website_visits_30d": "Website Visits (30 Days)",
            "content_engagements_30d": "Content Engagements (30 Days)",
            "pricing_page_views_30d": "Pricing Page Views (30 Days)",
        },
    )

with scoring_view:
    scoring_eligible = prospects[
        prospects["email_valid"]
        & prospects["domain_valid"]
        & ~prospects["is_duplicate"]
    ]
    excluded_from_scoring = len(prospects) - len(scoring_eligible)
    st.caption(f"{excluded_from_scoring:,} records need data repair. Valid leads are scored automatically; a score of 70 qualifies for routing.")
    scored = score_prospects(prospects, {"fit": 40, "intent": 30, "signal_data_confidence": 30})

    score_summary = pd.DataFrame(
        {
            "score_component": ["Fit", "Intent", "Signal & data confidence", "Weighted total"],
            "average_score": [
                scored["fit_score"].mean(),
                scored["intent_score"].mean(),
                scored["signal_data_confidence_score"].mean(),
                scored["total_score"].mean(),
            ],
        }
    )
    show_chart(
        bar_chart(score_summary, "score_component", "average_score", title="Average Score by Component"),
        use_container_width=True,
    )

    friendly_dataframe(scored[["prospect_id", "account_name", "segment", "fit_score", "intent_score", "signal_data_confidence_score", "total_score"]], hide_index=True, use_container_width=True)

with recycling_view:
    st.subheader("Nurture Campaigns")
    campaigns = campaign_records(lifecycle, os.environ.get("MARKETING_FROM_EMAIL", "Not configured"))
    a, b, c = st.columns(3)
    a.metric("Campaign Enrollments", len(campaigns))
    b.metric("Emails Sent", int(lifecycle.loc[lifecycle.status.eq("nurture"), "nurture_touch_count"].sum()))
    c.metric("Recovered SQLs", recycling["recovered"])
    st.caption("Marketing-owned email campaigns · sample data · email delivery not connected. Sent counts require delivery confirmation; blank engagement counts mean tracking history is unavailable.")
    if campaigns.empty:
        st.info("No leads are currently enrolled in nurture campaigns.")
    else:
        friendly_dataframe(campaigns, hide_index=True, use_container_width=True,
            column_config={"email_type": "Next Email Type", "email_theme": "Next Email Theme",
                           "next_email_due": st.column_config.DatetimeColumn("Next Email Due (UTC)", format="D MMM YYYY"),
                           "last_email_sent": st.column_config.DatetimeColumn("Last Email Sent (UTC)", format="D MMM YYYY"),
                           "enrolled_on": st.column_config.DatetimeColumn("Enrolled On (UTC)", format="D MMM YYYY")})
    st.caption("Campaigns use the configured company marketing address. A due date is a planned send, not confirmation that an email was sent.")
    st.download_button("Download campaign tracking", campaigns.to_csv(index=False), "nurture-campaigns.csv", "text/csv")
