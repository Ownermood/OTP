"""Shared HTTP client behaviour: timeouts, bounded retries, error mapping.

Retries only cover *idempotent* reads and transient failures. Anything that
creates state upstream (buying a number, creating an invoice) passes
``retries=0`` so a timeout can never produce a duplicate order or invoice.
"""

from __future__ import annotations

import asyncio
from typing import Any, Mapping

import httpx

from app.core.exceptions import ProviderAuthError, ProviderError, ProviderRateLimitError
from app.core.logging import get_logger

logger = get_logger(__name__)

#: Status codes worth retrying -- transient upstream problems only.
RETRYABLE_STATUS = frozenset({429, 500, 502, 503, 504})


async def request(
    client: httpx.AsyncClient,
    method: str,
    url: str,
    *,
    provider: str,
    params: Mapping[str, Any] | None = None,
    json: Any = None,
    data: Mapping[str, Any] | None = None,
    retries: int = 2,
    backoff: float = 0.5,
) -> httpx.Response:
    """Perform an HTTP request with logging, bounded retries and error mapping."""
    last_error: Exception | None = None

    for attempt in range(retries + 1):
        try:
            response = await client.request(method, url, params=params, json=json, data=data)
        except httpx.TimeoutException as exc:
            last_error = exc
            logger.warning("provider.timeout", provider=provider, url=url, attempt=attempt)
        except httpx.HTTPError as exc:
            last_error = exc
            logger.warning("provider.http_error", provider=provider, url=url, error=str(exc))
        else:
            if response.status_code in (401, 403):
                # Credentials are wrong; retrying cannot fix that.
                raise ProviderAuthError(f"{provider} rejected our credentials")
            if response.status_code == 429:
                last_error = ProviderRateLimitError(f"{provider} rate limited us")
                logger.warning("provider.rate_limited", provider=provider, attempt=attempt)
            elif response.status_code in RETRYABLE_STATUS:
                last_error = ProviderError(f"{provider} returned {response.status_code}")
                logger.warning(
                    "provider.server_error",
                    provider=provider,
                    status=response.status_code,
                    attempt=attempt,
                )
            else:
                return response

        if attempt < retries:
            await asyncio.sleep(backoff * (2**attempt))

    if isinstance(last_error, ProviderError):
        raise last_error
    raise ProviderError(f"{provider} is unreachable") from last_error
