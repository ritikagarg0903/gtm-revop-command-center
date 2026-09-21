# GTM Workflow Addition: Lead Recycling & Multi-Touch Routing

## Purpose

The current funnel treats leads as binary: they either pass a threshold and move to Sales, or they fail and effectively disappear (or sit as "unassigned prospects"). This spec adds two recycling paths so no lead is dropped — every lead below or at the edge of the qualification bar gets a defined next action instead of going stale.

This turns the dashboard from a **funnel report** into a **lifecycle management system**.

---

## Current State (for context)

- Leads are scored/validated (see "Scoring & Review" and "Prospecting & Enrichment" stages).
- Leads that pass move to SQL → Opportunity → Customer.
- Leads that fail, or aren't yet assigned, currently just sit in an "exceptions" bucket (e.g. "Unassigned prospects," "Prospects failing validation") with no defined next step.

---

## Addition 1: Below-Threshold → Automated Nurture Track

### Trigger condition
A lead scores **below the qualification threshold** at the Scoring & Review stage (insufficient firmographic fit, low engagement signal, or incomplete enrichment data).

### Logic
1. Instead of being dropped or left in "exceptions," the lead is tagged `status: nurture` and routed to an automated, non-sales-touched email sequence.
2. Nurture sequence = 3–5 touch multi-touch email cadence over 2–4 weeks (content, not sales pitch — educational/value-add).
3. Every engagement event (open, click, site revisit, content download, reply) increments an `engagement_score` field on the lead record.
4. A scheduled job re-scores nurture leads on a regular cadence (e.g. daily or weekly).
5. If `engagement_score` crosses a re-qualification threshold, the lead is automatically **promoted** back into the active funnel at MQL or SQL stage (status changes from `nurture` → `re-engaged` → `SQL`).
6. If a lead sits in nurture past a max duration (e.g. 90 days) with no engagement, it is marked `dormant` and removed from active nurture (but not deleted — kept for future re-import).

### Data fields to add
| Field | Type | Description |
|---|---|---|
| `status` | enum | `active`, `nurture`, `re-engaged`, `dormant` |
| `nurture_entry_date` | date | When lead entered nurture |
| `engagement_score` | int | Cumulative engagement points |
| `nurture_touch_count` | int | Number of nurture emails sent |
| `re_engagement_date` | date (nullable) | When/if lead was promoted back |

### New funnel stage
```
Lead → MQL → [Nurture (failed threshold)] → Re-engaged → SQL → Opportunity → Customer
                     ↑___________________________|
              (loops back if engagement threshold met)
```

### New dashboard metric
- **Nurture-to-SQL Recovery Rate** = (# leads promoted from nurture back to SQL) / (total leads that entered nurture) × 100
- This is the single most important new metric — it proves the recycling loop actually works, not just that leads are being warehoused.

### Implementation notes for the builder
- If using an automation tool (e.g. Make.com/Zapier), this can be a scheduled scenario: query leads with `status = nurture`, check `engagement_score` against threshold, update status and trigger a webhook/notification to move the record.
- Email sequence can be sent via any ESP (e.g. Mailchimp, Customer.io, Instantly) triggered by the `nurture_entry_date` field.
- Engagement tracking requires either ESP-native open/click tracking or a lightweight tracking pixel/UTM setup feeding back into the same sheet/database.

---

## Addition 2: Above-Threshold but Not Sales-Ready → Multi-Touch Sales Cadence

### Trigger condition
A lead **passes** the qualification threshold but is not immediately assigned to a rep for a direct call (this addresses the "Unassigned prospects" exception bucket directly).

### Logic
1. Instead of sitting unassigned, the lead is auto-enrolled in a **rep-led multi-touch cadence**: a structured sequence combining email + LinkedIn touch + call attempt over a defined window (e.g. 10 business days).
2. Cadence steps are sequenced and time-boxed, e.g.:
   - Day 0: Personalized email #1
   - Day 2: LinkedIn connection/message
   - Day 4: Call attempt #1
   - Day 7: Personalized email #2
   - Day 10: Call attempt #2 + final email
3. If the lead responds/engages at any point, they are marked `status: sales-engaged` and pulled out of the automated cadence into a live conversation.
4. If the lead completes the full cadence with no response, they are marked `status: cadence-complete — no response` and can be looped back into the **nurture track** (Addition 1) rather than lost entirely.
5. Cadence assignment should auto-route to the correct rep based on existing `Segment`/`Territory` fields already in the data.

### Data fields to add
| Field | Type | Description |
|---|---|---|
| `cadence_status` | enum | `not started`, `in progress`, `sales-engaged`, `completed-no response` |
| `cadence_step` | int | Current step number in sequence |
| `assigned_rep` | string | Rep owner (derived from Segment/Territory) |
| `last_touch_date` | date | Date of most recent cadence action |
| `response_date` | date (nullable) | Date lead responded, if any |

### New dashboard metric
- **Cadence Response Rate** = (# leads that responded during cadence) / (total leads enrolled in cadence) × 100
- **Time-to-First-Response** = average days from cadence start to first lead response
- **Unassigned Prospect Reduction** = before/after comparison showing how many of the "91 unassigned prospects" now have an active cadence instead of sitting idle

### Implementation notes for the builder
- Rep assignment logic can reuse existing Segment/Territory columns already present in the "Validated and Enriched Prospects" table — no new source data needed, just a routing rule (e.g. round-robin within territory, or rep-to-segment mapping table).
- Cadence tooling could be simulated in the same Sheets/automation stack (a simple day-offset column that triggers each step) or represented conceptually if this is a portfolio/demo build rather than a live system.
- On failure (no response after full cadence), write the lead back into the Addition 1 nurture table with `status: nurture` and `nurture_entry_date = today`, closing the loop between both additions.

---

## Combined Funnel View (both additions applied)

```
                                   ┌────────────────────────────┐
                                   │        NURTURE TRACK        │
                                   │ (auto email sequence,       │
                                   │  re-scored periodically)    │
                                   └─────────────┬────────────────┘
                                                 │ engagement threshold met
                                                 ▼
Lead → MQL ──(fails threshold)──────────────────┤
  │                                              │
  │ (passes threshold, unassigned)               │
  ▼                                              │
CADENCE TRACK ──(no response after full cadence)─┘
  │ (responds)
  ▼
SQL → Opportunity → Customer
```

## Summary of new metrics to add to the "Pipeline Health" or "GTM Operations" tab

1. Nurture-to-SQL Recovery Rate
2. Cadence Response Rate
3. Time-to-First-Response (cadence)
4. Unassigned Prospect Reduction (before/after)
5. Dormant Lead Count (leads that exhausted nurture with no engagement)

These five metrics collectively demonstrate that the system doesn't just filter and report leads — it actively recovers and routes them, which is the core value-add expected of a GTM/RevOps workflow.
