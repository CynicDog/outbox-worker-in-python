"""Background poll loop + claim_and_dispatch.

poll_loop() runs forever as a fire-and-forget asyncio task (started at
application lifespan). It is the correctness guarantee: every PENDING job
will be picked up within POLL_INTERVAL seconds even if the nudge was missed.

claim_and_dispatch() is the shared core called by both the timer and the
nudge endpoint. It checks available slots, claims jobs atomically from the
DB, and hands each one to a worker thread.

store.claim_pending() is synchronous (SQLAlchemy). asyncio.to_thread() runs
it in a thread so the event loop is never blocked by the DB round-trip.
"""

import asyncio

import config as cfg
from worker import pool, runner, store


async def poll_loop() -> None:
    while True:
        await asyncio.sleep(cfg.POLL_INTERVAL)
        await claim_and_dispatch()


async def claim_and_dispatch() -> None:
    available = pool.max_workers() - pool.active_count()
    if available <= 0:
        return
    jobs = await asyncio.to_thread(store.claim_pending, cfg.WORKER_ID, available)
    for job in jobs:
        runner.submit(job)
