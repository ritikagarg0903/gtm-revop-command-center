from __future__ import annotations

import importlib
from pathlib import Path

import pandas as pd
import plotly.express as px
import streamlit as st

from src.gtm_operations import (
    REVIEW_REASONS,
    REVIEW_STATUSES,
    capacity_recommendation,
    experiment_results,
    review_quality,
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
    sales_cycle_days,
    sla_summary,
    source_performance,
    stale_deals,
    win_rate,
)
from src.risk_scoring import add_risk_scores


PROJECT_ROOT = Path(__file__).resolve().parent
DATA_DIR = PROJECT_ROOT / "data"
DEALS_PATH = DATA_DIR / "synthetic_deals.csv"
QUOTAS_PATH = DATA_DIR / "rep_quotas.csv"
LEADS_PATH = DATA_DIR / "synthetic_leads.csv"
PROSPECTS_PATH = DATA_DIR / "synthetic_prospects.csv"
REP_CAPACITY_PATH = DATA_DIR / "rep_capacity.csv"
OUTBOUND_EVENTS_PATH = DATA_DIR / "outbound_events.csv"


st.set_page_config(
    page_title="GTM & Revenue Operations Command Center",
    page_icon=":bar_chart:",
    layout="wide",
)

st.markdown(
    """
    <style>
        .block-container {
            padding-top: 1rem;
            padding-bottom: 1rem;
            max-width: 1500px;
        }
        [data-testid="stHeader"] { height: 2.25rem; }
        h1 { margin-top: 0; margin-bottom: 0.15rem; line-height: 1.15; }
        h2, h3 { margin-top: 0.4rem; margin-bottom: 0.2rem; }
        [data-testid="stMetric"] { padding-top: 0.15rem; padding-bottom: 0.15rem; }
        [data-testid="stCaptionContainer"] { margin-bottom: 0.25rem; }
        .stTabs [data-baseweb="tab-list"] { gap: 0.35rem; }
        .stTabs [data-baseweb="tab"] { padding-top: 0.45rem; padding-bottom: 0.45rem; }
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
def load_data() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    paths = [DEALS_PATH, QUOTAS_PATH, LEADS_PATH, PROSPECTS_PATH, REP_CAPACITY_PATH, OUTBOUND_EVENTS_PATH]
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
    outbound_events = (
        pd.read_csv(OUTBOUND_EVENTS_PATH)
        if OUTBOUND_EVENTS_PATH.exists()
        else data_factory.generate_outbound_events(prospects)
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
    return deals, quotas, leads, prospects, rep_capacity, outbound_events


def section_header(title: str, caption: str) -> None:
    st.subheader(title)
    st.caption(caption)


def insight(text: str) -> None:
    st.info(text)


def bar_chart(
    df: pd.DataFrame,
    x: str,
    y: str,
    color: str | None = None,
    title: str | None = None,
    height: int = 390,
):
    fig = px.bar(df, x=x, y=y, color=color, title=title, text_auto=".2s")
    fig.update_layout(margin=dict(l=20, r=20, t=45, b=15), height=height)
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


deals, quotas, leads, prospects, rep_capacity, outbound_events = load_data()

st.title("GTM & Revenue Operations Command Center")
st.caption(
    "An end-to-end view of demand conversion, acquisition sources, pipeline health, "
    "sales performance, and manager actions."
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
won = filtered[filtered["stage"] == "Closed Won"]
closed = filtered[filtered["stage"].isin(["Closed Won", "Closed Lost"])]
high_risk = filtered_open[filtered_open["ai_risk_level"] == "High"]

tabs = st.tabs(
    [
        "Executive Overview",
        "GTM Funnel & Sources",
        "GTM Operations",
        "Pipeline Health",
        "Rep Performance",
        "Manager Action Queue",
    ]
)

with tabs[0]:
    section_header(
        "Executive Overview",
        "Can the current pipeline close the remaining revenue gap, and how much of it needs attention?",
    )

    col1, col2, col3, col4, col5 = st.columns(5)
    col1.metric(
        "Total Open Deals",
        money(coverage["open_pipeline"]),
        help="Total value of all opportunities that have not been won or lost.",
    )
    col2.metric(
        "Expected Pipeline Value",
        money(coverage["weighted_pipeline"]),
        help="Open pipeline adjusted by each sales stage's probability of closing.",
    )
    col3.metric(
        "Revenue Needed to Hit Quota",
        money(coverage["remaining_quota_gap"]),
        help="Team quota minus revenue already closed won in the selected period.",
    )
    col4.metric(
        "Open Pipeline per $1 Needed",
        f"${coverage['pipeline_coverage']:.2f}",
        help="Open pipeline divided by the revenue still needed to reach quota.",
    )
    col5.metric(
        "Pipeline at High Risk",
        money(high_risk["deal_amount"].sum()),
        help="Value of open opportunities flagged for immediate manager review.",
    )

    if coverage["remaining_quota_gap"] > 0:
        insight(
            f"For every $1 of revenue still needed to reach quota, the team has "
            f"${coverage['pipeline_coverage']:.2f} in open opportunities. After adjusting for the likelihood "
            f"of each sales stage closing, that falls to ${coverage['weighted_coverage']:.2f}."
        )
    else:
        insight("The selected team has already covered quota for this filtered period.")

    overdue_commit = filtered_open[
        (filtered_open["forecast_category"] == "Commit")
        & (pd.to_datetime(filtered_open["expected_close_date"], errors="coerce") < pd.Timestamp.today())
    ]
    risky_commit = filtered_open[
        (filtered_open["forecast_category"] == "Commit")
        & (filtered_open["ai_risk_level"].isin(["High", "Medium"]))
    ]

    left, right = st.columns(2)
    with left:
        stage_pipeline = (
            filtered_open.groupby("stage", as_index=False)[["deal_amount", "weighted_pipeline"]]
            .sum()
            .sort_values("stage", key=lambda values: values.map({stage: i for i, stage in enumerate(OPEN_STAGES)}))
        )
        if stage_pipeline.empty:
            st.warning("No open pipeline matches the selected filters.")
        else:
            stage_long = stage_pipeline.melt(
                id_vars="stage",
                value_vars=["deal_amount", "weighted_pipeline"],
                var_name="pipeline_type",
                value_name="pipeline_value",
            )
            stage_long["pipeline_type"] = stage_long["pipeline_type"].map(
                {"deal_amount": "Total open pipeline", "weighted_pipeline": "Expected pipeline value"}
            )
            st.plotly_chart(
                bar_chart(
                    stage_long,
                    "stage",
                    "pipeline_value",
                    color="pipeline_type",
                    title="Total vs Expected Pipeline Value by Stage",
                    height=300,
                ),
                use_container_width=True,
            )
    with right:
        forecast_watch = pd.DataFrame(
            {
                "risk_indicator": ["Past-due Commit", "At-risk Commit"],
                "pipeline_value": [overdue_commit["deal_amount"].sum(), risky_commit["deal_amount"].sum()],
            }
        )
        st.plotly_chart(
            bar_chart(
                forecast_watch,
                "risk_indicator",
                "pipeline_value",
                title="Commit Forecast Risk",
                height=300,
            ),
            use_container_width=True,
        )

    if not overdue_commit.empty or not risky_commit.empty:
        insight(
            f"{money(overdue_commit['deal_amount'].sum())} in Commit is past its expected close date and "
            f"{money(risky_commit['deal_amount'].sum())} is rated medium or high risk. "
            "These deals should be revalidated before the next forecast call."
        )

with tabs[1]:
    section_header(
        "GTM Funnel & Acquisition Sources",
        "How demand moves from lead to customer, which sources create revenue, and whether sales follows up on MQLs quickly.",
    )

    funnel = gtm_funnel(filtered_leads)
    source_results = source_performance(filtered)
    sla, sla_details = sla_summary(filtered_leads, target_hours=24)

    sla1, sla2, sla3, sla4 = st.columns(4)
    sla1.metric("MQLs Created", f"{int(sla['mql_count']):,}")
    sla2.metric(
        "Contacted Within 24 Hours",
        f"{sla['within_sla_pct']:.1f}%",
        help="Share of contacted MQLs receiving their first sales touch within 24 hours.",
    )
    sla3.metric("Median Response Time", f"{sla['median_response_hours']:.1f} hrs")
    sla4.metric("Awaiting Sales Follow-up", f"{int(sla['awaiting_follow_up']):,}")

    left, right = st.columns(2)
    with left:
        funnel_fig = px.funnel(
            funnel,
            x="record_count",
            y="lifecycle_stage",
            title="Lead-to-Customer Funnel",
            custom_data=["conversion_from_prior_pct"],
        )
        funnel_fig.update_traces(
            texttemplate="%{value:,} records<br>%{customdata[0]:.1f}% of previous stage"
        )
        funnel_fig.update_layout(height=430, margin=dict(l=20, r=20, t=50, b=20))
        st.plotly_chart(funnel_fig, use_container_width=True)
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
        st.plotly_chart(
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

    sla_exceptions = sla_details[sla_details["sla_status"] != "Within SLA"].copy()
    st.markdown("**Marketing-to-Sales SLA Exceptions**")
    friendly_dataframe(
        sla_exceptions[
            [
                "lead_id",
                "acquisition_source",
                "segment",
                "owner_name",
                "mql_date",
                "first_sales_contact_at",
                "response_hours",
                "sla_status",
            ]
        ].sort_values(["sla_status", "response_hours"], ascending=[True, False]),
        use_container_width=True,
        hide_index=True,
        column_config={
            "response_hours": st.column_config.NumberColumn("Response hours", format="%.1f"),
            "sla_status": "SLA status",
        },
    )

with tabs[2]:
    section_header(
        "GTM Operations",
        "Operational controls for enrichment, routing, scoring review, and outbound experimentation.",
    )

    routing_view, enrichment_view, scoring_view, experiment_view = st.tabs(
        ["Lead Routing", "Prospecting & Enrichment", "Scoring Review", "Outbound Experiments"]
    )

    default_weights = {"fit": 40, "intent": 30, "signal_quality": 20, "data_confidence": 10}
    default_scored = score_prospects(prospects, default_weights)
    routed = route_leads(default_scored, rep_capacity)
    routing_sla_breach = routed[
        routed["routing_status"].eq("Unassigned")
        & (routed["received_at"] < pd.Timestamp.now() - pd.Timedelta(hours=24))
    ]

    with routing_view:
        route1, route2, route3, route4 = st.columns(4)
        route1.metric("Assigned Leads", f"{routed['routing_status'].eq('Assigned').sum():,}")
        route2.metric("Unassigned Queue", f"{routed['routing_status'].eq('Unassigned').sum():,}")
        route3.metric("Routing SLA Breaches", f"{len(routing_sla_breach):,}")
        route4.metric("Available Reps", f"{rep_capacity['available'].sum():,}")

        st.markdown("**Unassigned and SLA-Breach Queue**")
        friendly_dataframe(
            routed[routed["routing_status"].eq("Unassigned")][
                [
                    "prospect_id",
                    "account_name",
                    "segment",
                    "territory",
                    "review_status",
                    "received_at",
                    "routing_reason",
                ]
            ].sort_values("received_at"),
            use_container_width=True,
            hide_index=True,
            column_config={"routing_reason": "Why it was not assigned"},
        )

        st.markdown("**Recent Explainable Assignments**")
        friendly_dataframe(
            routed[routed["routing_status"].eq("Assigned")][
                ["prospect_id", "account_name", "segment", "territory", "routed_rep", "routing_reason"]
            ].head(30),
            use_container_width=True,
            hide_index=True,
            column_config={"routing_reason": "Routing explanation"},
        )

        st.markdown("**Rep Capacity and Availability**")
        friendly_dataframe(rep_capacity, use_container_width=True, hide_index=True)

    with enrichment_view:
        stale_cutoff = pd.Timestamp.now() - pd.Timedelta(days=30)
        enrich1, enrich2, enrich3, enrich4 = st.columns(4)
        enrich1.metric("Canonical Prospects", f"{len(prospects):,}")
        enrich2.metric("Valid Email Rate", f"{prospects['email_valid'].mean() * 100:.1f}%")
        enrich3.metric("Duplicates Blocked", f"{prospects['is_duplicate'].sum():,}")
        enrich4.metric("Records Older Than 30 Days", f"{(prospects['source_updated_at'] < stale_cutoff).sum():,}")

        provider_counts = prospects.groupby("source_provider", as_index=False).agg(
            records=("prospect_id", "count"),
            average_confidence=("source_confidence", "mean"),
        )
        provider_counts["average_confidence"] = (provider_counts["average_confidence"] * 100).round(1)
        st.plotly_chart(
            bar_chart(provider_counts, "source_provider", "records", title="Canonical Records by Provider"),
            use_container_width=True,
        )

        st.markdown("**Canonical Account and Contact Records**")
        enrichment_display = prospects.copy()
        enrichment_display["source_confidence_pct"] = enrichment_display["source_confidence"] * 100
        friendly_dataframe(
            enrichment_display[
                [
                    "prospect_id",
                    "account_name",
                    "canonical_domain",
                    "contact_name",
                    "canonical_email",
                    "email_valid",
                    "domain_valid",
                    "source_provider",
                    "source_confidence_pct",
                    "source_updated_at",
                    "is_duplicate",
                    "duplicate_of",
                    "field_lineage",
                ]
            ].head(100),
            use_container_width=True,
            hide_index=True,
            column_config={
                "source_confidence_pct": st.column_config.NumberColumn("Source confidence", format="%.0f%%"),
                "field_lineage": "Field-level source lineage",
            },
        )

    with scoring_view:
        st.caption("Adjust the component weights. Scores are recalculated immediately and normalized to 100%.")
        weight1, weight2, weight3, weight4 = st.columns(4)
        fit_weight = weight1.slider("Fit weight", 0, 100, 40, 5)
        intent_weight = weight2.slider("Intent weight", 0, 100, 30, 5)
        signal_weight = weight3.slider("Signal-quality weight", 0, 100, 20, 5)
        confidence_weight = weight4.slider("Data-confidence weight", 0, 100, 10, 5)
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
        st.plotly_chart(
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
        review_evaluation = scored.copy().set_index("prospect_id")
        edited_index = edited_reviews.set_index("prospect_id")
        review_evaluation.loc[edited_index.index, ["review_status", "reviewer_reason"]] = edited_index[
            ["review_status", "reviewer_reason"]
        ]
        review_evaluation = review_evaluation.reset_index()
        quality = review_quality(review_evaluation)
        quality1, quality2, quality3 = st.columns(3)
        quality1.metric("Reviewed Prospects", f"{int(quality['reviewed']):,}")
        quality2.metric(
            "False-Positive Rate",
            f"{quality['false_positive_pct']:.1f}%",
            help="Approved prospects that did not become opportunities in the synthetic outcome data.",
        )
        quality3.metric(
            "False-Negative Rate",
            f"{quality['false_negative_pct']:.1f}%",
            help="Rejected prospects that later became opportunities in the synthetic outcome data.",
        )

    with experiment_view:
        results = experiment_results(outbound_events)
        recommendation = capacity_recommendation(results)
        total_sent = int(results["sample_size"].sum())
        total_delivered = int(results["delivered"].sum())
        total_positive = int(results["positive_replies"].sum())
        total_meetings = int(results["meetings"].sum())
        exp1, exp2, exp3, exp4 = st.columns(4)
        exp1.metric("Messages Sent", f"{total_sent:,}")
        exp2.metric("Delivery Rate", f"{total_delivered / max(total_sent, 1) * 100:.1f}%")
        exp3.metric("Positive Replies", f"{total_positive:,}")
        exp4.metric("Meetings Booked", f"{total_meetings:,}")

        results["ci_plus"] = results["ci_high_pct"] - results["positive_reply_rate_pct"]
        results["ci_minus"] = results["positive_reply_rate_pct"] - results["ci_low_pct"]
        experiment_fig = px.bar(
            results,
            x="segment",
            y="positive_reply_rate_pct",
            color="message_variant",
            barmode="group",
            error_y="ci_plus",
            error_y_minus="ci_minus",
            title="Positive-Reply Rate by Segment and Message Variant (95% CI)",
            labels={
                "positive_reply_rate_pct": "Positive-reply rate (%)",
                "message_variant": "Message variant",
                "segment": "Segment",
            },
        )
        experiment_fig.update_layout(height=460, margin=dict(l=20, r=20, t=60, b=20))
        st.plotly_chart(experiment_fig, use_container_width=True)
        insight(recommendation)
        friendly_dataframe(
            results[
                [
                    "segment",
                    "message_variant",
                    "sample_size",
                    "delivered",
                    "replied",
                    "positive_replies",
                    "meetings",
                    "positive_reply_rate_pct",
                    "ci_low_pct",
                    "ci_high_pct",
                ]
            ],
            use_container_width=True,
            hide_index=True,
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
    )
    risk_order = {"Low": 0, "Medium": 1, "High": 2}
    risk_summary["risk_order"] = risk_summary["ai_risk_level"].map(risk_order)
    risk_summary = risk_summary.sort_values("risk_order")

    left, right = st.columns(2)
    with left:
        if stage_pipeline.empty:
            st.warning("No open pipeline matches the selected filters.")
        else:
            expected_stage_pipeline = stage_pipeline.rename(
                columns={"weighted_pipeline": "expected_pipeline_value"}
            )
            st.plotly_chart(
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
            st.plotly_chart(
                bar_chart(risk_summary, "ai_risk_level", "pipeline_value", title="Open Pipeline by Risk Level"),
                use_container_width=True,
            )

    aged = stale_deals(filtered, min_days=45)
    aged_value = aged["deal_amount"].sum()
    insight(f"{money(aged_value)} in open pipeline has been in its current stage for 45+ days.")

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

with tabs[4]:
    section_header(
        "Rep Performance",
        "Quota attainment, revenue contribution, win rate, average deal size, and cycle length.",
    )

    rep_attainment = attainment.copy()
    rep_win = win_rate(filtered, "rep_name")
    avg_deal = won.groupby("rep_name", as_index=False)["deal_amount"].mean().rename(columns={"deal_amount": "avg_deal_size"})

    cycles = closed.copy()
    cycles["sales_cycle_days"] = sales_cycle_days(cycles)
    avg_cycle = cycles.groupby("rep_name", as_index=False)["sales_cycle_days"].mean()

    rep_table = (
        rep_attainment.merge(rep_win, on="rep_name", how="left")
        .merge(avg_deal, on="rep_name", how="left")
        .merge(avg_cycle, on="rep_name", how="left")
        .fillna(0)
    )

    if rep_table["attainment_pct"].sum() == 0 and rep_table["win_rate"].sum() == 0:
        st.warning("No closed outcomes are available for rep performance comparison in the selected period.")
    else:
        performance_fig = px.scatter(
            rep_table,
            x="attainment_pct",
            y="win_rate",
            size="closed_won_revenue",
            color="segment_focus",
            text="rep_name",
            title="Quota Attainment vs Win Rate",
            labels={
                "attainment_pct": "Quota attainment (%)",
                "win_rate": "Win rate (%)",
                "closed_won_revenue": "Closed-won revenue",
                "segment_focus": "Segment",
            },
            hover_data={"avg_deal_size": ":$,.0f", "sales_cycle_days": ":.0f"},
        )
        performance_fig.add_vline(
            x=100,
            line_dash="dash",
            line_color="#64748b",
            annotation_text="Quota target",
            annotation_position="top",
        )
        performance_fig.update_traces(textposition="top center")
        performance_fig.update_yaxes(range=[0, 105])
        performance_fig.update_layout(height=500, margin=dict(l=20, r=20, t=60, b=20))
        st.plotly_chart(performance_fig, use_container_width=True)

    top_rep = rep_table.sort_values("attainment_pct", ascending=False).head(1)
    if not top_rep.empty:
        row = top_rep.iloc[0]
        insight(
            f"{row['rep_name']} leads quota attainment at {row['attainment_pct']:.1f}%, "
            f"with {row['win_rate']:.1f}% win rate in the selected period."
        )

    display = rep_table[
        [
            "rep_name",
            "segment_focus",
            "quota",
            "closed_won_revenue",
            "attainment_pct",
            "quota_gap",
            "win_rate",
            "avg_deal_size",
            "sales_cycle_days",
        ]
    ].copy()
    friendly_dataframe(display, use_container_width=True, hide_index=True)

with tabs[5]:
    section_header(
        "Manager Action Queue",
        "Prioritized opportunities that need validation, escalation, or a clear next step.",
    )

    action_queue = filtered_open[filtered_open["ai_risk_level"].isin(["High", "Medium"])].copy()
    action_queue["risk_priority"] = action_queue["ai_risk_level"].map({"High": 0, "Medium": 1})
    action_queue = action_queue.sort_values(["risk_priority", "deal_amount"], ascending=[True, False])

    no_recent_activity = filtered_open[
        pd.to_datetime(filtered_open["last_activity_date"], errors="coerce")
        < (pd.Timestamp.today().normalize() - pd.Timedelta(days=21))
    ]

    metric1, metric2, metric3, metric4 = st.columns(4)
    metric1.metric(
        "Deals Requiring Action",
        f"{len(action_queue):,}",
        help="Open opportunities rated medium or high risk.",
    )
    metric2.metric(
        "Pipeline Requiring Action",
        money(action_queue["deal_amount"].sum()),
        help="Total value of medium- and high-risk open opportunities.",
    )
    metric3.metric(
        "Past-Due Commit Deals",
        f"{len(overdue_commit):,}",
        help="Open Commit opportunities whose expected close date has passed.",
    )
    metric4.metric(
        "No Activity for 21+ Days",
        f"{len(no_recent_activity):,}",
        help="Open opportunities without recorded activity in more than 21 days.",
    )

    if not high_risk.empty:
        largest = high_risk.sort_values("deal_amount", ascending=False).iloc[0]
        insight(
            f"{money(high_risk['deal_amount'].sum())} in open pipeline is high risk. "
            f"The largest flagged deal is {largest['account_name']} at {money(largest['deal_amount'])}: "
            f"{largest['recommended_action']}"
        )
    else:
        insight("No high-risk open deals are present in the selected filters.")

    st.markdown("**Prioritized Opportunities**")
    friendly_dataframe(
        action_queue[
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
                "ai_risk_level",
                "ai_risk_reason",
                "recommended_action",
            ]
        ],
        use_container_width=True,
        hide_index=True,
        column_config={
            "ai_risk_level": "Risk level",
            "ai_risk_reason": "Risk reason",
            "recommended_action": "Manager action",
            "deal_amount": st.column_config.NumberColumn("Deal amount", format="$%d"),
        },
    )

