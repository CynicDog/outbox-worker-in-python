"""ThreadPoolExecutor wrapper with explicit slot tracking.

acquire() is called before executor.submit() so _active correctly reflects
in-flight jobs even in the instant between submission and thread start.
"""

from concurrent.futures import ThreadPoolExecutor
from typing import Callable, Any

import config as cfg

_executor: ThreadPoolExecutor = ThreadPoolExecutor(max_workers=cfg.MAX_WORKERS)
_active: dict[str, bool] = {}
_max_workers: int = cfg.MAX_WORKERS


def acquire(job_id: str) -> None:
    _active[job_id] = True


def release(job_id: str) -> None:
    _active.pop(job_id, None)


def active_count() -> int:
    return len(_active)


def max_workers() -> int:
    return _max_workers


def capacity() -> bool:
    return len(_active) < _max_workers


def submit(fn: Callable, *args: Any) -> None:
    _executor.submit(fn, *args)


def shutdown(wait: bool = False) -> None:
    _executor.shutdown(wait=wait)


def set_max_workers(n: int) -> None:
    global _max_workers, _executor
    _max_workers = n
    _executor.shutdown(wait=False)
    _executor = ThreadPoolExecutor(max_workers=n)
