from __future__ import annotations

import hashlib
import pandas as pd

CADENCE = [(0, "Personalized email"), (2, "LinkedIn connection/message"),
           (4, "Call attempt"), (7, "Follow-up email"), (10, "Final call + email")]
EVENT_POINTS = {"open": 1, "click": 3, "site revisit": 4, "download": 5, "reply": 10}


def simulate_lifecycle(prospects, scored, routed, reps, as_of=None, threshold=70, recovery_threshold=20):
    """Deterministic portfolio simulation; never sends messages or changes CRM data.

    Historical dates are synthetic scenarios, independent of received_at. Cadence
    ownership uses a separate demo workload, not the direct-call capacity pool.
    Invalid/duplicate records remain blocked from outreach with a repair action.
    """
    today = pd.Timestamp(as_of or pd.Timestamp.today()).normalize()
    scores = scored.set_index("prospect_id")["total_score"].to_dict()
    routes = routed.set_index("prospect_id").to_dict("index")
    loads = {name: 0 for name in reps["rep_name"]}
    rows = []
    for _, p in prospects.sort_values("prospect_id").iterrows():
        seed = int(hashlib.sha256(p.prospect_id.encode()).hexdigest()[:8], 16)
        r = p.to_dict()
        r.update(status="active", lifecycle_stage="MQL", nurture_entry_date=pd.NaT,
                 engagement_score=0, nurture_touch_count=0, re_engagement_date=pd.NaT,
                 cadence_status="not started", cadence_step=0, assigned_rep="",
                 last_touch_date=pd.NaT, response_date=pd.NaT, cadence_start_date=pd.NaT,
                 was_unassigned=False, next_action="Human review required", engagement_events="")
        eligible = p.email_valid and p.domain_valid and not p.is_duplicate
        route = routes.get(p.prospect_id, {})
        needs_nurture = eligible and scores.get(p.prospect_id, 0) < threshold
        if not eligible:
            r["next_action"] = "Repair email/domain or merge duplicate before enrollment"
        elif needs_nurture:
            r["nurture_entry_date"] = today - pd.Timedelta(days=seed % 110)
        elif p.review_status == "Approved":
            if route.get("routing_status") == "Assigned":
                r.update(assigned_rep=route["routed_rep"], next_action="Rep to contact qualified lead")
            else:
                r["was_unassigned"] = True
                pool = reps[reps["available"] & reps["territories"].str.split("|").map(lambda x: p.territory in x)
                            & reps["segments"].str.split("|").map(lambda x: p.segment in x)]
                if pool.empty:
                    r["next_action"] = "Routing manager: assign territory/segment cadence owner"
                else:
                    owner = min(pool.rep_name, key=lambda name: (loads[name], name))
                    loads[owner] += 1
                    start = today - pd.offsets.BDay(seed % 18)
                    response = start + pd.offsets.BDay(1 + seed % 9) if seed % 3 == 0 else pd.NaT
                    cutoff = min(today, response) if pd.notna(response) else today
                    steps = [(day, action) for day, action in CADENCE if start + pd.offsets.BDay(day) <= cutoff]
                    r.update(assigned_rep=owner, cadence_start_date=start, cadence_step=len(steps),
                             last_touch_date=start + pd.offsets.BDay(steps[-1][0]), cadence_status="in progress")
                    if pd.notna(response) and response <= today:
                        r.update(cadence_status="sales-engaged", response_date=response,
                                 lifecycle_stage="SQL", next_action="Live sales conversation; cadence stopped")
                    elif start + pd.offsets.BDay(10) <= today:
                        r.update(cadence_status="completed-no response",
                                 nurture_entry_date=start + pd.offsets.BDay(10))
                        needs_nurture = True
                    else:
                        day, action = CADENCE[len(steps)]
                        r["next_action"] = f"{action} on {(start + pd.offsets.BDay(day)).date()}"
        if needs_nurture:
            age = (today - r["nurture_entry_date"]).days
            # Four educational emails over three weeks. Engagement is accrued per event.
            touches = [day for day in (0, 7, 14, 21) if day <= age]
            event = list(EVENT_POINTS)[seed % len(EVENT_POINTS)]
            event_days = [] if seed % 4 == 0 else touches
            score = 0
            promoted = None
            for day in event_days:
                score += EVENT_POINTS[event]
                if score >= recovery_threshold:
                    promoted = day
                    break
            if promoted is not None:
                touches = [day for day in touches if day <= promoted]
            r.update(status="nurture", engagement_score=score, nurture_touch_count=len(touches),
                     engagement_events=f"{event}: {len(touches)}" if event_days else "No engagement",
                     next_action="Daily re-score; educational email cadence (days 0, 7, 14, 21)")
            if promoted is not None:
                r.update(status="re-engaged", lifecycle_stage="SQL",
                         re_engagement_date=r["nurture_entry_date"] + pd.Timedelta(days=promoted),
                         next_action="Recovered SQL: sales handoff; nurture stopped")
            elif age >= 90 and score == 0:
                r.update(status="dormant", next_action="Retained for future re-import; nurture stopped")
            elif age >= 21:
                r["next_action"] = "Daily re-score; email sequence complete"
        rows.append(r)
    columns = list(prospects.columns) + ["status", "lifecycle_stage", "nurture_entry_date",
        "engagement_score", "nurture_touch_count", "re_engagement_date", "cadence_status",
        "cadence_step", "assigned_rep", "last_touch_date", "response_date", "cadence_start_date",
        "was_unassigned", "next_action", "engagement_events"]
    result = pd.DataFrame(rows, columns=list(dict.fromkeys(columns)))
    result["was_unassigned"] = result["was_unassigned"].astype(bool)
    for column in ("nurture_entry_date", "re_engagement_date", "last_touch_date", "response_date", "cadence_start_date"):
        result[column] = pd.to_datetime(result[column])
    return result


def lifecycle_metrics(records):
    nurture = records.nurture_entry_date.notna()
    enrolled = records.cadence_start_date.notna()
    responded = records.response_date.notna() & enrolled
    before = int(records.was_unassigned.sum())
    after = int((records.was_unassigned & ~enrolled).sum())
    return dict(nurture_total=int(nurture.sum()), recovered=int((nurture & records.re_engagement_date.notna()).sum()),
                recovery_rate=100 * (nurture & records.re_engagement_date.notna()).sum() / max(1, nurture.sum()),
                cadence_total=int(enrolled.sum()), responses=int(responded.sum()),
                response_rate=100 * responded.sum() / max(1, enrolled.sum()),
                response_days=(records.loc[responded, "response_date"] - records.loc[responded, "cadence_start_date"]).dt.days.mean(),
                unassigned_before=before, unassigned_after=after,
                dormant=int(records.status.eq("dormant").sum()))
