from __future__ import annotations

import importlib
from pathlib import Path

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from src.gtm_operations import (
    REVIEW_REASONS,
    REVIEW_STATUSES,
    route_leads,
    score_prospects,
)
from src.metrics import (
    OPEN_STAGES,
    filter_deals,
    gtm_funnel,
    open_deals,
    pipeline_coverage,
    quota_attainment,
    sla_summary,
    source_performance,
    stale_deals,
)
from src.risk_scoring import add_risk_scores


PROJECT_ROOT = Path(__file__).resolve().parent
DATA_DIR = PROJECT_ROOT / "data"
DEALS_PATH = DATA_DIR / "synthetic_deals.csv"
QUOTAS_PATH = DATA_DIR / "rep_quotas.csv"
LEADS_PATH = DATA_DIR / "synthetic_leads.csv"
PROSPECTS_PATH = DATA_DIR / "synthetic_prospects.csv"
REP_CAPACITY_PATH = DATA_DIR / "rep_capacity.csv"
DATA_SCHEMA_VERSION = 3


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


def insight(text: str) -> None:
    escaped_text = text.replace("$", r"\$")
    st.info(f"**Insight:** {escaped_text}")


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


def operating_flow_chart(stages: list[tuple[str, str]]):
    """Build a compact, non-proportional view of the GTM operating sequence."""
    box_width = 0.16
    gap = (1 - box_width * len(stages)) / (len(stages) - 1)
    colors = ["#2563EB", "#0EA5E9", "#14B8A6", "#22C55E", "#84CC16"]
    fig = go.Figure()

    for index, ((label, value), color) in enumerate(zip(stages, colors)):
        x0 = index * (box_width + gap)
        x1 = x0 + box_width
        fig.add_shape(
            type="rect",
            x0=x0,
            x1=x1,
            y0=0.22,
            y1=0.82,
            line=dict(color=color, width=2),
            fillcolor=color,
            opacity=0.12,
            layer="below",
        )
        fig.add_annotation(
            x=(x0 + x1) / 2,
            y=0.52,
            text=f"<b>{label}</b><br><span style='font-size:20px'>{value}</span>",
            showarrow=False,
            align="center",
            font=dict(color="#0F172A", size=13),
        )
        if index < len(stages) - 1:
            fig.add_annotation(
                x=x1 + gap * 0.82,
                y=0.52,
                ax=x1 + gap * 0.18,
                ay=0.52,
                xref="x",
                yref="y",
                axref="x",
                ayref="y",
                text="",
                showarrow=True,
                arrowhead=2,
                arrowsize=1.1,
                arrowwidth=2,
                arrowcolor="#94A3B8",
            )

    fig.update_xaxes(range=[-0.02, 1.02], visible=False, fixedrange=True)
    fig.update_yaxes(range=[0, 1], visible=False, fixedrange=True)
    fig.update_layout(
        title="GTM Operating Flow",
        height=250,
        margin=dict(l=15, r=15, t=55, b=10),
        plot_bgcolor="rgba(0,0,0,0)",
        paper_bgcolor="rgba(0,0,0,0)",
    )
    return fig


deals, quotas, leads, prospects, rep_capacity = load_data(DATA_SCHEMA_VERSION)

st.title("GTM & Revenue Operations Command Center")
st.caption(
    "An end-to-end view of demand conversion, acquisition sources, pipeline health, "
    "prospect readiness, and lead routing."
)

with st.sidebar:
    st.header("Filters")
    quarters = sorted(deals["close_quarter"].dropna().unique())
    current_quarter = current_quarter_label()
    default_quarter = current_quarter if current_quarter in quarters else quarters[-1]
    selected_quarter = st.selectbox("Close quarter", quarters, index=quarters.index(default_quarter))

    selected_segments = st.multiselect("Segment", sorted(deals["segment"].unique()))

    st.divider()
    st.caption("Data is synthetic. Quarter and segment filters apply across every dashboard section.")

