# Automatic lead workflow

The dashboard runs `src/workflow.py` against sample records. Unlike the historical simulation, this engine persists actual transitions in SQLite and calculates follow-up work from observed events and delivery acknowledgements. The Nurture Campaigns tab shows marketing email tracking only. Pending actions and movement history remain in the engine for adapters; they are not shown in this tab.

## Rules

- Invalid email/domain or duplicate: blocked with a repair action, no outreach.
- Score below 70: Nurture. Score at least 70: MQL, matched to an available territory/segment rep with capacity.
- Nurture engagement reaches 20: SQL; allocate an owner if capacity allows.
- Reply during cadence: SQL; cancel pending outreach.
- Five acknowledged cadence steps without reply: Nurture after a one-day response window following the final delivery.
- 90 days in nurture with no engagement: Dormant.
- `opportunity_created` event: Opportunity. `customer_won` event: Customer. Scores alone never imply a sale.

Scoring is now automatic at 40/30/30. The old human-review preview does not control routing. Duplicate event IDs are ignored, database transactions serialize updates, and an audit record plus CRM update action is saved with each stage transition.

## Worker

Run from the repository root:

```sh
python -m src.worker --records leads.csv --reps reps.csv --events events.json --db /durable/workflow.sqlite --watch
```

Omit `--watch` for one scheduler run. Watch mode checks every 60 seconds and does not depend on an open browser. Publish input files atomically to avoid partially written snapshots. Lead snapshots need `prospect_id`, `account_name`, `segment`, `territory`, boolean `email_valid`, `domain_valid`, `is_duplicate`, and numeric `total_score` (0–100). Rep snapshots use the existing rep-capacity schema. `current_load` must exclude ownership already held in this workflow to avoid double counting.

Events are JSON objects with unique `event_id`, `prospect_id`, `type`, and UTC `occurred_at`. Supported types: `open`, `click`, `site revisit`, `download`, `reply`, `opportunity_created`, `customer_won`. Initialize a lead before replaying its activity. Unknown leads and future-dated events remain unconsumed for a later run. Importing a snapshot never replaces workflow-owned stage/history.

## Delivery boundary

The engine automatically changes its internal pipeline and writes durable pending actions. A future CRM/email adapter must consume these actions, preserve action-ID idempotency, process each lead's stage updates in order, check cancellation before delivery, and call `Workflow.acknowledge(action_id)` only after confirmed success. Pending emails/calls are not counted as completed. LinkedIn and phone steps represent rep tasks.

No CRM or email adapter is connected, per the current scope. The dashboard no longer includes manual activity dropdowns; events are processed through the worker contract. No production credentials or real data should be added to the public demo. The sample dashboard uses `data/sample-workflow.sqlite`; `WORKFLOW_DB` may override the storage location for testing. This alone does not connect a live data feed.

SQLite survives process restarts on persistent disk, but Streamlit Cloud local files are not durable across rebuilds. A production deployment needs authenticated ingestion, durable database storage, a separately supervised worker, and the chosen source/delivery adapters. These are intentionally deferred until the source system is selected.
