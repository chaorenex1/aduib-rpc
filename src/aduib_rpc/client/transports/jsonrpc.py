import json
from typing import AsyncGenerator, Any
from uuid import uuid4

import httpx
from httpx_sse import SSEError, aconnect_sse
from pydantic import ValidationError

from aduib_rpc.client.call_options import RetryOptions, resolve_call_options
from aduib_rpc.client.errors import ClientHTTPError, ClientJSONError
from aduib_rpc.client import ClientContext, ClientRequestInterceptor, ClientJSONRPCError
from aduib_rpc.client.transports.base import ClientTransport
from aduib_rpc.types import (
    AduibRpcRequest,
    AduibRpcResponse,
    JsonRpcMessageRequest,
    JsonRpcMessageResponse,
    JSONRPCErrorResponse,
    JsonRpcStreamingMessageRequest,
    JsonRpcStreamingMessageResponse,
)
from aduib_rpc.utils.constant import DEFAULT_RPC_PATH
from aduib_rpc.client.retry import retry_async
from aduib_rpc.protocol.v2.health import HealthCheckRequest, HealthCheckResponse
from aduib_rpc.server.tasks import (
    TaskCancelRequest,
    TaskCancelResponse,
    TaskEvent,
    TaskQueryRequest,
    TaskQueryResponse,
    TaskSubmitRequest,
    TaskSubmitResponse,
    TaskSubscribeRequest,
)