filtered = filter_deals(deals, selected_quarter, selected_segments, [], [])
if filtered.empty:
    st.warning(
        "No deals match the current filters. Clear one or more filters to restore dashboard results."
    )
    st.stop()

filtered_leads = leads[leads["lead_quarter"] == selected_quarter].copy()
if selected_segments:
    filtered_leads = filtered_leads[filtered_leads["segment"].isin(selected_segments)]

filtered_open = open_deals(filtered)
attainment = quota_attainment(filtered, quotas, selected_quarter)
if selected_segments:
    attainment = attainment[attainment["segment_focus"].isin(selected_segments)].copy()
coverage = pipeline_coverage(filtered, attainment)
overview_prospects = prospects.copy()
if selected_segments:
    overview_prospects = overview_prospects[overview_prospects["segment"].isin(selected_segments)].copy()
overview_ready = overview_prospects[
    ~overview_prospects["is_duplicate"]
    & overview_prospects["email_valid"]
    & overview_prospects["domain_valid"]
]
overview_scored = score_prospects(
    overview_prospects,
    {"fit": 40, "intent": 30, "signal_quality": 20, "data_confidence": 10},
)
overview_routing_candidates = overview_scored[overview_scored["review_status"].eq("Approved")].copy()
overview_routed = route_leads(overview_routing_candidates, rep_capacity)
overview_sla, _ = sla_summary(filtered_leads, target_hours=24)
lead_to_opportunity_rate = (
    filtered_leads["opportunity_date"].notna().mean() * 100 if len(filtered_leads) else 0
)

tabs = st.tabs(
    [
        "Executive Overview",
        "GTM Funnel & Sources",
        "GTM Operations",
        "Pipeline Health",
    ]
)

with tabs[0]:
    section_header(
        "Executive Overview",
        "End-to-end health of demand conversion, prospect readiness, routing, and revenue pipeline.",
    )

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Lead-to-Opportunity Rate", f"{lead_to_opportunity_rate:.1f}%")
    col2.metric("CRM-Ready Prospects", f"{len(overview_ready):,}")
    col3.metric("Prospects Assigned", f"{overview_routed['routing_status'].eq('Assigned').sum():,}")
    col4.metric("Open Pipeline", money(coverage["open_pipeline"]))

    assigned_count = int(overview_routed["routing_status"].eq("Assigned").sum())
    operating_stages = [
        ("Demand", f"{len(filtered_leads):,} leads"),
        ("CRM Validation", f"{len(overview_ready):,} ready"),
        ("Human Review", f"{len(overview_routing_candidates):,} approved"),
        ("Lead Routing", f"{assigned_count:,} assigned"),
        ("Pipeline", money(coverage["open_pipeline"])),
    ]
    show_chart(operating_flow_chart(operating_stages), use_container_width=True)
    st.caption(
        "The operating flow summarizes connected processes. Stage values come from separate synthetic "
        "lead, prospect, routing, and opportunity datasets and are not a single conversion cohort."
    )

    operational_exceptions = pd.DataFrame(
        {
            "exception_type": [
                "MQLs not contacted",
                "Prospects failing validation",
                "Unassigned prospects",
            ],
            "record_count": [
                int(overview_sla["awaiting_follow_up"]),
                len(overview_prospects) - len(overview_ready),
                int(overview_routed["routing_status"].eq("Unassigned").sum()),
            ],
        }
    )
    show_chart(
        bar_chart(
            operational_exceptions,
            "exception_type",
            "record_count",
            title="Operational Exceptions Requiring Attention",
            height=280,
        ),
        use_container_width=True,
    )

    insight(
        f"{len(overview_ready):,} prospects are validated for CRM delivery, "
        f"{assigned_count:,} are assigned, and "
        f"open pipeline totals {money(coverage['open_pipeline'])}."
    )

