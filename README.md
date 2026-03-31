# transactional-outbox-wake-signal

A minimal, runnable showcase of the **Transactional Outbox + Wake Signal** pattern: a brokerless background job queue built with FastAPI, asyncio, and `ThreadPoolExecutor`. No Celery, no Redis, no Kafka — just a PostgreSQL table and two concurrency primitives.

The transformation is intentionally trivial (double every number in a list). The point is the infrastructure around it.

## Architecture

```
┌──────────────────────────────────────────────────────────────────────┐
│  asyncio event loop  (single thread)                                 │
│                                                                      │
│  FastAPI request handlers   ──►  lightweight, non-blocking           │
│  poll_loop() timer          ──►  sleeps between cycles               │
│  claim_and_dispatch()       ──►  claims PENDING jobs from PostgreSQL │
│  nudge handler              ──►  fires claim_and_dispatch() as task  │
└────────────────────────────────┬─────────────────────────────────────┘
                                 │  pool.submit(_run_job, job)
                                 │  (bridge: async → thread)
┌────────────────────────────────▼─────────────────────────────────────┐
│  ThreadPoolExecutor  (N worker threads)                              │
│                                                                      │
│  _run_job()  ──►  double_values()  ──►  store.complete()             │
└──────────────────────────────────────────────────────────────────────┘
```

## File layout

```
transactional-outbox-wake-signal/
├── main.py              # FastAPI app + lifespan (starts poll_loop, shuts down pool)
├── config.py            # Env vars: WORKER_ID, POLL_INTERVAL, MAX_WORKERS, DATABASE_URL
├── docker-compose.yml   # PostgreSQL + app
├── Dockerfile
│
├── api/
│   ├── models.py        # JobRequest, JobResponse (Pydantic)
│   └── routes.py        # POST /jobs, POST /nudge, GET /jobs/{id}, GET /health
│
├── worker/
│   ├── store.py         # SQLAlchemy job queue (insert, claim, complete, fail, reset_stuck)
│   ├── pool.py          # ThreadPoolExecutor + slot tracking (_active dict)
│   ├── poller.py        # poll_loop() + claim_and_dispatch()
│   └── runner.py        # submit() bridge + _run_job() thread function
│
└── core/
    └── transform.py     # double_values(): pure function, no I/O
```

## Running with Docker Compose

```bash
docker compose up --build
```

App is available at `http://localhost:8652`.

## Running locally

```bash
pip install -r requirements.txt
uvicorn main:app --reload --port 8652
```

Requires a running PostgreSQL instance. Set `DATABASE_URL` accordingly.

## Try it

```bash
# Submit a job — nudge fires automatically, thread picks it up within milliseconds
http POST localhost:8652/jobs values:='[1, 2, 3, 4, 5]'
# → {"id": "abc-123", "status": "PENDING"}

# Poll for result (paste the id from above)
http GET localhost:8652/jobs/{id}
# → {"id": "abc-123", "status": "COMPLETED", "result": [2, 4, 6, 8, 10]}

# Control sleep_secs per job (default: 1.0)
http POST localhost:8652/jobs values:='[1, 2, 3]' sleep_secs:=0    # instant
http POST localhost:8652/jobs values:='[1, 2, 3]' sleep_secs:=5    # 5-second transform

# Check how many threads are active right now
http GET localhost:8652/health

# Trigger the wake signal manually
# (this is what the caller does immediately after writing a PENDING row)
http POST localhost:8652/nudge

# Reset stuck RUNNING jobs back to PENDING
http POST "localhost:8652/admin/reset-stuck?stuck_minutes=30&max_retries=3"
```

## Environment variables

| Variable | Default | Description |
|----------|---------|-------------|
| `WORKER_ID` | `worker-1` | Written to `claimed_by` column so you can see which instance claimed a job |
| `POLL_INTERVAL` | `5` | Seconds between poll cycles (the correctness safety net) |
| `MAX_WORKERS` | `4` | Thread pool size |
| `DATABASE_URL` | `postgresql://worker:worker@localhost:5432/jobs` | SQLAlchemy connection string |

## The key idea

Every job submission does two things:

1. Write a `PENDING` row to PostgreSQL — durable, survives crashes, the outbox
2. Fire `claim_and_dispatch()` as a background asyncio task — the wake signal, millisecond latency

`claim_and_dispatch()` uses `SELECT FOR UPDATE SKIP LOCKED` so concurrent claim calls
receive non-overlapping rows — no row is returned to more than one caller.
`poll_loop()` runs the same claim every `POLL_INTERVAL` seconds as a correctness
safety net. The wake signal is purely a latency optimisation — correctness never
depends on it arriving.
