from datetime import timedelta
from temporalio import workflow
from temporalio.common import RetryPolicy

with workflow.unsafe.imports_passed_through():
    from activities import (
        read_last_run_timestamp,
        fetch_events,
        save_event_to_db,
        forward_event,
        update_last_run_timestamp,
    )

BILLABLE_STATUSES = {"created", "success", "deleted"}


@workflow.defn
class PollBillingEventsWorkflow:

    @workflow.run
    async def run(self) -> None:
        # Step 1 — read last run timestamp from billing_state table
        last_run = await workflow.execute_activity(
            read_last_run_timestamp,
            schedule_to_close_timeout=timedelta(seconds=30),
            retry_policy=RetryPolicy(maximum_attempts=3),
        )

        # Step 2 — calculate time window
        range_from = last_run
        range_to = workflow.now().strftime("%Y-%m-%dT%H:%M:%S.000Z")

        # Step 3 — fetch all events from Rafay controller API
        events = await workflow.execute_activity(
            fetch_events,
            args=[range_from, range_to],
            schedule_to_close_timeout=timedelta(seconds=60),
            retry_policy=RetryPolicy(maximum_attempts=3),
        )

        # Step 4 — filter and process each billable event
        for event in events:
            if event.get("status") not in BILLABLE_STATUSES:
                continue

            # save to billing_events table in postgres
            await workflow.execute_activity(
                save_event_to_db,
                args=[event],
                schedule_to_close_timeout=timedelta(seconds=10),
                retry_policy=RetryPolicy(maximum_attempts=5),
            )

            # forward to webhook
            await workflow.execute_activity(
                forward_event,
                args=[event],
                schedule_to_close_timeout=timedelta(seconds=10),
                retry_policy=RetryPolicy(maximum_attempts=3),
            )

        # Step 5 — save current time so next run picks up from here
        await workflow.execute_activity(
            update_last_run_timestamp,
            args=[range_to],
            schedule_to_close_timeout=timedelta(seconds=10),
            retry_policy=RetryPolicy(maximum_attempts=3),
        )
