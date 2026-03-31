"""PostgreSQL-backed job queue via SQLAlchemy.

All functions here are synchronous. Callers in the asyncio event loop
(routes, poller) must call them via asyncio.to_thread() to avoid blocking
the loop. Callers in worker threads (runner) may call them directly.

Atomic claiming uses SELECT FOR UPDATE SKIP LOCKED — the PostgreSQL-native
competing-consumers primitive. Two callers running simultaneously will each
receive different rows; locked rows are silently skipped by the other caller.
This replaces the version-column optimistic locking used in the SQLite version.
"""

import json
from datetime import datetime, timezone

from sqlalchemy import create_engine, select, text, String, Integer, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker
from sqlalchemy.types import DateTime

import config as cfg

# ---------------------------------------------------------------------------
# Engine + session factory
# ---------------------------------------------------------------------------

engine = create_engine(cfg.DATABASE_URL, pool_size=10, max_overflow=5)
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)


# ---------------------------------------------------------------------------
# ORM model
# ---------------------------------------------------------------------------

class Base(DeclarativeBase):
    pass


class Job(Base):
    __tablename__ = "job"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    status: Mapped[str] = mapped_column(String, nullable=False, default="PENDING")
    claimed_by: Mapped[str | None] = mapped_column(String, nullable=True)
    claimed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    payload: Mapped[str | None] = mapped_column(Text, nullable=True)
    result: Mapped[str | None] = mapped_column(Text, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    retry_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )


# ---------------------------------------------------------------------------
# Public interface
# ---------------------------------------------------------------------------

def init_db() -> None:
    Base.metadata.create_all(engine)


def insert(job_id: str, payload: list[float], sleep_secs: float = 1.0) -> None:
    with SessionLocal() as session:
        session.add(
            Job(
                id=job_id,
                payload=json.dumps({"values": payload, "sleep_secs": sleep_secs}),
                created_at=datetime.now(timezone.utc),
            )
        )
        session.commit()


def get(job_id: str) -> Job | None:
    with SessionLocal() as session:
        return session.get(Job, job_id)


def claim_pending(worker_id: str, limit: int) -> list[dict]:
    """Atomically claim up to ``limit`` PENDING jobs.

    SELECT FOR UPDATE SKIP LOCKED lets two concurrent callers run the same
    query simultaneously and receive non-overlapping sets of rows — no row
    is returned to more than one caller. Rows locked by another transaction
    are silently skipped rather than waited on.
    """
    now = datetime.now(timezone.utc)
    with SessionLocal() as session:
        rows = (
            session.execute(
                select(Job)
                .where(Job.status == "PENDING")
                .limit(limit)
                .with_for_update(skip_locked=True)
            )
            .scalars()
            .all()
        )
        claimed = []
        for row in rows:
            row.status = "RUNNING"
            row.claimed_by = worker_id
            row.claimed_at = now
            claimed.append({"id": row.id, **json.loads(row.payload)})
        session.commit()
    return claimed


def complete(job_id: str, result: list[float]) -> None:
    with SessionLocal() as session:
        row = session.get(Job, job_id)
        if row:
            row.status = "COMPLETED"
            row.result = json.dumps(result)
            session.commit()


def fail(job_id: str, error: str) -> None:
    with SessionLocal() as session:
        row = session.get(Job, job_id)
        if row:
            row.status = "FAILED"
            row.error = error
            row.retry_count += 1
            session.commit()


def reset_stuck(stuck_minutes: int = 30, max_retries: int = 3) -> int:
    """Reset RUNNING jobs stuck longer than ``stuck_minutes``.

    Jobs that have exhausted ``max_retries`` are marked FAILED.
    Returns the number of rows reset to PENDING.
    """
    threshold = text(
        f"claimed_at < NOW() - INTERVAL '{stuck_minutes} minutes'"
    )
    with SessionLocal() as session:
        stuck = (
            session.execute(
                select(Job).where(Job.status == "RUNNING").where(threshold)
            )
            .scalars()
            .all()
        )
        reset_count = 0
        for row in stuck:
            if row.retry_count >= max_retries:
                row.status = "FAILED"
                row.error = "max retries exceeded"
            else:
                row.status = "PENDING"
                row.claimed_by = None
                row.claimed_at = None
                row.retry_count += 1
                reset_count += 1
        session.commit()
    return reset_count
