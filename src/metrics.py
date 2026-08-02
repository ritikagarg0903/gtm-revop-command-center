from __future__ import annotations

import pandas as pd


CLOSED_STAGES = ["Closed Won", "Closed Lost"]
OPEN_STAGES = ["Prospecting", "Qualified", "Proposal", "Negotiation"]
STAGE_ORDER = ["Prospecting", "Qualified", "Proposal", "Negotiation", "Closed Won", "Closed Lost"]


def open_deals(deals: pd.DataFrame) -> pd.DataFrame:
    return deals[~deals["stage"].isin(CLOSED_STAGES)].copy()


def closed_won(deals: pd.DataFrame) -> pd.DataFrame:
    return deals[deals["stage"] == "Closed Won"].copy()


def closed_deals(deals: pd.DataFrame) -> pd.DataFrame:
    return deals[deals["stage"].isin(CLOSED_STAGES)].copy()


def sales_cycle_days(deals: pd.DataFrame) -> pd.Series:
    created = pd.to_datetime(deals["created_date"], errors="coerce")
    closed = pd.to_datetime(deals["actual_close_date"], errors="coerce")
    return (closed - created).dt.days


def win_rate(deals: pd.DataFrame, group_by: str | None = None) -> pd.DataFrame | float:
    closed = closed_deals(deals)
    if closed.empty:
        return 0.0 if group_by is None else pd.DataFrame(columns=[group_by, "win_rate"])
    if group_by is None:
        return (closed["stage"].eq("Closed Won").mean() * 100).round(1)
    result = closed.groupby(group_by)["stage"].apply(lambda values: values.eq("Closed Won").mean() * 100)
    return result.round(1).reset_index(name="win_rate")


def quota_attainment(deals: pd.DataFrame, quotas: pd.DataFrame, quarter: str) -> pd.DataFrame:
    won = closed_won(deals)
    won_revenue = won.groupby("rep_name", as_index=False)["deal_amount"].sum().rename(columns={"deal_amount": "closed_won_revenue"})
    quota = quotas[quotas["quarter"] == quarter].copy()
    result = quota.merge(won_revenue, on="rep_name", how="left")
    result["closed_won_revenue"] = result["closed_won_revenue"].fillna(0)
    result["attainment_pct"] = (result["closed_won_revenue"] / result["quota"] * 100).round(1)
    result["quota_gap"] = (result["quota"] - result["closed_won_revenue"]).clip(lower=0)
    return result.sort_values("attainment_pct", ascending=False)


def pipeline_coverage(deals: pd.DataFrame, attainment: pd.DataFrame) -> dict[str, float]:
    open_pipeline = open_deals(deals)["deal_amount"].sum()
    weighted_pipeline = open_deals(deals)["weighted_pipeline"].sum()
    remaining_gap = attainment["quota_gap"].sum()
    if remaining_gap <= 0:
        raw_coverage = 0.0
        weighted_coverage = 0.0
    else:
        raw_coverage = open_pipeline / remaining_gap
        weighted_coverage = weighted_pipeline / remaining_gap
    return {
        "open_pipeline": float(open_pipeline),
        "weighted_pipeline": float(weighted_pipeline),
        "remaining_quota_gap": float(remaining_gap),
        "pipeline_coverage": round(raw_coverage, 2),
        "weighted_coverage": round(weighted_coverage, 2),
    }


def forecast_accuracy(deals: pd.DataFrame) -> pd.DataFrame:
    commit = deals[deals["forecast_category"] == "Commit"].copy()
    if commit.empty:
        return pd.DataFrame(columns=["rep_name", "committed_pipeline", "actual_closed_won", "accuracy_pct"])
    committed = commit.groupby("rep_name", as_index=False)["deal_amount"].sum().rename(columns={"deal_amount": "committed_pipeline"})
    won_commit = commit[commit["stage"] == "Closed Won"].groupby("rep_name", as_index=False)["deal_amount"].sum()
    won_commit = won_commit.rename(columns={"deal_amount": "actual_closed_won"})
    result = committed.merge(won_commit, on="rep_name", how="left")
    result["actual_closed_won"] = result["actual_closed_won"].fillna(0)
    result["accuracy_pct"] = (result["actual_closed_won"] / result["committed_pipeline"] * 100).round(1)
    result["forecast_gap"] = result["committed_pipeline"] - result["actual_closed_won"]
    return result.sort_values("accuracy_pct", ascending=False)


