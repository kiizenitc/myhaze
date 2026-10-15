"""HTTP GET with retries. Error messages never include URLs or query strings (they can hold API keys)."""
from __future__ import annotations

import time
from urllib.parse import urlsplit

import httpx

from .config import USER_AGENT


class FetchError(RuntimeError):
    """A source could not be fetched or returned something unusable."""


def make_client(transport: httpx.BaseTransport | None = None) -> httpx.Client:
    return httpx.Client(
        headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
        timeout=httpx.Timeout(30.0),
        follow_redirects=True,
        transport=transport,
    )


def _describe(exc: Exception | None) -> str:
    if isinstance(exc, httpx.HTTPStatusError):
        return f"HTTP {exc.response.status_code}"
    return type(exc).__name__


def _get(client: httpx.Client, url: str, params: dict | None, label: str | None,
         attempts: int, backoff_s: float, parse):
    last: Exception | None = None
    for attempt in range(attempts):
        try:
            response = client.get(url, params=params)
            response.raise_for_status()
            return parse(response)
        except (httpx.HTTPError, ValueError) as exc:
            last = exc
            if attempt < attempts - 1:
                time.sleep(backoff_s * (attempt + 1))
    name = label or urlsplit(url).netloc
    raise FetchError(f"{name} failed after {attempts} attempts: {_describe(last)}") from None


def get_json(client: httpx.Client, url: str, params: dict | None = None, *,
             label: str | None = None, attempts: int = 3, backoff_s: float = 2.0):
    return _get(client, url, params, label, attempts, backoff_s, lambda response: response.json())


def get_text(client: httpx.Client, url: str, params: dict | None = None, *,
             label: str | None = None, attempts: int = 3, backoff_s: float = 2.0) -> str:
    return _get(client, url, params, label, attempts, backoff_s, lambda response: response.text)
