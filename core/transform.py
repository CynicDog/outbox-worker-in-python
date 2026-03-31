"""Pure transformation logic — no I/O, no framework dependencies.

The transform doubles every number in the input list.
This is intentionally trivial; the point of this repo is the concurrency
infrastructure around it, not the transformation itself.
"""

import time


def double_values(values: list[float], *, sleep_secs: float = 0.0) -> list[float]:
    """Return a new list with every value multiplied by two.

    ``sleep_secs`` simulates a slow transform (e.g. a real Polars/PyArrow
    operation on a large file). Because this runs inside a ThreadPoolExecutor
    thread, sleeping here does not block the asyncio event loop.
    """
    if sleep_secs > 0:
        time.sleep(sleep_secs)
    return [v * 2 for v in values]
