# Temporal Billing POC

A Temporal workflow that polls the Rafay controller API every 5 minutes for compute instance lifecycle events, filters the billable ones, persists them to PostgreSQL, and forwards them to a webhook endpoint.

Runs entirely on a single OCI VM — no Kubernetes, no microservices. Built to understand every part of Temporal before scaling up.

---

## What This Does

```
Rafay Controller API
        ↓  every 5 minutes (Temporal Schedule)
PollBillingEventsWorkflow
        ├── read_last_run_timestamp()   reads previous_run from billing_state table
        ├── fetch_events()              GET from Rafay API (paginated)
        ├── for each billable event:
        │     ├── save_event_to_db()   INSERT into billing_events table
        │     └── forward_event()      POST to /webhook/process-event
        └── update_last_run_timestamp() saves current time for next run
```

Billable statuses: `created`, `success`, `deleted`. All others are dropped.

---

## File Structure

```
temporal-billing/
├── activities.py        all @activity.defn functions (DB + HTTP calls)
├── workflows.py         @workflow.defn — orchestration logic, calls activities
├── worker.py            starts the Worker, registers workflows + activities
├── create_schedule.py   run once — creates the 5-min Temporal schedule
└── dummy_webhook.py     dummy HTTP server on port 5678, prints received events
```

---

## Setup — What Was Done on the OCI VM

This section documents every step taken, including every error encountered and how it was fixed.

### Step 1 — Install Temporal CLI

```bash
curl -sSf https://temporal.download/cli.sh | sh
```

Output confirmed:
```
temporal: Temporal CLI installed at /home/ubuntu/.temporalio/bin/temporal
```

**Issue:** Running `temporal` immediately after install gave:
```
Command 'temporal' not found, but can be installed with:
sudo snap install temporal
```

**Fix:** The installer does not add itself to PATH automatically. Had to export it manually:

"README.md" 297L, 8520B
