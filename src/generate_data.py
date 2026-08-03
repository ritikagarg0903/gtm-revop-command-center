from __future__ import annotations

import random
from datetime import date, timedelta
from pathlib import Path

import pandas as pd

from src.gtm_operations import (
    SyntheticCompanyFeedAdapter,
    SyntheticYCAdapter,
    add_canonical_and_duplicate_fields,
    deterministic_variant,
)


random.seed(42)

REPS = [
    "Avery Chen",
    "Jordan Lee",
    "Maya Patel",
    "Noah Brooks",
    "Priya Shah",
    "Sam Rivera",
    "Taylor Morgan",
    "Riley Johnson",
    "Casey Nguyen",
    "Morgan Allen",
    "Jamie Carter",
    "Drew Parker",
]

SEGMENTS = {
    "SMB": {"amount": (8_000, 45_000), "cycle": (20, 55), "quota": (325_000, 475_000)},
    "Mid-Market": {"amount": (35_000, 130_000), "cycle": (45, 95), "quota": (625_000, 850_000)},
    "Enterprise": {"amount": (110_000, 420_000), "cycle": (80, 170), "quota": (950_000, 1_350_000)},
}

STAGES = ["Prospecting", "Qualified", "Proposal", "Negotiation", "Closed Won", "Closed Lost"]
STAGE_PROBABILITIES = {
    "Prospecting": 0.10,
    "Qualified": 0.25,
    "Proposal": 0.50,
    "Negotiation": 0.75,
    "Closed Won": 1.00,
    "Closed Lost": 0.00,
}

ACQUISITION_SOURCES = ["Inbound", "Outbound", "Paid Search", "Events", "Partners", "Referrals"]
SOURCE_WEIGHTS = [30, 25, 14, 10, 12, 9]

RISK_NOTES = [
    "Budget frozen until next quarter; champion says timing is uncertain.",
    "Procurement review delayed and legal has not returned redlines.",
    "Competitor evaluation active; no economic buyer confirmed yet.",
    "Decision maker changed roles and the new sponsor has not been briefed.",
    "Security review is blocked pending customer questionnaire.",
    "No recent activity after proposal was sent.",
]

POSITIVE_NOTES = [
    "Champion identified; executive sponsor joined last call and approved business case.",
    "Procurement started; mutual action plan agreed with close date confirmed.",
    "Technical validation complete and buyer requested final pricing.",
    "Legal review complete; customer asked for order form revisions.",
    "Economic buyer confirmed budget and implementation timeline.",
    "Verbal approval received; waiting on purchase order.",
]

NEUTRAL_NOTES = [
    "Discovery complete; rep is mapping stakeholders and confirming use case.",
    "Demo completed; buyer requested ROI calculator and reference call.",
    "Proposal sent; customer is reviewing internally this week.",
    "Follow-up scheduled with operations lead and finance partner.",
    "Evaluation in progress with two additional departments.",
]

ACCOUNT_PREFIXES = [
    "Northstar",
    "Bluefield",
    "Summit",
    "Riverbend",
    "Cedar",
    "Brightline",
    "Silvergate",
    "Cloudpeak",
    "Horizon",
    "Redwood",
    "Clearwater",
    "Westhaven",
]


