import asyncio
from temporalio.client import Client
from temporalio.worker import Worker
from workflows import PollBillingEventsWorkflow
from activities import (
    read_last_run_timestamp,
    fetch_events,
    save_event_to_db,
    forward_event,
    update_last_run_timestamp,
)

TASK_QUEUE = "billing-task-queue"


async def main():
    client = await Client.connect("localhost:7233")

    worker = Worker(
        client,
        task_queue=TASK_QUEUE,
        workflows=[PollBillingEventsWorkflow],
        activities=[
            read_last_run_timestamp,
            fetch_events,
            save_event_to_db,
            forward_event,
            update_last_run_timestamp,
        ],
    )

    print(f"Worker started — polling task queue: {TASK_QUEUE}")
    await worker.run()


asyncio.run(main())