with tabs[1]:
    section_header(
        "GTM Funnel & Acquisition Sources",
        "How demand moves from lead to customer, which sources create revenue, and whether sales follows up on MQLs quickly.",
    )

    funnel = gtm_funnel(filtered_leads)
    source_results = source_performance(filtered)
    sla, _ = sla_summary(filtered_leads, target_hours=24)

    sla1, sla2, sla3 = st.columns(3)
    sla1.metric(
        "Contacted Within 24 Hours",
        f"{sla['within_sla_pct']:.1f}%",
    )
    sla2.metric("Median Response Time", f"{sla['median_response_hours']:.1f} hrs")
    sla3.metric(
        "MQLs Not Yet Contacted",
        f"{int(sla['awaiting_follow_up']):,}",
    )

    left, right = st.columns(2)
    with left:
        funnel_fig = px.funnel(
            funnel,
            x="record_count",
            y="lifecycle_stage",
            title="Lead-to-Customer Funnel",
            custom_data=["conversion_from_prior_pct"],
            labels={"record_count": "Records", "lifecycle_stage": "Lifecycle Stage"},
        )
        funnel_fig.update_traces(
            texttemplate="%{value:,} records<br>%{customdata[0]:.1f}% of previous stage"
        )
        funnel_fig.update_layout(height=430, margin=dict(l=20, r=20, t=50, b=20))
        show_chart(funnel_fig, use_container_width=True)
    with right:
        source_long = source_results.melt(
            id_vars="acquisition_source",
            value_vars=["pipeline_generated", "closed_won_revenue"],
            var_name="revenue_type",
            value_name="amount",
        )
        source_long["revenue_type"] = source_long["revenue_type"].map(
            {"pipeline_generated": "Pipeline generated", "closed_won_revenue": "Closed-won revenue"}
        )
        show_chart(
            bar_chart(
                source_long,
                "acquisition_source",
                "amount",
                color="revenue_type",
                title="Pipeline and Revenue by Acquisition Source",
            ),
            use_container_width=True,
        )

    st.markdown("**Acquisition Source Performance**")
    friendly_dataframe(
        source_results,
        use_container_width=True,
        hide_index=True,
        column_config={
            "acquisition_source": "Acquisition source",
            "pipeline_generated": st.column_config.NumberColumn("Pipeline generated", format="$%d"),
            "closed_won_revenue": st.column_config.NumberColumn("Closed-won revenue", format="$%d"),
            "opportunity_count": "Opportunities",
            "revenue_conversion_pct": st.column_config.NumberColumn("Revenue conversion", format="%.1f%%"),
        },
    )

    st.caption(
        "This section summarizes marketing-to-sales response performance. "
        "Record-level assignment exceptions are managed in GTM Operations > Lead Routing."
    )

