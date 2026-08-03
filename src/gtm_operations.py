from __future__ import annotations

import hashlib
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass
from math import sqrt

import pandas as pd


REVIEW_STATUSES = ["Pending", "Approved", "Rejected", "Hold"]
REVIEW_REASONS = [
    "Meets ICP",
    "High intent",
    "Needs research",
    "Bad data",
    "Duplicate",
    "Outside ICP",
    "No current need",
]


@dataclass(frozen=True)
class ProviderRecord:
    account_name: str
    domain: str
    source_provider: str
    source_confidence: float


class ProviderAdapter(ABC):
    """Minimal interface for swapping synthetic feeds with real enrichment providers."""

    @abstractmethod
    def fetch(self, limit: int) -> list[ProviderRecord]:
        raise NotImplementedError


class SyntheticYCAdapter(ProviderAdapter):
    def fetch(self, limit: int) -> list[ProviderRecord]:
        return [
            ProviderRecord(f"YC Company {index:03d}", f"yc-company-{index}.example", "YC Feed", 0.92)
            for index in range(1, limit + 1)
        ]


class SyntheticCompanyFeedAdapter(ProviderAdapter):
    def fetch(self, limit: int) -> list[ProviderRecord]:
        return [
            ProviderRecord(f"Growth Company {index:03d}", f"growth-{index}.example", "Company Feed", 0.84)
            for index in range(1, limit + 1)
        ]


def canonical_domain(value: str) -> str:
    domain = str(value or "").strip().lower()
    domain = re.sub(r"^https?://", "", domain)
    domain = re.sub(r"^www\.", "", domain)
    return domain.split("/")[0]


def canonical_email(value: str) -> str:
    return str(value or "").strip().lower()


def valid_domain(value: str) -> bool:
    return bool(re.fullmatch(r"[a-z0-9][a-z0-9.-]+\.[a-z]{2,}", canonical_domain(value)))


def valid_email(value: str) -> bool:
    return bool(re.fullmatch(r"[^@\s]+@[^@\s]+\.[a-zA-Z]{2,}", canonical_email(value)))


def add_canonical_and_duplicate_fields(prospects: pd.DataFrame) -> pd.DataFrame:
    result = prospects.copy()
    result["canonical_domain"] = result["domain"].map(canonical_domain)
    result["canonical_email"] = result["email"].map(canonical_email)
    result["domain_valid"] = result["canonical_domain"].map(valid_domain)
    result["email_valid"] = result["canonical_email"].map(valid_email)
    duplicate_mask = result.duplicated("canonical_domain", keep="first") | result.duplicated(
        "canonical_email", keep="first"
    )
    result["is_duplicate"] = duplicate_mask
    first_by_domain = result.drop_duplicates("canonical_domain").set_index("canonical_domain")["prospect_id"]
    result["duplicate_of"] = result["canonical_domain"].map(first_by_domain).where(duplicate_mask, "")
    return result


def score_prospects(prospects: pd.DataFrame, weights: dict[str, float]) -> pd.DataFrame:
    result = prospects.copy()
    score_columns = {
        "fit": "fit_score",
        "intent": "intent_score",
        "signal_quality": "signal_quality_score",
        "data_confidence": "data_confidence_score",
    }
    total_weight = sum(max(weights.get(key, 0), 0) for key in score_columns) or 1
    result["total_score"] = sum(
        result[column] * max(weights.get(key, 0), 0) for key, column in score_columns.items()
    ) / total_weight
    result["total_score"] = result["total_score"].round(1)
    return result


