from __future__ import annotations

from typing import Any, Tuple

from aduib_rpc.client import ClientContext, ClientRequestInterceptor
from aduib_rpc.utils.constant import SecuritySchemes


class OTelClientInterceptor(ClientRequestInterceptor):
    """Client-side request interceptor adding trace context headers.

    Works for REST/JSON-RPC (httpx kwargs) and can be extended for gRPC separately.
    """

    async def intercept_request(
        self,
        method: str,
        request_body: dict[str, Any],
        http_kwargs: dict[str, Any],
        context: ClientContext,
        schema: SecuritySchemes,
    ) -> Tuple[dict[str, Any], dict[str, Any]]:
        try:
            from opentelemetry.propagate import inject
        except Exception:
            return request_body, http_kwargs

        headers = dict(http_kwargs.get("headers") or {})
        inject(headers)
        http_kwargs = dict(http_kwargs)
        http_kwargs["headers"] = headers
        return request_body, http_kwargs

