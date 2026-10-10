"""Waiting out a rate-limited or failed request to an outside service, the same way for every
one of them."""

from typing import Any

# Seconds to wait before each retry of a rate-limited or failed request (about 2 minutes).
RETRY_WAITS = (2, 5, 10, 20, 40, 60)


def retry_after(response: Any) -> float | None:
    try:
        return min(float(response.headers.get("retry-after", "")), 120.0)
    except ValueError:
        return None
