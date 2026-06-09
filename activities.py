import asyncpg
import aiohttp
from temporalio import activity

DB_URL = "postgresql://postgres:postgres@localhost/postgres"
BILLABLE_WEBHOOK_URL = "http://localhost:5678/webhook/process-event"


@activity.defn
async def read_last_run_timestamp() -> str:
    conn = await asyncpg.connect(DB_URL)
    try:
        row = await conn.fetchrow(
            "SELECT value FROM billing_state WHERE key = 'previous_run'"
        )
        return row["value"] if row else "2025-01-20T01:00:00.000Z"
    finally:
        await conn.close()


@activity.defn
async def fetch_events(range_from: str, range_to: str) -> list:
    async with aiohttp.ClientSession() as session:
        async with session.get(
            "https://YOUR_CONTROLLER_URL/apis/dashboard.envmgmt.io/v1/events/paas/partner/kind/compute/instance",
            params={"range_from": range_from, "range_to": range_to, "limit": 30},
            ssl=False
        ) as resp:
            data = await resp.json()
            return data.get("items", [])


@activity.defn
async def save_event_to_db(event: dict) -> None:
    conn = await asyncpg.connect(DB_URL)
    try:
        await conn.execute(
            """INSERT INTO billing_events (id, status, instance_id, organization_id, event_data)
               VALUES ($1, $2, $3, $4, $5)
               ON CONFLICT (id) DO NOTHING""",
            event["id"],
            event["status"],
            event["instance_id"],
            event.get("organization_id", ""),
            str(event)
        )
    finally:
        await conn.close()


@activity.defn
async def forward_event(event: dict) -> None:
    async with aiohttp.ClientSession() as session:
        await session.post(BILLABLE_WEBHOOK_URL, json=event)


@activity.defn
async def update_last_run_timestamp(timestamp: str) -> None:
    conn = await asyncpg.connect(DB_URL)
    try:
        await conn.execute(
            """INSERT INTO billing_state (key, value) VALUES ('previous_run', $1)
               ON CONFLICT (key) DO UPDATE SET value = $1""",
            timestamp
        )
    finally:
        await conn.close()
