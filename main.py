import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI

from api.routes import router
from worker import pool, store
from worker.poller import poll_loop


@asynccontextmanager
async def lifespan(app: FastAPI):
    await asyncio.to_thread(store.init_db)
    asyncio.create_task(poll_loop())
    yield
    pool.shutdown(wait=False)


app = FastAPI(
    title="transactional-outbox-wake-signal",
    description="Brokerless job queue: Transactional Outbox + Wake Signal pattern",
    version="0.1.0",
    lifespan=lifespan,
)

app.include_router(router)
