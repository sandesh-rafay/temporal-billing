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

```bash
export PATH="$PATH:/home/ubuntu/.temporalio/bin"
```

To make this permanent across sessions:
```bash
echo 'export PATH="$PATH:/home/ubuntu/.temporalio/bin"' >> ~/.bashrc
source ~/.bashrc
```

---

### Step 2 — Start Temporal Server (first attempt)

```bash
temporal server start-dev
```

Server started at `localhost:7233` and UI at `http://localhost:8233`. But opening `http://<oci-public-ip>:8233` in the browser showed nothing.

**Reason:** By default the server binds to `127.0.0.1` — only accessible from the VM itself, not from outside.

**Fix — Part 1:** Bind to all interfaces and persist state to a file:
```bash
temporal server start-dev --ui-ip 0.0.0.0 --ip 0.0.0.0 --db-filename temporal.db
```

`--db-filename temporal.db` stores workflow history and schedules in a SQLite file on disk. Without this flag, `start-dev` uses an in-memory database — everything is lost when the server is killed.

**Fix — Part 2:** OCI VM OS firewall was still blocking port 8233.

Tried `ufw` first:
```bash
sudo ufw allow 8233/tcp
# sudo: ufw: command not found
```

`ufw` is not installed on this Ubuntu image. Used `iptables` directly instead:
```bash
sudo iptables -I INPUT -p tcp --dport 8233 -j ACCEPT
```

After both fixes, `http://<oci-public-ip>:8233` opened the Temporal Web UI successfully.

**Note:** Also open port 7233 if your Worker will connect from a different machine:
```bash
sudo iptables -I INPUT -p tcp --dport 7233 -j ACCEPT
```

For this POC the Worker runs on the same VM so `localhost:7233` works without opening the port externally.

---

### Step 3 — Install PostgreSQL

```bash
sudo apt update
sudo apt install -y postgresql postgresql-contrib
sudo systemctl start postgresql
sudo systemctl enable postgresql
```

Set password for the postgres user:
```bash
sudo -u postgres psql -c "ALTER USER postgres PASSWORD 'postgres';"
```

Output:
```
ALTER ROLE
```

Create the tables:
```bash
sudo -u postgres psql -d postgres -c "
  CREATE TABLE IF NOT EXISTS billing_events (
    id TEXT PRIMARY KEY,
    status TEXT NOT NULL,
    instance_id TEXT NOT NULL,
    organization_id TEXT,
    received_at TIMESTAMPTZ DEFAULT NOW(),
    event_data TEXT NOT NULL
  );
  CREATE TABLE IF NOT EXISTS billing_state (
    key TEXT PRIMARY KEY,
    value TEXT
  );"
```

Output:
```
CREATE TABLE
CREATE TABLE
```

---

### Step 4 — Set Up Python Virtual Environment

**Issue 1:** `pip` not found:
```bash
pip install temporalio aiohttp asyncpg
# Command 'pip' not found
pip3 install temporalio aiohttp asyncpg
# Command 'pip3' not found
```

**Fix:** Install pip:
```bash
sudo apt install python3-pip
```

**Issue 2:** Even after installing pip, running `pip3 install` gave:
```
error: externally-managed-environment
```

Ubuntu 24.04 (Python 3.12) blocks system-wide pip installs by design to protect the OS Python installation. The correct fix is to use a virtual environment, not `--break-system-packages`.

**Issue 3:** Trying to create a venv:
```bash
python3 -m venv .venv
# The virtual environment was not created successfully because ensurepip is not available.
# apt install python3.12-venv
```

**Fix:** Install the required packages:
```bash
sudo apt install -y python3-venv python3-full
```

Then create and activate the venv:
```bash
python3 -m venv .venv
source .venv/bin/activate
```

Install dependencies inside the venv:
```bash
pip install temporalio aiohttp asyncpg
```

This succeeded cleanly.

**Important:** Every time you open a new terminal on the OCI VM, activate the venv before running any Python file:
```bash
source .venv/bin/activate
```

---

