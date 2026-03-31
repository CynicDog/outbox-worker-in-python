import os

WORKER_ID: str = os.getenv("WORKER_ID", "worker-1")
POLL_INTERVAL: float = float(os.getenv("POLL_INTERVAL", "5"))
MAX_WORKERS: int = int(os.getenv("MAX_WORKERS", "4"))
DATABASE_URL: str = os.getenv(
    "DATABASE_URL",
    "postgresql://worker:worker@localhost:5432/jobs",
)
