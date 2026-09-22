# GTM & Revenue Operations Command Center

An interactive portfolio project that models an end-to-end go-to-market and revenue operations workflow using synthetic CRM, prospect, routing, and pipeline data.

The dashboard connects demand generation to revenue execution: leads enter the funnel, prospect records are enriched and validated, approved prospects are scored and routed, and pipeline health is monitored.

**[Open the Live Dashboard](https://gtm-revops-command-center.streamlit.app/)**

## Dashboard Preview

### Executive Overview

![Executive overview of the GTM and Revenue Operations Command Center](assets/executive-overview.png)

### GTM Funnel & Sources

![Lead funnel, sales response metrics, and acquisition-source performance](assets/gtm-funnel-sources.png)

The displayed values are synthetic. In the example snapshot, the dashboard identifies a 10.1% lead-to-opportunity rate, 467 CRM-ready prospects, 98 assigned prospects, and $15.9M in open pipeline.

## Business Questions Addressed

- How efficiently does demand convert from lead to customer?
- Which acquisition sources generate pipeline and closed-won revenue?
- Is sales contacting marketing-qualified leads within the response SLA?
- Which prospect records are valid, current, unique, and ready for CRM delivery?
- Which prospects meet the scoring and human-review criteria for routing?
- Which representatives are eligible and accepting new leads?
- Where is open pipeline concentrated, aging, or at risk?

## End-to-End Operating Model

The command center covers the full path from demand creation to revenue execution:

1. **Demand Generation & Funnel Performance** — track leads through MQL, SQL, opportunity, and customer stages; compare conversion rates and acquisition-source contribution.
2. **Marketing-to-Sales Handoff** — monitor whether MQLs receive a first sales contact within the response SLA and identify leads still awaiting contact.
3. **Prospecting & Enrichment** — standardize company and contact data, validate emails and domains, assess provider quality and freshness, and exclude duplicate records.
4. **Scoring & Human Review** — admit only unique records with valid email and domain data, calculate fit, intent, and combined signal-and-data-confidence scores, then approve, reject, or hold each eligible prospect with a reason code.
5. **Lead Routing** — route only approved, scored prospects using territory, segment specialization, rep availability, remaining capacity, lowest workload utilization, and round-robin tie-breaking. Rejected, pending, held, and data-quality-ineligible prospects do not enter this stage.
6. **Pipeline & Forecast Management** — monitor expected pipeline value, stage aging, forecast categories, and rules-based Deal Risk Level.

The **Executive Overview** summarizes the health of this operating model across demand conversion, CRM readiness, assignment, and pipeline.

## Key Features

- End-to-end executive overview spanning demand conversion, CRM readiness, routing, and pipeline
- Lead-to-customer funnel based on dated lifecycle milestones
- Pipeline and closed-won revenue by acquisition source
- Marketing-to-sales response SLA summary
- Provider-quality comparison using validity, duplicate rate, freshness, and source confidence
- Validated and enriched prospect records ready for CRM delivery
- Configurable three-component scoring across fit, intent, and combined signal and data confidence
- Human approve, reject, and hold review gate with reason codes
- Approved-only routing using territory, segment specialization, rep availability, remaining capacity, lowest workload utilization, and round-robin tie-breaking
- Expected pipeline value and deal risk by sales stage
- Synthetic data generator for safe public demonstration

## Dashboard Sections

The navigation has five main tabs, with no nested GTM Operations tabs:

- **Overview:** Leads Generated, Lead-to-MQL Conversion, Marketing-Sourced Pipeline, and Nurture-to-SQL Recovery.
- **Prospecting & Enrichment:** Provider quality and validated prospect records.
- **Scoring & Review:** Configurable scoring and the review preview.
- **Lead Routing:** Ownership, routing exceptions, and rep capacity.
- **Nurture Campaigns:** Marketing-owned email campaign enrollment, next email themes, sequence progress, send dates, engagement, and CSV export.

Funnel and acquisition-source views, pipeline risk/aging details, and additional summary metrics have been removed to focus the dashboard on a Marketing Specialist workflow. Marketing-sourced pipeline is total opportunity value across stages from Inbound, Paid Search, and Events; the metric tooltip makes this attribution convention explicit. Lead metrics use creation quarter, pipeline uses close quarter, and nurture recovery uses the current simulated prospect cohort. Segment filters apply throughout.

## Scoring Method

Prospect scores are transparent and configurable. Before scoring, a data-quality eligibility gate excludes records with an invalid email, invalid domain, or duplicate identity:

- **Fit:** segment, company size, and role
- **Intent:** website visits, content engagement, and pricing-page views in the last 30 days
- **Signal & data confidence:** signal recency, corroboration, source confidence, and record freshness. This combines the former signal-quality and data-confidence components; email and domain validity remain prerequisites in the scoring eligibility gate.

The component weights are normalized to 100%. A human review gate remains between scoring and routing so the score informs a decision rather than automatically activating every prospect.

Default weights are **Fit 40%**, **Intent 30%**, and **Signal & Data Confidence 30%**. Within the combined component, the former signal-quality score contributes two-thirds and the former data-confidence score contributes one-third, preserving the prior 20% and 10% contributions.

## Routing Criteria

Only scoring-eligible prospects approved by the human review gate enter routing. They are evaluated in this order:

1. Territory match
2. Segment specialization match
3. Representative accepting new leads
4. Remaining representative capacity
5. Lowest current workload utilization
6. Round-robin tie-break among equally utilized eligible representatives

## Deal Risk Method

Deal Risk Level is a deterministic, auditable rating based on:

- Deal notes and identified blockers
- Sales stage
- Days in the current stage
- Recent activity
- Expected close date
- Forecast category

The rules produce a Low, Medium, or High rating and a concise risk reason. This is a rules-based operations model, not a predictive machine-learning model.

## Tech Stack

- Python
- Streamlit
- pandas
- Plotly

## Project Structure

```text
sales-ops-command-center/
  app.py
  requirements.txt
  README.md
  assets/
    executive-overview.png
    gtm-funnel-sources.png
  data/
    synthetic_deals.csv
    synthetic_leads.csv
    synthetic_prospects.csv
    rep_capacity.csv
    rep_quotas.csv
  src/
    generate_data.py
    gtm_operations.py
    metrics.py
    risk_scoring.py
```

## Run Locally

Install dependencies:

```bash
pip install -r requirements.txt
```

Run the app:

```bash
streamlit run app.py
```

The first run generates synthetic input data when local CSV files are not present.

## Synthetic Data Disclaimer

All CRM, prospect, and representative data is synthetic. No real customer, employer, prospect, or CRM export data is used.

## Production Extensions

With access to production systems, the next steps would be to:

- Connect Salesforce or HubSpot opportunities, accounts, contacts, owners, and activity history
- Integrate enrichment and email-validation providers
- Persist review decisions and routing history in an operational database
- Validate lifecycle stages, forecast categories, quotas, territories, and SLA definitions with business owners
- Reconcile closed-won revenue against finance-approved bookings
- Track stage movement and forecast changes over time
- Add role-based access, audit logs, alerts, and scheduled pipeline summaries

## Previous Lifecycle Simulation (reference)

The [source specification](docs/lead-recycling-spec.md) is implemented as a deterministic portfolio simulation in `src/lifecycle.py`. No real outreach is sent, and no scheduler or CRM integration is connected.

- Valid, unique prospects below the qualification score of 70 enter nurture. Invalid or duplicate records receive a repair action before any outreach.
- Four educational touches run on days 0, 7, 14, and 21. Synthetic open/click/site revisit/download/reply events contribute 1/3/4/5/10 points. Daily re-scoring is modeled; 20 points promotes to re-engaged with an SQL milestone. No engagement for 90 days marks the record dormant.
- Approved, above-threshold prospects without a direct-call owner enter a matching territory/segment rep cadence. This demo has a separate balanced cadence workload; it does not claim to free direct-call capacity. Missing or unavailable coverage remains an explicit manager action.
- Sales touches follow business-day offsets 0/2/4/7/10. A response stops the cadence; completion without response enters nurture and preserves cadence history.
- Overview focuses on nurture-to-SQL recovery; cadence and dormancy history remain in the Lead Recycling records. Denominators include all historical enrollments, including completed records. No responses displays a dash.
- Lifecycle dates are synthetic historical scenarios, not reconstructed CRM events. Segment filters apply to prospects; quarter filters apply to demand and revenue only. The lifecycle and routing use default scoring and source review decisions; the existing scoring editor is a what-if preview.

Validate with `python -m unittest discover -s tests -v`.

## Automatic Workflow

The dashboard now uses a persistent rules engine with event deduplication, automatic pipeline transitions, capacity-aware assignment, pending delivery actions, and a movement audit trail. Scoring uses the fixed 40/30/30 model; the former what-if review editor is removed. The historical simulation module remains only for reference tests. See [Automatic workflow](docs/automatic-workflow.md) for rules, worker execution, data contracts, and deferred integration requirements.

## Company context for sales

Overview cards include visible plain-language definitions. Provider quality shows record counts, valid email/domain rates, and duplicate rates; Fresh Record and Average Confidence are removed. Company enrichment fields remain in the prospect table. Standalone sales briefs and the technical pending-action queue are removed from the dashboard; the nurture tab is named Nurture Campaigns. Generated company profiles are explicitly synthetic. Existing provider records without these fields display Not provided; no live company research is claimed.

## Nurture campaign tracking

The nurture tab shows only currently enrolled nurture leads. It has no dropdowns, sales-rep column, or general pipeline activity controls. Leads entering nurture release their sales rep; recovered SQLs can be assigned again. Campaign fields include segment-based campaign name, status, company sender email, next email type/theme/CTA, confirmed sequence progress, enrollment and send dates, opens/clicks/replies, engagement score, and last engagement. Configure `MARKETING_FROM_EMAIL` to display the company sender; this setting alone does not enable delivery. Themes are planned educational content, not generated/sent email bodies. Counters use observed events and send acknowledgements; legacy missing tracking is blank. Delivery, bounce and unsubscribe rates require future provider integration.