def route_leads(prospects: pd.DataFrame, rep_capacity: pd.DataFrame) -> pd.DataFrame:
    """Apply territory/segment eligibility, availability, capacity and round-robin assignment."""
    result = prospects.copy().sort_values("prospect_id")
    capacity = rep_capacity.copy()
    counters: dict[tuple[str, str], int] = {}
    assignments = []

    for _, lead in result.iterrows():
        reason = ""
        rep_name = ""
        status = "Unassigned"

        if bool(lead.get("is_duplicate", False)):
            reason = f"Duplicate of {lead.get('duplicate_of', 'existing record')}"
        elif not bool(lead.get("email_valid", False)) or not bool(lead.get("domain_valid", False)):
            reason = "Invalid email or domain"
        elif lead.get("review_status") != "Approved":
            reason = f"Review gate: {lead.get('review_status', 'Pending')}"
        else:
            eligible = capacity[
                capacity["available"]
                & (capacity["current_load"] < capacity["max_capacity"])
                & capacity["territories"].str.split("|").apply(lambda values: lead["territory"] in values)
                & capacity["segments"].str.split("|").apply(lambda values: lead["segment"] in values)
            ].sort_values("rep_name")

            if eligible.empty:
                reason = "No available rep with matching territory, segment and capacity"
            else:
                key = (lead["territory"], lead["segment"])
                position = counters.get(key, 0) % len(eligible)
                selected_index = eligible.index[position]
                selected = capacity.loc[selected_index]
                rep_name = selected["rep_name"]
                capacity.loc[selected_index, "current_load"] += 1
                counters[key] = counters.get(key, 0) + 1
                status = "Assigned"
                reason = (
                    f"Matched {lead['territory']} territory and {lead['segment']} segment; "
                    f"round-robin position {position + 1}; capacity "
                    f"{int(selected['current_load'])}/{int(selected['max_capacity'])} before assignment"
                )

        assignments.append({"routed_rep": rep_name, "routing_status": status, "routing_reason": reason})

    return pd.concat([result.reset_index(drop=True), pd.DataFrame(assignments)], axis=1)


def deterministic_variant(key: str, variants: list[str]) -> str:
    digest = hashlib.sha256(key.encode("utf-8")).hexdigest()
    return variants[int(digest[:8], 16) % len(variants)]


def wilson_interval(successes: int, sample_size: int, z: float = 1.96) -> tuple[float, float]:
    if sample_size <= 0:
        return 0.0, 0.0
    rate = successes / sample_size
    denominator = 1 + z**2 / sample_size
    centre = rate + z**2 / (2 * sample_size)
    margin = z * sqrt((rate * (1 - rate) + z**2 / (4 * sample_size)) / sample_size)
    return (max(0.0, (centre - margin) / denominator), min(1.0, (centre + margin) / denominator))


def experiment_results(events: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for (segment, variant), group in events.groupby(["segment", "message_variant"]):
        sent = int(group["sent"].sum())
        positive = int(group["positive_reply"].sum())
        low, high = wilson_interval(positive, sent)
        rows.append(
            {
                "segment": segment,
                "message_variant": variant,
                "sample_size": sent,
                "delivered": int(group["delivered"].sum()),
                "replied": int(group["replied"].sum()),
                "positive_replies": positive,
                "meetings": int(group["meeting"].sum()),
                "positive_reply_rate_pct": round(positive / sent * 100, 1) if sent else 0.0,
                "ci_low_pct": round(low * 100, 1),
                "ci_high_pct": round(high * 100, 1),
            }
        )
    return pd.DataFrame(rows).sort_values("positive_reply_rate_pct", ascending=False)


def capacity_recommendation(results: pd.DataFrame) -> str:
    segment_results = results.groupby("segment", as_index=False).agg(
        sample_size=("sample_size", "sum"),
        positive_replies=("positive_replies", "sum"),
    )
    segment_results["rate"] = segment_results["positive_replies"] / segment_results["sample_size"].clip(lower=1)
    eligible = segment_results[segment_results["sample_size"] >= 30].sort_values("rate")
    if len(eligible) < 2:
        return "Keep allocation unchanged until at least two segments have 30 or more sends."
    low = eligible.iloc[0]
    high = eligible.iloc[-1]
    if high["rate"] - low["rate"] < 0.02:
        return "Keep allocation balanced; observed segment performance is not materially different."
    return (
        f"Shift 20% of outbound capacity from {low['segment']} to {high['segment']}; "
        f"positive-reply rates are {low['rate'] * 100:.1f}% vs {high['rate'] * 100:.1f}%."
    )


def review_quality(prospects: pd.DataFrame) -> dict[str, float]:
    reviewed = prospects[prospects["review_status"].isin(["Approved", "Rejected"])].copy()
    false_positive = reviewed[reviewed["review_status"].eq("Approved") & ~reviewed["became_opportunity"]]
    false_negative = reviewed[reviewed["review_status"].eq("Rejected") & reviewed["became_opportunity"]]
    return {
        "reviewed": float(len(reviewed)),
        "false_positive_count": float(len(false_positive)),
        "false_negative_count": float(len(false_negative)),
        "false_positive_pct": round(len(false_positive) / len(reviewed) * 100, 1) if len(reviewed) else 0.0,
        "false_negative_pct": round(len(false_negative) / len(reviewed) * 100, 1) if len(reviewed) else 0.0,
    }

