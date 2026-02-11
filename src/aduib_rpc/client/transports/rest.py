import json
from typing import AsyncGenerator, Any

import httpx
from httpx_sse import aconnect_sse, SSEError
from pydantic import ValidationError

from aduib_rpc.client import ClientContext, ClientRequestInterceptor
from aduib_rpc.client.call_options import resolve_timeout_s
from aduib_rpc.client.errors import ClientJSONError, ClientHTTPError
from aduib_rpc.client.transports.base import ClientTransport
from aduib_rpc.types import AduibRpcRequest, AduibRpcResponse
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
from aduib_rpc.utils.constant import DEFAULT_RPC_PATH


class RestTransport(ClientTransport):
    """A REST transport for the Aduib RPC client.

    Pure v2 wire:
      - POST {DEFAULT_RPC_PATH}/v2/rpc
      - POST {DEFAULT_RPC_PATH}/v2/rpc/stream (SSE)

    This transport uses v2 endpoints only.
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
            raise ValueError("Must provide  url")
        if self.url.endswith("/"):
            self.url = self.url[:-1]
        if not self.url.endswith(DEFAULT_RPC_PATH):
            self.url = f"{self.url}{DEFAULT_RPC_PATH}"
        self.httpx_client = httpx_client
        self.interceptors = interceptors or []

    def get_http_args(self, context: ClientContext) -> dict:
        return context.state["http_kwargs"] if "http_kwargs" in context.state else {}

    async def _apply_interceptors(
        self,
        method_name: str,
        request_payload: dict[str, Any],
        http_kwargs: dict[str, Any] | None,
        context: ClientContext,
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
                context.get_schema(),
            )
        return final_request_payload, final_http_kwargs

    async def _prepare_http(
        self,
        method_name: str,
        payload: dict[str, Any],
        context: ClientContext,
        *,
        meta: dict[str, Any] | None = None,
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        http_args = self.get_http_args(context)
        payload, http_args = await self._apply_interceptors(
            method_name,
            payload,
            http_args,
            context,
        )
        cfg_timeout = getattr(context, "config", None).http_timeout if hasattr(context, "config") else None
        timeout_s = resolve_timeout_s(config_timeout_s=cfg_timeout, meta=meta, context_http_kwargs=http_args)
        if timeout_s is not None and "timeout" not in http_args:
            http_args["timeout"] = timeout_s
        return payload, http_args

    async def _post_json(
        self,
        endpoint: str,
        payload: dict[str, Any],
        *,
        context: ClientContext,
        meta: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        payload, http_args = await self._prepare_http(endpoint, payload, context, meta=meta)
        return await self._send_post_request(endpoint, payload, http_args, request_meta=meta)

    async def _stream_json(
        self,
        endpoint: str,
        payload: dict[str, Any],
        *,
        context: ClientContext,
        meta: dict[str, Any] | None = None,
    ) -> AsyncGenerator[dict[str, Any], None]:
        payload, http_args = await self._prepare_http(endpoint, payload, context, meta=meta)
        async with aconnect_sse(
            self.httpx_client,
            "POST",
            f"{self.url}{endpoint}",
            json=payload,
            **http_args,
        ) as event_source:
            try:
                async for sse in event_source.aiter_sse():
                    yield json.loads(sse.data)
            except SSEError as e:
                raise ClientHTTPError(400, f"Invalid SSE response or protocol error: {e}") from e
            except json.JSONDecodeError as e:
                raise ClientJSONError(str(e)) from e
            except httpx.RequestError as e:
                raise ClientHTTPError(503, f"Network communication error: {e}") from e

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

    async def completion(self, request: AduibRpcRequest, *, context: ClientContext) -> AduibRpcResponse:
        # v2 unary endpoint
        endpoint = "/v2/rpc"
        payload = request.model_dump(mode="json", exclude_none=True)
        response_data = await self._post_json(endpoint, payload, context=context, meta=request.meta)
        response = AduibRpcResponse.model_validate(response_data)
        return response

    async def call(self, request: AduibRpcRequest, *, context: ClientContext) -> AduibRpcResponse:
        endpoint = "/v2/rpc"
        payload = request.model_dump(mode="json", exclude_none=True)
        response_data = await self._post_json(endpoint, payload, context=context, meta=request.meta)
        response = AduibRpcResponse.model_validate(response_data)
        return response

    async def completion_stream(
        self, request: AduibRpcRequest, *, context: ClientContext
    ) -> AsyncGenerator[AduibRpcResponse, None]:
        endpoint = "/v2/rpc/stream"
        payload = request.model_dump(mode="json", exclude_none=True)
        async for data in self._stream_json(endpoint, payload, context=context, meta=request.meta):
            response = AduibRpcResponse.model_validate(data)
            yield response

    async def call_client_stream(
        self,
        requests,
        *,
        context: ClientContext,
    ) -> AduibRpcResponse:
        raise NotImplementedError("REST transport does not support client-streaming calls")

    async def call_bidirectional(
        self,
        requests,
        *,
        context: ClientContext,
    ) -> AsyncGenerator[AduibRpcResponse, None]:
        raise NotImplementedError("REST transport does not support bidirectional streaming")

    async def call_server_stream(
        self,
        request: AduibRpcRequest,
        *,
        context: ClientContext,
    ) -> AsyncGenerator[AduibRpcResponse, None]:
        endpoint = "/v2/rpc/stream"
        payload = request.model_dump(mode="json", exclude_none=True)
        async for data in self._stream_json(endpoint, payload, context=context, meta=request.meta):
            response = AduibRpcResponse.model_validate(data)
            yield response

    async def health_check(self, request: HealthCheckRequest, *, context: ClientContext) -> HealthCheckResponse:
        payload = (
            request.model_dump(exclude_none=True)
            if isinstance(request, HealthCheckRequest)
            else request
            if isinstance(request, dict)
            else {}
        )
        endpoint = "/v2/HealthService/Check"
        response_data = await self._post_json(endpoint, payload, context=context)
        return HealthCheckResponse.model_validate(response_data or {})

    async def health_watch(
        self,
        request: HealthCheckRequest,
        *,
        context: ClientContext,
    ) -> AsyncGenerator[HealthCheckResponse, None]:
        payload = (
            request.model_dump(exclude_none=True)
            if isinstance(request, HealthCheckRequest)
            else request
            if isinstance(request, dict)
            else {}
        )
        endpoint = "/v2/HealthService/Watch"
        async for data in self._stream_json(endpoint, payload, context=context):
            yield HealthCheckResponse.model_validate(data or {})

    async def task_submit(self, request: TaskSubmitRequest, *, context: ClientContext) -> TaskSubmitResponse:
        submit = request if isinstance(request, TaskSubmitRequest) else TaskSubmitRequest.model_validate(request)
        payload = submit.model_dump(exclude_none=True)
        endpoint = "/v2/TaskService/Submit"
        response_data = await self._post_json(endpoint, payload, context=context)
        return TaskSubmitResponse.model_validate(response_data or {})

    async def task_query(self, request: TaskQueryRequest, *, context: ClientContext) -> TaskQueryResponse:
        query = request if isinstance(request, TaskQueryRequest) else TaskQueryRequest.model_validate(request)
        payload = query.model_dump(exclude_none=True)
        endpoint = "/v2/TaskService/Query"
        response_data = await self._post_json(endpoint, payload, context=context)
        return TaskQueryResponse.model_validate(response_data or {})

    async def task_cancel(self, request: TaskCancelRequest, *, context: ClientContext) -> TaskCancelResponse:
        cancel = request if isinstance(request, TaskCancelRequest) else TaskCancelRequest.model_validate(request)
        payload = cancel.model_dump(exclude_none=True)
        endpoint = "/v2/TaskService/Cancel"
        response_data = await self._post_json(endpoint, payload, context=context)
        return TaskCancelResponse.model_validate(response_data or {})

    async def task_subscribe(
        self,
        request: TaskSubscribeRequest,
        *,
        context: ClientContext,
    ) -> AsyncGenerator[TaskEvent, None]:
        sub = request if isinstance(request, TaskSubscribeRequest) else TaskSubscribeRequest.model_validate(request)
        payload = sub.model_dump(exclude_none=True)
        endpoint = "/v2/TaskService/Subscribe"
        async for data in self._stream_json(endpoint, payload, context=context):
            yield TaskEvent.model_validate(data or {})

    async def _send_request(
        self, request: httpx.Request, *, request_meta: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        try:
            response = await self.httpx_client.send(request)
            response.raise_for_status()
            return response.json()
        except httpx.ReadTimeout as e:
            raise ClientHTTPError(408, "Client request timed out") from e
        except httpx.HTTPStatusError as e:
            raise ClientHTTPError(e.response.status_code, str(e)) from e
        except json.JSONDecodeError as e:
            raise ClientJSONError(str(e)) from e
        except httpx.RequestError as e:
            raise ClientHTTPError(503, f"Network communication error: {e}") from e

    async def _send_post_request(
        self,
        target: str,
        rpc_request_payload: dict[str, Any],
        http_kwargs: dict[str, Any] | None = None,
        *,
        request_meta: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return await self._send_request(
            self.httpx_client.build_request(
                "POST",
                f"{self.url}{target}",
                json=rpc_request_payload,
                **(http_kwargs or {}),
            ),
            request_meta=request_meta,
        )
