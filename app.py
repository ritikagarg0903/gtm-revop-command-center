from __future__ import annotations

from pathlib import Path

import pandas as pd
import plotly.express as px
import streamlit as st

from src.generate_data import write_data
from src.metrics import (
    OPEN_STAGES,
    filter_deals,
    open_deals,
    pipeline_coverage,
    quota_attainment,
    sales_cycle_days,
    stale_deals,
    win_rate,
)
from src.risk_scoring import add_risk_scores


PROJECT_ROOT = Path(__file__).resolve().parent
DATA_DIR = PROJECT_ROOT / "data"
DEALS_PATH = DATA_DIR / "synthetic_deals.csv"
QUOTAS_PATH = DATA_DIR / "rep_quotas.csv"


st.set_page_config(
    page_title="Revenue Operations Command Center",
    page_icon=":bar_chart:",
    layout="wide",
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
def load_data() -> tuple[pd.DataFrame, pd.DataFrame]:
    if not DEALS_PATH.exists() or not QUOTAS_PATH.exists():
        write_data(DATA_DIR)

    deals = pd.read_csv(DEALS_PATH)
    quotas = pd.read_csv(QUOTAS_PATH)

    date_columns = ["created_date", "expected_close_date", "actual_close_date", "last_activity_date"]
    for column in date_columns:
        deals[column] = pd.to_datetime(deals[column], errors="coerce")

    deals = add_risk_scores(deals)
    return deals, quotas


def section_header(title: str, caption: str) -> None:
    st.subheader(title)
    st.caption(caption)


def insight(text: str) -> None:
    st.info(text)


def bar_chart(df: pd.DataFrame, x: str, y: str, color: str | None = None, title: str | None = None):
    fig = px.bar(df, x=x, y=y, color=color, title=title, text_auto=".2s")
    fig.update_layout(margin=dict(l=20, r=20, t=50, b=20), height=390)
    return fig


deals, quotas = load_data()

st.title("Revenue Operations Command Center")
st.caption(
    "A revenue operations view of pipeline coverage, deal health, rep performance, "
    "and the actions managers should prioritize."
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
                {"deal_amount": "Open pipeline", "weighted_pipeline": "Weighted pipeline"}
            )
            st.plotly_chart(
                bar_chart(
                    stage_long,
                    "stage",
                    "pipeline_value",
                    color="pipeline_type",
                    title="Open and Weighted Pipeline by Stage",
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
            bar_chart(forecast_watch, "risk_indicator", "pipeline_value", title="Commit Forecast Risk"),
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
        "Pipeline Health",
        "Where pipeline dollars sit, how much is weighted, and which deals are aging.",
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
            st.plotly_chart(
                bar_chart(stage_pipeline, "stage", "weighted_pipeline", title="Weighted Pipeline by Stage"),
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

    st.dataframe(
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

    st.markdown("**Largest High-Risk Opportunities**")
    st.dataframe(
        high_risk[
            [
                "deal_id",
                "account_name",
                "rep_name",
                "stage",
                "forecast_category",
                "deal_amount",
                "days_in_current_stage",
                "ai_risk_reason",
            ]
        ].sort_values("deal_amount", ascending=False).head(15),
        use_container_width=True,
        hide_index=True,
        column_config={
            "ai_risk_reason": "Risk reason",
            "deal_amount": st.column_config.NumberColumn("Deal amount", format="$%d"),
        },
    )

with tabs[2]:
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

    left, right = st.columns(2)
    with left:
        if rep_table["attainment_pct"].sum() == 0:
            st.warning("No closed-won revenue is available for quota attainment in the selected period.")
        else:
            st.plotly_chart(
                bar_chart(rep_table, "rep_name", "attainment_pct", title="Quota Attainment by Rep"),
                use_container_width=True,
            )
    with right:
        if rep_table["win_rate"].sum() == 0:
            st.warning("No closed won/lost outcomes are available for win-rate comparison in the selected period.")
        else:
            st.plotly_chart(
                bar_chart(rep_table, "rep_name", "win_rate", title="Win Rate by Rep"),
                use_container_width=True,
            )

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
    st.dataframe(display, use_container_width=True, hide_index=True)

with tabs[3]:
    section_header(
        "Manager Action Queue",
        "Prioritized opportunities that need validation, escalation, or a clear next step.",
    )

    risk_rep = (
        filtered_open[filtered_open["ai_risk_level"] == "High"]
        .groupby("rep_name", as_index=False)["deal_amount"]
        .sum()
        .sort_values("deal_amount", ascending=False)
    )

    if risk_rep.empty:
        st.warning("No high-risk open deals are available under the selected filters.")
    else:
        st.plotly_chart(
            bar_chart(risk_rep, "rep_name", "deal_amount", title="High-Risk Pipeline by Owner"),
            use_container_width=True,
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

    action_queue = filtered_open[filtered_open["ai_risk_level"].isin(["High", "Medium"])].copy()
    action_queue["risk_priority"] = action_queue["ai_risk_level"].map({"High": 0, "Medium": 1})
    action_queue = action_queue.sort_values(["risk_priority", "deal_amount"], ascending=[True, False])

    st.dataframe(
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