class JsonRpcTransport(ClientTransport):
    """ A JSON-RPC transport for the Aduib RPC client.

    Pure v2 routing:
      - JSON-RPC `method` is the v2 `rpc.v2/{service}/{handler}` string.
      - `params` is the AduibRpcRequest envelope.

    Streaming:
      - Uses SSE (server emits JSON-RPC responses as SSE events).
    """

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

    @staticmethod
    def _looks_like_aduib_response(value: Any) -> bool:
        if isinstance(value, AduibRpcResponse):
            return True
        if not isinstance(value, dict):
            return False
        status = value.get("status")
        if isinstance(status, str) and status.lower() in {"success", "error", "partial"}:
            return True
        return "aduib_rpc" in value

    def _coerce_aduib_response(self, value: Any) -> AduibRpcResponse | None:
        if isinstance(value, AduibRpcResponse):
            return value
        if not self._looks_like_aduib_response(value):
            return None
        try:
            return AduibRpcResponse.model_validate(value)
        except ValidationError:
            return None

    async def _request_unary(
        self,
        request: AduibRpcRequest,
        *,
        context: ClientContext,
    ) -> JsonRpcMessageResponse:
        return await self._request_unary_with_params(
            request.method,
            request,
            context=context,
            request_meta=request.meta,
        )

    async def _request_unary_with_params(
        self,
        method: str,
        params: Any,
        *,
        context: ClientContext,
        request_meta: dict[str, Any] | None = None,
    ) -> JsonRpcMessageResponse:
        rpc_request = JsonRpcMessageRequest(method=method, params=params, id=str(uuid4()))
        payload, modified_kwargs = await self._apply_interceptors(
            method,
            rpc_request.model_dump(mode='json', exclude_none=True),
            self._get_http_args(context),
            context,
        )

        opts = resolve_call_options(
            config_timeout_s=getattr(context, 'config', None).http_timeout if hasattr(context, 'config') else None,
            meta=request_meta,
            context_http_kwargs=modified_kwargs,
            retry_defaults=RetryOptions(
                enabled=False,
                max_attempts=1,
            ),
        )

        if opts.timeout_s is not None:
            modified_kwargs["timeout"] = opts.timeout_s

        response_data = await self._send_request(payload, modified_kwargs, request_meta=request_meta, opts=opts)
        return JsonRpcMessageResponse.model_validate(response_data)

    async def _stream_requests(
        self,
        request: AduibRpcRequest,
        *,
        context: ClientContext,
    ) -> AsyncGenerator[JsonRpcStreamingMessageResponse, None]:
        async for response in self._stream_requests_with_params(
            request.method,
            request,
            context=context,
            request_meta=request.meta,
        ):
            yield response

    async def _stream_requests_with_params(
        self,
        method: str,
        params: Any,
        *,
        context: ClientContext,
        request_meta: dict[str, Any] | None = None,
    ) -> AsyncGenerator[JsonRpcStreamingMessageResponse, None]:
        rpc_request = JsonRpcStreamingMessageRequest(
            method=method,
            params=params,
            id=str(uuid4()),
        )
        payload, modified_kwargs = await self._apply_interceptors(
            method,
            rpc_request.model_dump(mode='json', exclude_none=True),
            self._get_http_args(context),
            context,
        )

        opts = resolve_call_options(
            config_timeout_s=getattr(context, 'config', None).http_timeout if hasattr(context, 'config') else None,
            meta=request_meta,
            context_http_kwargs=modified_kwargs,
            retry_defaults=RetryOptions(
                enabled=False,
                max_attempts=1,
            ),
        )
        if opts.timeout_s is not None:
            modified_kwargs["timeout"] = opts.timeout_s

        async with aconnect_sse(
                self.httpx_client,
                'POST',
                self.url,
                json=payload,
                **modified_kwargs,
        ) as event_source:
            try:
                async for sse in event_source.aiter_sse():
                    yield JsonRpcStreamingMessageResponse.model_validate(
                        json.loads(sse.data)
                    )
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

    async def completion(self, request: AduibRpcRequest, *, context: ClientContext) -> AduibRpcResponse:
        """Sends a non-streaming request."""
        response = await self._request_unary(request, context=context)
        if isinstance(response.root, JSONRPCErrorResponse):
            raise ClientJSONRPCError(response.root)
        result = self._coerce_aduib_response(response.root.result)
        if result is None:
            raise ClientJSONError("Invalid JSON-RPC result payload for AduibRpcResponse")
        return result

    async def call(self, request: AduibRpcRequest, *, context: ClientContext) -> AduibRpcResponse:
        response = await self._request_unary(request, context=context)
        if isinstance(response.root, JSONRPCErrorResponse):
            raise ClientJSONRPCError(response.root)
        result = self._coerce_aduib_response(response.root.result)
        if result is None:
            raise ClientJSONError("Invalid JSON-RPC result payload for AduibRpcResponse")
        return result

    async def completion_stream(self, request: AduibRpcRequest, *, context: ClientContext) -> AsyncGenerator[
        AduibRpcResponse, None]:
        """Sends a streaming request and yields responses as they arrive."""
        async for response in self._stream_requests(request, context=context):
            if isinstance(response.root, JSONRPCErrorResponse):
                raise ClientJSONRPCError(response.root)
            result = self._coerce_aduib_response(response.root.result)
            if result is None:
                raise ClientJSONError("Invalid JSON-RPC result payload for AduibRpcResponse")
            yield result

    async def call_client_stream(
        self,
        requests,
        *,
        context: ClientContext,
    ) -> AduibRpcResponse:
        raise NotImplementedError("JSON-RPC transport does not support client-streaming calls")

    async def call_bidirectional(
        self,
        requests,
        *,
        context: ClientContext,
    ) -> AsyncGenerator[AduibRpcResponse, None]:
        raise NotImplementedError("JSON-RPC transport does not support bidirectional streaming")

    async def call_server_stream(
        self,
        request: AduibRpcRequest,
        *,
        context: ClientContext,
    ) -> AsyncGenerator[AduibRpcResponse, None]:
        async for response in self._stream_requests(request, context=context):
            if isinstance(response.root, JSONRPCErrorResponse):
                raise ClientJSONRPCError(response.root)
            result = self._coerce_aduib_response(response.root.result)
            if result is None:
                raise ClientJSONError("Invalid JSON-RPC result payload for AduibRpcResponse")
            yield result

    async def health_check(self, request: HealthCheckRequest, *, context: ClientContext) -> HealthCheckResponse:
        if isinstance(request, HealthCheckRequest):
            payload = request.model_dump(exclude_none=True)
        else:
            payload = request if isinstance(request, dict) else {}
        response = await self._request_unary_with_params(
            "rpc.v2/HealthService/Check",
            payload,
            context=context,
        )
        if isinstance(response.root, JSONRPCErrorResponse):
            raise ClientJSONRPCError(response.root)
        result = response.root.result
        return HealthCheckResponse.model_validate(result or {})

    async def health_watch(
        self,
        request: HealthCheckRequest,
        *,
        context: ClientContext,
    ) -> AsyncGenerator[HealthCheckResponse, None]:
        if isinstance(request, HealthCheckRequest):
            payload = request.model_dump(exclude_none=True)
        else:
            payload = request if isinstance(request, dict) else {}
        async for response in self._stream_requests_with_params(
            "rpc.v2/HealthService/Watch",
            payload,
            context=context,
        ):
            if isinstance(response.root, JSONRPCErrorResponse):
                raise ClientJSONRPCError(response.root)
            result = response.root.result
            yield HealthCheckResponse.model_validate(result or {})

    async def task_submit(self, request: TaskSubmitRequest, *, context: ClientContext) -> TaskSubmitResponse:
        submit = request if isinstance(request, TaskSubmitRequest) else TaskSubmitRequest.model_validate(request)
        payload = submit.model_dump(exclude_none=True)
        response = await self._request_unary_with_params(
            "rpc.v2/TaskService/Submit",
            payload,
            context=context,
        )
        if isinstance(response.root, JSONRPCErrorResponse):
            raise ClientJSONRPCError(response.root)
        result = response.root.result
        return TaskSubmitResponse.model_validate(result or {})

    async def task_query(self, request: TaskQueryRequest, *, context: ClientContext) -> TaskQueryResponse:
        query = request if isinstance(request, TaskQueryRequest) else TaskQueryRequest.model_validate(request)
        response = await self._request_unary_with_params(
            "rpc.v2/TaskService/Query",
            query.model_dump(exclude_none=True),
            context=context,
        )
        if isinstance(response.root, JSONRPCErrorResponse):
            raise ClientJSONRPCError(response.root)
        result = response.root.result
        return TaskQueryResponse.model_validate(result or {})

    async def task_cancel(self, request: TaskCancelRequest, *, context: ClientContext) -> TaskCancelResponse:
        cancel = request if isinstance(request, TaskCancelRequest) else TaskCancelRequest.model_validate(request)
        response = await self._request_unary_with_params(
            "rpc.v2/TaskService/Cancel",
            cancel.model_dump(exclude_none=True),
            context=context,
        )
        if isinstance(response.root, JSONRPCErrorResponse):
            raise ClientJSONRPCError(response.root)
        result = response.root.result
        return TaskCancelResponse.model_validate(result or {})

    async def task_subscribe(
        self,
        request: TaskSubscribeRequest,
        *,
        context: ClientContext,
    ) -> AsyncGenerator[TaskEvent, None]:
        sub = request if isinstance(request, TaskSubscribeRequest) else TaskSubscribeRequest.model_validate(request)
        async for response in self._stream_requests_with_params(
            "rpc.v2/TaskService/Subscribe",
            sub.model_dump(exclude_none=True),
            context=context,
        ):
            if isinstance(response.root, JSONRPCErrorResponse):
                raise ClientJSONRPCError(response.root)
            result = response.root.result
            yield TaskEvent.model_validate(result or {})

    async def _send_request(
            self,
            rpc_request_payload: dict[str, Any],
            http_kwargs: dict[str, Any] | None = None,
            *,
            request_meta: dict[str, Any] | None = None,
            opts=None,
    ) -> dict[str, Any]:
        http_kwargs = http_kwargs or {}
        retry_enabled = False
        max_attempts = 1
        if request_meta:
            retry_enabled = bool(request_meta.get("retry_enabled"))
            max_attempts = int(request_meta.get("retry_max_attempts", 1))
        idempotent = bool(request_meta.get("idempotent")) if request_meta else False

        retry_opts = RetryOptions(
            enabled=retry_enabled,
            max_attempts=max_attempts,
            backoff_ms=int(request_meta.get("retry_backoff_ms", 200)) if request_meta else 200,
            max_backoff_ms=int(request_meta.get("retry_max_backoff_ms", 2000)) if request_meta else 2000,
            jitter=float(request_meta.get("retry_jitter", 0.1)) if request_meta else 0.1,
            idempotent_required=True,
        )

        async def _op():
            response = await self.httpx_client.post(
                self.url, json=rpc_request_payload, **http_kwargs
            )
            response.raise_for_status()
            return response.json()

        try:
            return await retry_async(_op, retry=retry_opts, idempotent=idempotent)
        except httpx.ReadTimeout as e:
            raise ClientHTTPError(408, 'Client request timed out') from e
        except httpx.HTTPStatusError as e:
            raise ClientHTTPError(e.response.status_code, str(e)) from e
        except json.JSONDecodeError as e:
            raise ClientJSONError(str(e)) from e
        except httpx.RequestError as e:
            raise ClientHTTPError(
                503, f'Network communication error: {e}'
            ) from e
