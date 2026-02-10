import functools
import json
import logging
from collections.abc import AsyncIterable, Awaitable
from typing import Any, Callable, Union

from fastapi import FastAPI, APIRouter
from sse_starlette import EventSourceResponse
from starlette.requests import Request
from starlette.responses import Response, JSONResponse

from aduib_rpc.protocol.v2.errors import ErrorCode, error_code_to_http_status
from aduib_rpc.server.context import ServerContext
from aduib_rpc.server.context_builder import V2ServerContextBuilder
from aduib_rpc.server.protocols.rpc.jsonrpc_app import ServerContextBuilder
from aduib_rpc.server.request_handlers import RequestHandler, RESTV2Handler
from aduib_rpc.protocol.v2.types import AduibRpcResponse, ResponseStatus
from aduib_rpc.utils.error_handlers import exception_to_error
from aduib_rpc.utils.constant import DEFAULT_RPC_PATH

logger = logging.getLogger(__name__)

class AduibRpcRestFastAPIApp:
    def __init__(self,
                 request_handler: RequestHandler,
                 context_builder: ServerContextBuilder | None = None,
                    ):
        """Initializes the AduibRpcRestFastAPIApp.
        Args:
            request_handler (RequestHandler): The request handler to process incoming requests.
            context_builder (ServerContextBuilder | None): Optional context builder for request processing.
        """
        self.context_builder = context_builder or V2ServerContextBuilder()
        self.request_handler_v2 = RESTV2Handler(request_handler)

    def build(self,
              rpc_path: str=DEFAULT_RPC_PATH,
              **kwargs: Any,
              ) -> FastAPI:
        """Builds and returns the FastAPI application with the necessary routes.
        Args:
            rpc_path (str): The path for the RPC endpoint. Defaults to '/'.
            **kwargs: Additional keyword arguments.
        Returns:
            FastAPI: The configured FastAPI application.
        """
        app = FastAPI(**kwargs)
        router = APIRouter()
        for (route, handler) in self.routes().items():
            router.add_api_route(
                f'{rpc_path}{route[0]}', handler, methods=[route[1]]
            )
        app.include_router(router)
        return app

    def routes(self) -> dict[tuple[str, str], Callable[[Request], Any]]:
        """Defines the routes for the FastAPI application.
        Returns:
            dict[tuple[str, str], Callable[[Request], Any]]: A mapping of (method, path) to handler functions.
        """
        routes: dict[tuple[str, str], Callable[[Request], Any]] = {
            # --- pure v2 endpoints (json envelope) ---
            ('/v2/rpc', 'POST'): functools.partial(
                self._handle_requests, self.request_handler_v2.on_message
            ),
            ('/v2/rpc/stream', 'POST'): functools.partial(
                self._handle_streaming_requests_v2, self.request_handler_v2.on_stream_message
            ),
            # --- gRPC service-style endpoints (v2) ---
            ('/v2/AduibRpcService/Call', 'POST'): functools.partial(
                self._handle_requests, self.request_handler_v2.Call
            ),
            ('/v2/AduibRpcService/CallServerStream', 'POST'): functools.partial(
                self._handle_streaming_requests_v2, self.request_handler_v2.CallServerStream
            ),
            ('/v2/AduibRpcService/CallClientStream', 'POST'): functools.partial(
                self._handle_requests, self.request_handler_v2.CallClientStream
            ),
            ('/v2/AduibRpcService/CallBidirectional', 'POST'): functools.partial(
                self._handle_streaming_requests_v2, self.request_handler_v2.CallBidirectional
            ),
            ('/v2/TaskService/Submit', 'POST'): functools.partial(
                self._handle_requests, self.request_handler_v2.Submit
            ),
            ('/v2/TaskService/Query', 'POST'): functools.partial(
                self._handle_requests, self.request_handler_v2.Query
            ),
            ('/v2/TaskService/Cancel', 'POST'): functools.partial(
                self._handle_requests, self.request_handler_v2.Cancel
            ),
            ('/v2/TaskService/Subscribe', 'POST'): functools.partial(
                self._handle_streaming_requests_v2, self.request_handler_v2.Subscribe
            ),
            ('/v2/HealthService/Check', 'POST'): functools.partial(
                self._handle_requests, self.request_handler_v2.Check
            ),
            ('/v2/HealthService/Watch', 'POST'): functools.partial(
                self._handle_streaming_requests_v2, self.request_handler_v2.Watch
            ),
        }
        return routes

    def _validate_rpc_path(self, request: Request, rpc_path: str) -> Response:
        """Validates the RPC path of the incoming request."""
        if not request.url.path.startswith(rpc_path):
            err = exception_to_error(
                ValueError("Invalid RPC path"),
                code=int(ErrorCode.METHOD_NOT_FOUND),
            )
            payload = AduibRpcResponse(
                id=None,
                status=ResponseStatus.ERROR,
                error=err,
            ).model_dump(mode="json", exclude_none=True)
            return JSONResponse(
                status_code=error_code_to_http_status(int(err.code)),
                content=payload,
            )
        return JSONResponse(status_code=200, content={})

    async def _handle_requests(self,
                        method: Union[Callable[[Request,ServerContext],Awaitable[Any]],Callable[[Request,ServerContext],AsyncIterable[Any]]],
                        request: Request
                        ) -> Response:
        """Handles incoming requests and delegates to the appropriate request handler method."""
        error_response = self._validate_rpc_path(request, DEFAULT_RPC_PATH)
        if error_response.status_code != 200:
            return error_response
        try:
            await request.json()
        except Exception:
            pass
        context = self.context_builder.build_context(request)
        response = await method(request, context)
        # Map RPC error codes to HTTP status codes per spec v2 section 5.3
        status_code = 200
        if isinstance(response, dict):
            if response.get("status") == ResponseStatus.ERROR:
                error_code = response.get("error", {}).get("code")
                if isinstance(error_code, int):
                    status_code = error_code_to_http_status(error_code)
        return JSONResponse(content=response, status_code=status_code)

    async def _handle_streaming_requests_v2(
        self,
        method: Callable[[Request, ServerContext], AsyncIterable[dict[str, Any]]],
        request: Request,
    ) -> EventSourceResponse:
        """Streaming for pure v2 handler.

        RESTV2Handler yields AduibRpcResponse dicts (already JSON-ready).
        EventSourceResponse will add the 'data:' prefix automatically.
        """
        error_response = self._validate_rpc_path(request, DEFAULT_RPC_PATH)
        if error_response.status_code != 200:
            async def _err() -> AsyncIterable[dict[str, str]]:
                err = exception_to_error(
                    ValueError("Invalid RPC path"),
                    code=int(ErrorCode.METHOD_NOT_FOUND),
                )
                payload = AduibRpcResponse(
                    id=None,
                    status=ResponseStatus.ERROR,
                    error=err,
                ).model_dump(mode="json", exclude_none=True)
                yield {"data": json.dumps(payload)}
            return EventSourceResponse(_err())

        try:
            await request.json()
        except Exception:
            pass
        context = self.context_builder.build_context(request)

        async def event_generator(stream: AsyncIterable[dict[str, Any]]) -> AsyncIterable[dict[str, str]]:
            async for item in stream:
                # EventSourceResponse will add "data:" prefix automatically
                yield {"data": json.dumps(item)}

        return EventSourceResponse(event_generator(method(request, context)))