def quarter_label(value: date) -> str:
    quarter = ((value.month - 1) // 3) + 1
    return f"{value.year} Q{quarter}"


def choose_stage(created: date, expected_close: date) -> str:
    age = (date.today() - created).days
    days_to_close = (expected_close - date.today()).days

    if days_to_close < -20:
        return random.choices(["Closed Won", "Closed Lost", "Negotiation"], weights=[44, 40, 16])[0]
    if age < 25:
        return random.choices(STAGES[:4], weights=[45, 35, 15, 5])[0]
    if days_to_close < 20:
        return random.choices(STAGES, weights=[5, 13, 26, 32, 13, 11])[0]
    return random.choices(STAGES[:4], weights=[18, 34, 30, 18])[0]


def forecast_category(stage: str) -> str:
    if stage == "Closed Won":
        return "Closed"
    if stage == "Closed Lost":
        return "Omitted"
    if stage == "Negotiation":
        return random.choices(["Commit", "Best Case", "Pipeline"], weights=[48, 38, 14])[0]
    if stage == "Proposal":
        return random.choices(["Best Case", "Pipeline", "Commit"], weights=[45, 43, 12])[0]
    return random.choices(["Pipeline", "Best Case"], weights=[82, 18])[0]


def deal_note(stage: str) -> str:
    if stage in {"Closed Won", "Closed Lost"}:
        return random.choice(POSITIVE_NOTES if stage == "Closed Won" else RISK_NOTES)
    return random.choices(
        [random.choice(POSITIVE_NOTES), random.choice(NEUTRAL_NOTES), random.choice(RISK_NOTES)],
        weights=[35, 38, 27],
    )[0]


def account_name(index: int) -> str:
    suffixes = ["Systems", "Analytics", "Logistics", "Foods", "Health", "Manufacturing", "Services"]
    return f"{random.choice(ACCOUNT_PREFIXES)} {random.choice(suffixes)} {index:03d}"


def generate_deals(row_count: int = 750) -> pd.DataFrame:
    rows = []
    today = date.today()

    for index in range(1, row_count + 1):
        segment = random.choices(list(SEGMENTS), weights=[43, 36, 21])[0]
        segment_config = SEGMENTS[segment]
        rep = random.choice(REPS)
        created = today - timedelta(days=random.randint(5, 300))
        base_cycle = random.randint(*segment_config["cycle"])
        expected_close = created + timedelta(days=base_cycle + random.randint(-12, 35))
        stage = choose_stage(created, expected_close)
        amount = random.randint(*segment_config["amount"])
        amount = int(round(amount / 1_000) * 1_000)

        actual_close = None
        if stage in {"Closed Won", "Closed Lost"}:
            actual_close = expected_close + timedelta(days=random.randint(-15, 28))

        last_activity = today - timedelta(days=random.randint(0, 55))
        days_in_stage = random.randint(3, 85)
        if stage in {"Proposal", "Negotiation"}:
            days_in_stage += random.randint(0, 35)

        category = forecast_category(stage)
        close_basis = actual_close or expected_close
        probability = STAGE_PROBABILITIES[stage]

        rows.append(
            {
                "deal_id": f"D-{index:04d}",
                "account_name": account_name(index),
                "rep_name": rep,
                "segment": segment,
                "acquisition_source": random.choices(ACQUISITION_SOURCES, weights=SOURCE_WEIGHTS)[0],
                "stage": stage,
                "forecast_category": category,
                "deal_amount": amount,
                "stage_probability": probability,
                "weighted_pipeline": round(amount * probability, 2),
                "created_date": created.isoformat(),
                "expected_close_date": expected_close.isoformat(),
                "actual_close_date": actual_close.isoformat() if actual_close else "",
                "close_month": close_basis.strftime("%Y-%m"),
                "close_quarter": quarter_label(close_basis),
                "committed_forecast": "Y" if category == "Commit" else "N",
                "days_in_current_stage": days_in_stage,
                "last_activity_date": last_activity.isoformat(),
                "activity_count": random.randint(1, 42),
                "notes": deal_note(stage),
            }
        )

    return pd.DataFrame(rows)


def generate_leads(deals: pd.DataFrame, row_count: int = 1_800) -> pd.DataFrame:
    """Create lifecycle records so GTM funnel and SLA metrics use real milestones."""
    rows = []
    today = date.today()

    for index, deal in deals.reset_index(drop=True).iterrows():
        opportunity_date = pd.to_datetime(deal["created_date"]).date()
        lead_created = opportunity_date - timedelta(days=random.randint(7, 60))
        mql_date = lead_created + timedelta(days=random.randint(1, 14))
        response_hours = random.choices(
            [random.randint(1, 24), random.randint(25, 72)], weights=[78, 22]
        )[0]
        first_contact = pd.Timestamp(mql_date) + pd.Timedelta(hours=response_hours)
        sales_accepted = first_contact.date()
        sql_date = sales_accepted + timedelta(days=random.randint(1, 8))

        rows.append(
            {
                "lead_id": f"L-{index + 1:05d}",
                "acquisition_source": deal["acquisition_source"],
                "segment": deal["segment"],
                "owner_name": deal["rep_name"],
                "lead_created_date": lead_created.isoformat(),
                "mql_date": mql_date.isoformat(),
                "sales_accepted_date": sales_accepted.isoformat(),
                "first_sales_contact_at": first_contact.isoformat(),
                "sql_date": sql_date.isoformat(),
                "opportunity_date": opportunity_date.isoformat(),
                "opportunity_id": deal["deal_id"],
                "customer_date": deal["actual_close_date"] if deal["stage"] == "Closed Won" else "",
            }
        )

    for index in range(len(rows) + 1, row_count + 1):
        lead_created = today - timedelta(days=random.randint(1, 300))
        lifecycle = random.choices(["Lead", "MQL", "SQL"], weights=[44, 36, 20])[0]
        mql_date = lead_created + timedelta(days=random.randint(1, 18)) if lifecycle != "Lead" else None
        contacted = lifecycle == "SQL" or (lifecycle == "MQL" and random.random() < 0.72)
        first_contact = None
        sales_accepted = None
        if mql_date and contacted:
            response_hours = random.choices(
                [random.randint(1, 24), random.randint(25, 96)], weights=[68, 32]
            )[0]
            first_contact = pd.Timestamp(mql_date) + pd.Timedelta(hours=response_hours)
            sales_accepted = first_contact.date()
        sql_date = first_contact.date() + timedelta(days=random.randint(1, 7)) if lifecycle == "SQL" else None

        rows.append(
            {
                "lead_id": f"L-{index:05d}",
                "acquisition_source": random.choices(ACQUISITION_SOURCES, weights=SOURCE_WEIGHTS)[0],
                "segment": random.choices(list(SEGMENTS), weights=[43, 36, 21])[0],
                "owner_name": random.choice(REPS) if contacted else "",
                "lead_created_date": lead_created.isoformat(),
                "mql_date": mql_date.isoformat() if mql_date else "",
                "sales_accepted_date": sales_accepted.isoformat() if sales_accepted else "",
                "first_sales_contact_at": first_contact.isoformat() if first_contact else "",
                "sql_date": sql_date.isoformat() if sql_date else "",
                "opportunity_date": "",
                "opportunity_id": "",
                "customer_date": "",
            }
        )

    return pd.DataFrame(rows)


def generate_quotas() -> pd.DataFrame:
    rows = []
    quarters = ["2026 Q1", "2026 Q2", "2026 Q3", "2026 Q4"]

    for rep in REPS:
        segment_focus = random.choices(list(SEGMENTS), weights=[30, 45, 25])[0]
        low, high = SEGMENTS[segment_focus]["quota"]
        for quarter in quarters:
            rows.append(
                {
                    "rep_name": rep,
                    "quarter": quarter,
                    "quota": int(round(random.randint(low, high) / 25_000) * 25_000),
                    "segment_focus": segment_focus,
                }
            )

    return pd.DataFrame(rows)


def generate_prospects(row_count: int = 500) -> pd.DataFrame:
    provider_records = SyntheticYCAdapter().fetch(row_count // 2) + SyntheticCompanyFeedAdapter().fetch(
        row_count - row_count // 2
    )
    territories = ["West", "Central", "East", "International"]
    title_options = ["VP Operations", "Head of Revenue", "Director of Sales", "COO", "RevOps Manager"]
    rows = []
    now = pd.Timestamp.now().floor("h")

    for index, provider in enumerate(provider_records, start=1):
        domain = provider.domain
        email_domain = domain
        if index % 23 == 0:
            domain = provider_records[index - 2].domain
            email_domain = domain
        email = f"buyer{index}@{email_domain}"
        if index % 41 == 0:
            email = f"buyer{index}-invalid"

        segment = random.choices(list(SEGMENTS), weights=[43, 36, 21])[0]
        source_updated = now - pd.Timedelta(days=random.randint(0, 90))
        fit_score = random.randint(35, 98)
        intent_score = random.randint(15, 95)
        signal_quality = random.randint(35, 100)
        data_confidence = round(
            min(100, provider.source_confidence * 100 - random.randint(0, 18)), 1
        )
        composite = fit_score * 0.4 + intent_score * 0.3 + signal_quality * 0.2 + data_confidence * 0.1
        review_status = random.choices(
            ["Approved", "Pending", "Hold", "Rejected"],
            weights=[50 if composite >= 70 else 20, 24, 12, 14 if composite >= 70 else 44],
        )[0]
        reason_map = {
            "Approved": random.choice(["Meets ICP", "High intent"]),
            "Pending": "Needs research",
            "Hold": "No current need",
            "Rejected": random.choice(["Outside ICP", "Bad data"]),
        }
        became_opportunity = random.random() < max(0.05, min(0.8, (composite - 25) / 100))

        rows.append(
            {
                "prospect_id": f"P-{index:05d}",
                "account_name": provider.account_name,
                "contact_name": f"Contact {index:03d}",
                "job_title": random.choice(title_options),
                "domain": domain,
                "email": email,
                "segment": segment,
                "territory": random.choice(territories),
                "employee_count": random.randint(25, 5_000),
                "source_provider": provider.source_provider,
                "source_confidence": provider.source_confidence,
                "source_updated_at": source_updated.isoformat(),
                "field_lineage": (
                    f"domain:{provider.source_provider}|email:Enrichment API|"
                    f"segment:Company Feed|intent:Signal Provider"
                ),
                "fit_score": fit_score,
                "intent_score": intent_score,
                "signal_quality_score": signal_quality,
                "data_confidence_score": data_confidence,
                "review_status": review_status,
                "reviewer_reason": reason_map[review_status],
                "became_opportunity": became_opportunity,
                "received_at": (now - pd.Timedelta(hours=random.randint(0, 72))).isoformat(),
            }
        )

    return add_canonical_and_duplicate_fields(pd.DataFrame(rows))


def generate_rep_capacity() -> pd.DataFrame:
    territory_rules = ["West|International", "Central", "East", "West", "Central|East"]
    segment_rules = ["SMB|Mid-Market", "Mid-Market|Enterprise", "SMB", "Enterprise", "SMB|Mid-Market|Enterprise"]
    rows = []
    for index, rep in enumerate(REPS):
        max_capacity = random.randint(18, 35)
        rows.append(
            {
                "rep_name": rep,
                "territories": territory_rules[index % len(territory_rules)],
                "segments": segment_rules[index % len(segment_rules)],
                "max_capacity": max_capacity,
                "current_load": random.randint(8, max_capacity),
                "available": random.random() > 0.12,
            }
        )
    return pd.DataFrame(rows)


def generate_outbound_events(prospects: pd.DataFrame, row_count: int = 700) -> pd.DataFrame:
    variants = ["Pain-led", "Benchmark-led", "Outcome-led"]
    segment_positive_rate = {"SMB": 0.055, "Mid-Market": 0.09, "Enterprise": 0.125}
    variant_lift = {"Pain-led": 0.0, "Benchmark-led": 0.018, "Outcome-led": 0.032}
    rows = []

    sample = prospects[~prospects["is_duplicate"]].head(row_count)
    for _, prospect in sample.iterrows():
        variant = deterministic_variant(prospect["prospect_id"], variants)
        delivered = random.random() < 0.94
        reply_rate = 0.16 if delivered else 0
        replied = delivered and random.random() < reply_rate
        positive_rate = segment_positive_rate[prospect["segment"]] + variant_lift[variant]
        positive = replied and random.random() < min(0.9, positive_rate / reply_rate)
        meeting = positive and random.random() < 0.58
        rows.append(
            {
                "prospect_id": prospect["prospect_id"],
                "segment": prospect["segment"],
                "message_variant": variant,
                "sent": 1,
                "delivered": int(delivered),
                "replied": int(replied),
                "positive_reply": int(positive),
                "meeting": int(meeting),
            }
        )
    return pd.DataFrame(rows)


def write_data(output_dir: Path | str = "data") -> None:
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    deals = generate_deals()
    prospects = generate_prospects()
    deals.to_csv(output_path / "synthetic_deals.csv", index=False)
    generate_leads(deals).to_csv(output_path / "synthetic_leads.csv", index=False)
    prospects.to_csv(output_path / "synthetic_prospects.csv", index=False)
    generate_rep_capacity().to_csv(output_path / "rep_capacity.csv", index=False)
    generate_outbound_events(prospects).to_csv(output_path / "outbound_events.csv", index=False)
    generate_quotas().to_csv(output_path / "rep_quotas.csv", index=False)


if __name__ == "__main__":
    project_root = Path(__file__).resolve().parents[1]
    write_data(project_root / "data")

