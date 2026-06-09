import asyncio
from datetime import timedelta
from temporalio.client import Client, Schedule, ScheduleActionStartWorkflow, ScheduleIntervalSpec, ScheduleSpec
from workflows import PollBillingEventsWorkflow

SCHEDULE_ID = "poll-billing-events-every-5min"
TASK_QUEUE = "billing-task-queue"


async def main():
    client = await Client.connect("localhost:7233")

    await client.create_schedule(
        SCHEDULE_ID,
        Schedule(
            action=ScheduleActionStartWorkflow(
                PollBillingEventsWorkflow.run,
                id="poll-billing-events",
                task_queue=TASK_QUEUE,
            ),
            spec=ScheduleSpec(
                intervals=[ScheduleIntervalSpec(every=timedelta(minutes=5))]
            ),
        ),
    )
    print(f"Schedule '{SCHEDULE_ID}' created — workflow runs every 5 minutes.")
    print("Check the Temporal Web UI to confirm: http://<your-oci-ip>:8233")


asyncio.run(main())