with tabs[2]:
    section_header(
        "GTM Operations",
        "Operational controls for enrichment, scoring review, and routing.",
    )

    enrichment_view, scoring_view, routing_view = st.tabs(
        [
            "1. Prospecting & Enrichment",
            "2. Scoring & Review",
            "3. Lead Routing",
        ]
    )

    default_weights = {"fit": 40, "intent": 30, "signal_quality": 20, "data_confidence": 10}
    default_scored = score_prospects(prospects, default_weights)
    routing_candidates = default_scored[default_scored["review_status"].eq("Approved")].copy()
    routed = route_leads(routing_candidates, rep_capacity)
    routing_sla_breach = routed[
        routed["routing_status"].eq("Unassigned")
        & (routed["received_at"] < pd.Timestamp.now() - pd.Timedelta(hours=24))
    ]

    with routing_view:
        route1, route2, route3, route4 = st.columns(4)
        route1.metric("Assigned Leads", f"{routed['routing_status'].eq('Assigned').sum():,}")
        route2.metric("Unassigned Queue", f"{routed['routing_status'].eq('Unassigned').sum():,}")
        route3.metric("Routing SLA Breaches", f"{len(routing_sla_breach):,}")
        route4.metric("Reps Accepting New Leads", f"{rep_capacity['available'].sum():,}")

        st.markdown(
            "**Routing criteria:** Approved review decision → valid email and domain → no duplicate → "
            "territory and segment match → rep accepting new leads → remaining capacity → round-robin assignment."
        )

        st.markdown("**Unassigned Lead Queue**")
        friendly_dataframe(
            routed[routed["routing_status"].eq("Unassigned")][
                [
                    "prospect_id",
                    "account_name",
                    "segment",
                    "territory",
                    "received_at",
                ]
            ].sort_values("received_at"),
            use_container_width=True,
            hide_index=True,
        )

        st.markdown("**Rep Capacity and Availability**")
        friendly_dataframe(
            rep_capacity,
            use_container_width=True,
            hide_index=True,
            column_config={"available": "Accepting New Leads"},
        )

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

        provider_quality = prospects.assign(
            fresh_record=prospects["source_updated_at"] >= stale_cutoff,
        ).groupby("source_provider", as_index=False).agg(
            records=("prospect_id", "count"),
            valid_email_rate=("email_valid", "mean"),
            valid_domain_rate=("domain_valid", "mean"),
            duplicate_rate=("is_duplicate", "mean"),
            fresh_record_rate=("fresh_record", "mean"),
            average_confidence=("source_confidence", "mean"),
        )
        for column in ["valid_email_rate", "valid_domain_rate", "duplicate_rate", "fresh_record_rate", "average_confidence"]:
            provider_quality[column] = (provider_quality[column] * 100).round(1)
        st.markdown("**Provider Data Quality**")
        friendly_dataframe(
            provider_quality,
            use_container_width=True,
            hide_index=True,
            column_config={column: st.column_config.NumberColumn(friendly_column_name(column), format="%.1f%%") for column in [
                "valid_email_rate", "valid_domain_rate", "duplicate_rate", "fresh_record_rate", "average_confidence"
            ]},
        )

        st.markdown("**Validated and Enriched Prospects Ready for CRM**")
        enrichment_display = prospects[
            ~prospects["is_duplicate"] & prospects["email_valid"] & prospects["domain_valid"]
        ].copy()
        enrichment_display["source_confidence_pct"] = enrichment_display["source_confidence"] * 100
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
                    "source_confidence_pct",
                    "source_updated_at",
                ]
            ].head(100),
            use_container_width=True,
            hide_index=True,
            column_config={
                "source_confidence_pct": st.column_config.NumberColumn("Source confidence", format="%.0f%%"),
                "website_visits_30d": "Website Visits (30 Days)",
                "content_engagements_30d": "Content Engagements (30 Days)",
                "pricing_page_views_30d": "Pricing Page Views (30 Days)",
            },
        )

    with scoring_view:
        st.caption("Adjust the component weights. Scores are recalculated immediately and normalized to 100%. The attributes in parentheses are the score inputs.")
        weight1, weight2, weight3, weight4 = st.columns(4)
        fit_weight = weight1.slider("Fit (segment, size, role)", 0, 100, 40, 5)
        intent_weight = weight2.slider("Intent (visits, content, pricing)", 0, 100, 30, 5)
        signal_weight = weight3.slider("Signal quality (recency, corroboration, source)", 0, 100, 20, 5)
        confidence_weight = weight4.slider("Data confidence (email, domain, freshness)", 0, 100, 10, 5)
        scored = score_prospects(
            prospects,
            {
                "fit": fit_weight,
                "intent": intent_weight,
                "signal_quality": signal_weight,
                "data_confidence": confidence_weight,
            },
        )

        score_summary = pd.DataFrame(
            {
                "score_component": ["Fit", "Intent", "Signal quality", "Data confidence", "Weighted total"],
                "average_score": [
                    scored["fit_score"].mean(),
                    scored["intent_score"].mean(),
                    scored["signal_quality_score"].mean(),
                    scored["data_confidence_score"].mean(),
                    scored["total_score"].mean(),
                ],
            }
        )
        show_chart(
            bar_chart(score_summary, "score_component", "average_score", title="Average Score by Component"),
            use_container_width=True,
        )

        st.markdown("**Human Review Gate**")
        review_candidates = scored.sort_values("total_score", ascending=False).head(40)[
            [
                "prospect_id",
                "account_name",
                "segment",
                "fit_score",
                "intent_score",
                "signal_quality_score",
                "data_confidence_score",
                "total_score",
                "review_status",
                "reviewer_reason",
            ]
        ]
        edited_reviews = friendly_data_editor(
            review_candidates,
            use_container_width=True,
            hide_index=True,
            disabled=[
                "prospect_id",
                "account_name",
                "segment",
                "fit_score",
                "intent_score",
                "signal_quality_score",
                "data_confidence_score",
                "total_score",
            ],
            column_config={
                "review_status": st.column_config.SelectboxColumn("Decision", options=REVIEW_STATUSES),
                "reviewer_reason": st.column_config.SelectboxColumn("Reason code", options=REVIEW_REASONS),
                "total_score": st.column_config.NumberColumn("Weighted score", format="%.1f"),
            },
            key="review_gate",
        )

