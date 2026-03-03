"""Simple in-memory sliding-window rate limiting utilities.

This module intentionally keeps logic framework-agnostic and deterministic for tests.
For production multi-instance deployments, replace with a shared backend (e.g. Redis).
"""

from __future__ import annotations

import time
from collections import deque
from dataclasses import dataclass, field
from threading import Lock


@dataclass
class SlidingWindowRateLimiter:
    """Rate limiter that tracks request timestamps per key."""

    max_requests: int
    window_seconds: int
    _buckets: dict[str, deque[float]] = field(default_factory=dict)
    _lock: Lock = field(default_factory=Lock)

    def allow(self, key: str) -> bool:
        """Return True when request is allowed for key."""
        now = time.monotonic()
        window_start = now - self.window_seconds
        with self._lock:
            bucket = self._buckets.setdefault(key, deque())
            while bucket and bucket[0] <= window_start:
                bucket.popleft()
            if len(bucket) >= self.max_requests:
                return False
            bucket.append(now)
            return True
