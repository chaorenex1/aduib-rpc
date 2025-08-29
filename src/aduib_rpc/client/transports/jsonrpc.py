import json
from typing import AsyncGenerator, Any
from uuid import uuid4

import httpx
from httpx_sse import SSEError, aconnect_sse

from aduib_rpc.client.errors import ClientHTTPError, ClientJSONError
from aduib_rpc.client import ClientContext, ClientRequestInterceptor, ClientJSONRPCError
from aduib_rpc.client.transports.base import ClientTransport
from aduib_rpc.types import AduibRpcRequest, AduibRpcResponse, JsonRpcMessageRequest, JsonRpcMessageResponse, \
    JSONRPCErrorResponse, JsonRpcStreamingMessageRequest, JsonRpcStreamingMessageResponse
from aduib_rpc.utils.constant import DEFAULT_RPC_PATH


class JsonRpcTransport(ClientTransport):
    """ A JSON-RPC transport for the Aduib RPC client. """
    def __init__(
        self,
        httpx_client: httpx.AsyncClient,
        url: str | None = None,
        interceptors: list[ClientRequestInterceptor] | None = None,
    ):
        """Initializes the RestTransport."""
        if url:
            self.url = url
        else:
            raise ValueError('Must provide  url')
        if self.url.endswith('/'):
            self.url = self.url[:-1]
        if not self.url.endswith(DEFAULT_RPC_PATH):
            self.url = f"{self.url}{DEFAULT_RPC_PATH}"
        self.httpx_client = httpx_client
        self.interceptors = interceptors or []


    async def _apply_interceptors(
        self,
        method_name: str,
        request_payload: dict[str, Any],
        http_kwargs: dict[str, Any] | None,
        context: ClientContext | None,
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        final_http_kwargs = http_kwargs or {}
        final_request_payload = request_payload

        for interceptor in self.interceptors:
            (
                final_request_payload,
                final_http_kwargs,
            ) = await interceptor.intercept_request(
                method_name,
                final_request_payload,
                final_http_kwargs,
                context,
                context.get_schema()
            )
        return final_request_payload, final_http_kwargs

    def _get_http_args(
        self, context: ClientContext | None
    ) -> dict[str, Any] | None:
        return context.state.get('http_kwargs') if context else None

    async def completion(self, request: AduibRpcRequest, *, context: ClientContext) -> AduibRpcResponse:
        """Sends a non-streaming message request to the agent."""
        rpc_request = JsonRpcMessageRequest(params=request, id=str(uuid4()))
        payload, modified_kwargs = await self._apply_interceptors(
            'message/completion',
            rpc_request.model_dump(mode='json', exclude_none=True),
            self._get_http_args(context),
            context,
        )
        response_data = await self._send_request(payload, modified_kwargs)
        response = JsonRpcMessageResponse.model_validate(response_data)
        if isinstance(response.root, JSONRPCErrorResponse):
            raise ClientJSONRPCError(response.root)
        if not response.root.result.is_success():
            raise ClientHTTPError(status_code=response.root.result.error.code, message=response.root.result.error.message)
        return response.root.result

    async def completion_stream(self, request: AduibRpcRequest, *, context: ClientContext) -> AsyncGenerator[
        AduibRpcResponse, None]:
        """Sends a streaming message request to the agent and yields responses as they arrive."""
        rpc_request = JsonRpcStreamingMessageRequest(
            params=request, id=str(uuid4())
        )
        payload, modified_kwargs = await self._apply_interceptors(
            'message/completion/stream',
            rpc_request.model_dump(mode='json', exclude_none=True),
            self._get_http_args(context),
            context,
        )

        modified_kwargs.setdefault('timeout', 60.0)  # default timeout of 60 seconds

        async with aconnect_sse(
                self.httpx_client,
                'POST',
                self.url,
                json=payload,
                **modified_kwargs,
        ) as event_source:
            try:
                async for sse in event_source.aiter_sse():
                    response = JsonRpcStreamingMessageResponse.model_validate(
                        json.loads(sse.data)
                    )
                    if isinstance(response.root, JSONRPCErrorResponse):
                        raise ClientJSONRPCError(response.root)
                    if not response.root.result.is_success():
                        raise ClientHTTPError(status_code=response.root.result.error.code, message=response.root.result.error.message)
                    yield response.root.result
            except SSEError as e:
                raise ClientHTTPError(
                    400, f'Invalid SSE response or protocol error: {e}'
                ) from e
            except json.JSONDecodeError as e:
                raise ClientJSONError(str(e)) from e
            except httpx.RequestError as e:
                raise ClientHTTPError(
                    503, f'Network communication error: {e}'
                ) from e

    async def _send_request(
            self,
            rpc_request_payload: dict[str, Any],
            http_kwargs: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        try:
            response = await self.httpx_client.post(
                self.url, json=rpc_request_payload, **(http_kwargs or {})
            )
            response.raise_for_status()
            return response.json()
        except httpx.ReadTimeout as e:
            raise ClientHTTPError('Client Request timed out') from e
        except httpx.HTTPStatusError as e:
            raise ClientHTTPError(e.response.status_code, str(e)) from e
        except json.JSONDecodeError as e:
            raise ClientJSONError(str(e)) from e
        except httpx.RequestError as e:
            raise ClientHTTPError(
                503, f'Network communication error: {e}'
            ) from e