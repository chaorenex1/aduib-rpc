import json
from typing import AsyncGenerator, Any

import httpx
from google.protobuf.json_format import MessageToDict, Parse, ParseDict
from httpx_sse import aconnect_sse, SSEError

from aduib_rpc.client import ClientContext, ClientRequestInterceptor
from aduib_rpc.client.call_options import RetryOptions, resolve_timeout_s
from aduib_rpc.client.errors import ClientJSONError, ClientHTTPError
from aduib_rpc.client.retry import retry_async
from aduib_rpc.client.transports.base import ClientTransport
from aduib_rpc.grpc import aduib_rpc_pb2
from aduib_rpc.types import AduibRpcRequest, AduibRpcResponse
from aduib_rpc.utils import proto_utils
from aduib_rpc.utils.constant import DEFAULT_RPC_PATH


class RestTransport(ClientTransport):
    """ A REST transport for the Aduib RPC client. """
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

    def get_http_args(self, context: ClientContext) -> dict:
        return context.state['http_kwargs'] if 'http_kwargs' in context.state else {}

    async def _setup_request_message(self,method, context, request)-> tuple[dict[str, Any], dict[str, Any]]:
        http_args = self.get_http_args(context)
        data_ = aduib_rpc_pb2.RpcTask(id=request.id, method=request.method,
                                      meta=proto_utils.ToProto.metadata(request.meta),
                                      data=proto_utils.ToProto.taskData(request.data, request.meta))
        final_request_payload = request.model_dump(exclude_none=True)
        final_http_kwargs = http_args or {}
        for interceptor in self.interceptors:
            (
                final_request_payload,
                final_http_kwargs,
            ) = await interceptor.intercept_request(
                method,
                final_request_payload,
                final_http_kwargs,
                context,
                context.get_schema()
            )
        return MessageToDict(data_), final_http_kwargs

    async def completion(self, request: AduibRpcRequest, *, context: ClientContext) -> AduibRpcResponse:
        method = "/v1/message/completion"
        data_, http_args = await self._setup_request_message(method,context, request)

        # Apply unified timeout (meta > http_kwargs > config).
        cfg_timeout = getattr(context, 'config', None).http_timeout if hasattr(context, 'config') else None
        timeout_s = resolve_timeout_s(config_timeout_s=cfg_timeout, meta=request.meta, context_http_kwargs=http_args)
        if timeout_s is not None and 'timeout' not in http_args:
            http_args['timeout'] = timeout_s

        response_data = await self._send_post_request(method, data_, http_args, request_meta=request.meta)
        response = aduib_rpc_pb2.RpcTaskResponse()
        ParseDict(response_data, response)
        rpc_response = proto_utils.FromProto.rpc_response(response)
        if not rpc_response.is_success():
            raise ClientHTTPError(rpc_response.error.code, rpc_response.error.message)
        return rpc_response

    async def completion_stream(self, request: AduibRpcRequest, *, context: ClientContext) -> AsyncGenerator[
        AduibRpcResponse, None]:
        method = "/v1/message/completion/stream"
        data_, http_args = await self._setup_request_message(method,context, request)

        # Apply unified timeout to SSE connect phase.
        cfg_timeout = getattr(context, 'config', None).http_timeout if hasattr(context, 'config') else None
        timeout_s = resolve_timeout_s(config_timeout_s=cfg_timeout, meta=request.meta, context_http_kwargs=http_args)
        if timeout_s is not None and 'timeout' not in http_args:
            http_args['timeout'] = timeout_s

        # Note: we do NOT transparently retry after the stream has started.
        async with aconnect_sse(
                self.httpx_client,
                'POST',
                f'{self.url}{method}',
                json=data_,
                **http_args,
        ) as event_source:
            try:
                async for sse in event_source.aiter_sse():
                    event = aduib_rpc_pb2.RpcTaskResponse()
                    Parse(sse.data, event)
                    response = proto_utils.FromProto.rpc_response(event)
                    if not response.is_success():
                        raise  ClientHTTPError( response.error.code, response.error.message)
                    yield response
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

    async def _send_request(self, request: httpx.Request, *, request_meta: dict[str, Any] | None = None) -> dict[str, Any]:
        request_meta = request_meta or {}
        idempotent = bool(request_meta.get('idempotent'))
        retry_opts = RetryOptions(
            enabled=bool(request_meta.get('retry_enabled', False)),
            max_attempts=int(request_meta.get('retry_max_attempts', 1)),
            backoff_ms=int(request_meta.get('retry_backoff_ms', 200)),
            max_backoff_ms=int(request_meta.get('retry_max_backoff_ms', 2000)),
            jitter=float(request_meta.get('retry_jitter', 0.1)),
            idempotent_required=True,
        )

        async def _op() -> dict[str, Any]:
            response = await self.httpx_client.send(request)
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
                'POST',
                f'{self.url}{target}',
                json=rpc_request_payload,
                **(http_kwargs or {}),
            ),
            request_meta=request_meta,
        )
