# Revenue Operations Command Center

An interactive revenue operations portfolio project that analyzes synthetic CRM data for pipeline health, quota attainment, rep performance, forecast risk, and manager action prioritization.

![Revenue Operations Command Center dashboard](assets/dashboard-overview.png)

The dashboard is framed around a practical business problem: helping revenue leaders understand whether the team has enough quality pipeline, which deals create forecast risk, and where manager attention should be focused before pipeline and forecast reviews.

## Why This Project Exists

Sales operations teams help leadership answer practical revenue questions:

- Do we have enough pipeline to hit quota?
- Which reps are on track or at risk?
- Which Commit deals may be creating forecast risk?
- Where are deals stalling in the pipeline?
- Which open deals need manager attention before the forecast call?

This dashboard turns synthetic CRM-style data into those business answers.

## Key Features

- Executive overview with open pipeline, weighted pipeline, quota gap, coverage, and Commit risk
- Pipeline health by stage, risk level, and stage age
- Rep performance by quota attainment, win rate, deal size, and sales cycle
- Manager action queue prioritized by deal risk and pipeline value
- Transparent deal risk scoring using notes, stage age, activity, close date, and forecast category
- Recommended manager action for medium- and high-risk deals
- Synthetic CRM data generator for safe public portfolio use

## Dashboard Structure

- **Executive Overview:** Are we on track, and how much Commit pipeline is exposed?
- **Pipeline Health:** Is the open pipeline healthy, weighted appropriately, and progressing?
- **Rep Performance:** Who is attaining quota, and where may coaching be required?
- **Manager Action Queue:** Which opportunities need validation, escalation, or a dated next step?

## Deal Risk Method

The deal-risk layer uses transparent business rules over:

- Deal notes
- Sales stage
- Days in current stage
- Last activity date
- Expected close date
- Forecast category

It produces a risk level, concise reason, and recommended manager action. The method is intentionally deterministic and auditable; it is not presented as a predictive machine-learning model.

This shows how unstructured sales notes and CRM activity signals can be converted into decision-useful insights that are easy to review and act on.

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
  .gitignore
  data/
    synthetic_deals.csv
    rep_quotas.csv
  src/
    generate_data.py
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

The first run creates synthetic data files in the `data/` folder if they do not already exist.

## Synthetic Data Disclaimer

All CRM data in this project is synthetic. No real customers, prospects, employer data, or CRM exports are used.

## What I Would Do With Real CRM Data

With access to Salesforce or HubSpot data, I would:

- Connect to opportunity, account, owner, activity, and quota tables
- Validate stage definitions and forecast categories with sales leadership
- Reconcile closed-won revenue against finance-approved bookings data
- Add historical trend analysis by week and quarter
- Add manager hierarchy and territory segmentation
- Track forecast changes over time instead of only final Commit status
- Calculate true stage conversion from opportunity stage history
- Build scheduled weekly pipeline risk summaries for sales managers