with tabs[3]:
    section_header(
        "Pipeline Health",
        "Where open pipeline sits, its expected value after stage probability, and which deals are aging.",
    )

    stage_pipeline = (
        filtered_open.groupby("stage", as_index=False)[["deal_amount", "weighted_pipeline"]]
        .sum()
        .sort_values("stage", key=lambda values: values.map({stage: i for i, stage in enumerate(OPEN_STAGES)}))
    )
    risk_summary = (
        filtered_open.groupby("ai_risk_level", as_index=False)
        .agg(deal_count=("deal_id", "count"), pipeline_value=("deal_amount", "sum"))
        .rename(columns={"ai_risk_level": "deal_risk_level"})
    )
    risk_order = {"Low": 0, "Medium": 1, "High": 2}
    risk_summary["risk_order"] = risk_summary["deal_risk_level"].map(risk_order)
    risk_summary = risk_summary.sort_values("risk_order")

    st.markdown(
        "**Deal Risk Level criteria:** Deal notes, stage age, recent activity, expected close date, "
        "and forecast category."
    )
    left, right = st.columns(2)
    with left:
        if stage_pipeline.empty:
            st.warning("No open pipeline matches the selected filters.")
        else:
            expected_stage_pipeline = stage_pipeline.rename(
                columns={"weighted_pipeline": "expected_pipeline_value"}
            )
            show_chart(
                bar_chart(
                    expected_stage_pipeline,
                    "stage",
                    "expected_pipeline_value",
                    title="Expected Pipeline Value by Stage",
                ),
                use_container_width=True,
            )
    with right:
        if risk_summary.empty:
            st.warning("No open deals are available for risk review under the selected filters.")
        else:
            show_chart(
                bar_chart(
                    risk_summary,
                    "deal_risk_level",
                    "pipeline_value",
                    title="Open Pipeline by Deal Risk Level",
                ),
                use_container_width=True,
            )

    aged = stale_deals(filtered, min_days=45)
    aged_value = aged["deal_amount"].sum()
    insight(f"{money(aged_value)} in open pipeline has been in its current stage for 45+ days.")

    st.markdown("**Forecast Category Legend**")
    legend_columns = st.columns(5)
    legend_items = [
        ("Pipeline", "Active deal; close evidence is incomplete"),
        ("Best Case", "Could close this period; a material dependency remains"),
        ("Commit", "Customer-confirmed next step supports closing this period"),
        ("Closed", "Opportunity is already Closed Won"),
        ("Omitted", "Excluded because it is lost or not forecastable"),
    ]
    for column, (category, definition) in zip(legend_columns, legend_items):
        column.markdown(f"**{category}**  \n{definition}")

    friendly_dataframe(
        aged[
            [
                "deal_id",
                "account_name",
                "rep_name",
                "segment",
                "stage",
                "forecast_category",
                "deal_amount",
                "days_in_current_stage",
                "last_activity_date",
            ]
        ].head(20),
        use_container_width=True,
        hide_index=True,
    )

