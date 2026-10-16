"""Reconnect only recoverable agent errors, with a finite outage budget."""
import os
import time
import httpx


def retryable(error):
    return isinstance(error, httpx.RequestError) or (
        isinstance(error, httpx.HTTPStatusError) and
        (error.response.status_code in (408, 429) or error.response.status_code >= 500))


def reconnect(operation, waiting, check=lambda: None):
    deadline = None
    budget = max(1, float(os.getenv('AGENT_RECONNECT_SECONDS', '300')))
    while True:
        check()
        try:
            return operation()
        except httpx.HTTPError as error:
            if not retryable(error): raise
            if deadline is None: deadline = time.monotonic() + budget
            if time.monotonic() >= deadline:
                raise TimeoutError(f'Agent unreachable for {budget:g}s; retry to reconnect') from error
            waiting(str(error))
            time.sleep(min(2, max(0, deadline - time.monotonic())))