def stage_conversion(deals: pd.DataFrame) -> pd.DataFrame:
    counts = deals["stage"].value_counts().reindex(STAGE_ORDER, fill_value=0).reset_index()
    counts.columns = ["stage", "deal_count"]
    counts["next_stage_count"] = counts["deal_count"].shift(-1)
    counts["conversion_to_next_pct"] = (counts["next_stage_count"] / counts["deal_count"] * 100).round(1)
    counts.loc[counts["stage"].isin(["Closed Won", "Closed Lost"]), "conversion_to_next_pct"] = None
    return counts


def stale_deals(deals: pd.DataFrame, min_days: int = 45) -> pd.DataFrame:
    open_pipeline = open_deals(deals)
    return open_pipeline[open_pipeline["days_in_current_stage"] >= min_days].sort_values(
        ["days_in_current_stage", "deal_amount"], ascending=[False, False]
    )


def filter_deals(deals: pd.DataFrame, quarter: str, segments: list[str], reps: list[str], categories: list[str]) -> pd.DataFrame:
    filtered = deals[deals["close_quarter"] == quarter].copy()
    if segments:
        filtered = filtered[filtered["segment"].isin(segments)]
    if reps:
        filtered = filtered[filtered["rep_name"].isin(reps)]
    if categories:
        filtered = filtered[filtered["forecast_category"].isin(categories)]
    return filtered


def gtm_funnel(leads: pd.DataFrame) -> pd.DataFrame:
    stages = [
        ("Lead", "lead_created_date"),
        ("MQL", "mql_date"),
        ("SQL", "sql_date"),
        ("Opportunity", "opportunity_date"),
        ("Customer", "customer_date"),
    ]
    rows = []
    previous_count = None
    for stage, column in stages:
        count = int(pd.to_datetime(leads[column], errors="coerce").notna().sum())
        conversion = 100.0 if previous_count is None else (count / previous_count * 100 if previous_count else 0.0)
        rows.append({"lifecycle_stage": stage, "record_count": count, "conversion_from_prior_pct": round(conversion, 1)})
        previous_count = count
    return pd.DataFrame(rows)


def source_performance(deals: pd.DataFrame) -> pd.DataFrame:
    result = (
        deals.groupby("acquisition_source", as_index=False)
        .agg(
            pipeline_generated=("deal_amount", "sum"),
            opportunity_count=("deal_id", "count"),
            closed_won_revenue=("deal_amount", lambda values: values[deals.loc[values.index, "stage"].eq("Closed Won")].sum()),
        )
    )
    result["revenue_conversion_pct"] = (
        result["closed_won_revenue"] / result["pipeline_generated"] * 100
    ).round(1)
    return result.sort_values("pipeline_generated", ascending=False)


def sla_summary(leads: pd.DataFrame, target_hours: int = 24) -> tuple[dict[str, float], pd.DataFrame]:
    mqls = leads[pd.to_datetime(leads["mql_date"], errors="coerce").notna()].copy()
    mqls["mql_at"] = pd.to_datetime(mqls["mql_date"], errors="coerce")
    mqls["contact_at"] = pd.to_datetime(mqls["first_sales_contact_at"], errors="coerce")
    mqls["response_hours"] = (mqls["contact_at"] - mqls["mql_at"]).dt.total_seconds() / 3600
    mqls["sla_status"] = "Awaiting follow-up"
    mqls.loc[mqls["response_hours"].notna() & (mqls["response_hours"] <= target_hours), "sla_status"] = "Within SLA"
    mqls.loc[mqls["response_hours"] > target_hours, "sla_status"] = "SLA missed"

    contacted = mqls[mqls["response_hours"].notna()]
    summary = {
        "mql_count": float(len(mqls)),
        "within_sla_pct": round((contacted["response_hours"] <= target_hours).mean() * 100, 1) if not contacted.empty else 0.0,
        "median_response_hours": round(float(contacted["response_hours"].median()), 1) if not contacted.empty else 0.0,
        "awaiting_follow_up": float(mqls["contact_at"].isna().sum()),
    }
    return summary, mqls