### Step 5 — Run the Dummy Webhook in Background

The `forward_event` activity POSTs to `http://localhost:5678/webhook/process-event`. No real webhook server exists in this POC environment, so a dummy server is used.

To run it in the background without occupying a terminal:
```bash
nohup python3 dummy_webhook.py > webhook.log 2>&1 &
```

- `nohup` — keeps it running after terminal close
- `> webhook.log 2>&1` — redirects all output to `webhook.log`
- `&` — runs in background

To watch events arrive in real time:
```bash
tail -f webhook.log
```

To stop it:
```bash
kill $(pgrep -f dummy_webhook.py)
```

---

## Running the Stack

After all setup is complete, the full running order is:

```bash
# Terminal 1 — Temporal server (keep running)
# --db-filename persists workflow history and schedules across restarts
temporal server start-dev --ui-ip 0.0.0.0 --ip 0.0.0.0 --db-filename temporal.db

# Terminal 2 — Worker (keep running)
source .venv/bin/activate
python3 worker.py

# Run once — create the 5-minute schedule
source .venv/bin/activate
python3 create_schedule.py

# Webhook runs in background (already started)
# To check: tail -f webhook.log
```

PostgreSQL runs as a system service and starts automatically — no manual action needed after reboot.

---

## Verify It Is Working

1. Open `http://<oci-public-ip>:8233` — Temporal Web UI
2. Click **Schedules** — you should see `poll-billing-events-every-5min`
3. Click **Workflows** — after the first tick (within 5 min) you should see a completed `PollBillingEventsWorkflow` run
4. Click into a workflow run to see the full activity execution history — each activity, its input, output, duration, and retry count
5. Check the database directly:
   ```bash
   sudo -u postgres psql -d postgres -c "SELECT id, status, received_at FROM billing_events ORDER BY received_at DESC LIMIT 10;"
   ```

---

## Crash Recovery

Temporal persists the state of every workflow execution in its database (`temporal.db`). Every time an activity completes, the result is written to disk before the workflow moves to the next step. On restart, the workflow function replays from the beginning but Temporal intercepts every activity call — if the result is already in the history, it returns it instantly without re-running the activity. This means no duplicate DB inserts, no duplicate webhook POSTs, even after a crash mid-run.

The Worker is stateless — all state lives in the Temporal server's database. If the Worker crashes mid-activity, Temporal marks it as failed and retries it when the Worker comes back. The workflow simply waits.

| What crashed | Data lost | Action needed |
|---|---|---|
| Worker only | Nothing | Restart worker |
| Temporal server only | Nothing (SQLite on disk) | Restart server |
| Worker + Temporal server | Nothing | Restart both |
| Everything | Nothing | Restart in order: postgres → server → worker |
| VM wiped / `temporal.db` deleted | Workflow history + schedules lost | Re-run `create_schedule.py` |

**Important:** This guarantee only holds when the server is started with `--db-filename temporal.db`. Without that flag, `start-dev` uses an in-memory database and all state is lost on server restart.

---

## Key Design Notes

| Item | Value |
|---|---|
| Temporal server | `localhost:7233` |
| Temporal Web UI | `http://<oci-public-ip>:8233` |
| Task queue | `billing-task-queue` |
| Schedule | every 5 minutes |
| Postgres | `localhost`, database `postgres`, user `postgres` |
| Webhook | `http://localhost:5678/webhook/process-event` (dummy server) |
| Venv location | `.venv/` inside project directory |

## Temporal Concepts Used

| Concept | File | Purpose |
|---|---|---|
| Activity | `activities.py` | Each unit of external work (DB, HTTP). Retried independently on failure. |
| Workflow | `workflows.py` | Orchestration logic. Deterministic. Never touches I/O directly. |
| Worker | `worker.py` | Polls task queue, executes registered workflows and activities. |
| Schedule | `create_schedule.py` | Fires the workflow every 5 minutes. Managed by Temporal server. |
| Task Queue | `billing-task-queue` | Channel between Temporal server and Worker. |
