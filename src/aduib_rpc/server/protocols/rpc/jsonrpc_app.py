import contextlib
import logging
from abc import ABC, abstractmethod
from typing import Any, AsyncGenerator, Callable

from fastapi import FastAPI
from sse_starlette import EventSourceResponse
from starlette.applications import Starlette
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from aduib_rpc.server.context import ServerContext
from aduib_rpc.server.rpc_execution import MethodName, get_runtime
from aduib_rpc.server.request_handlers.jsonrpc_v2_handler import JSONRPCV2Handler
from aduib_rpc.server.request_handlers.request_handler import RequestHandler
from aduib_rpc.types import JsonRpcMessageRequest, JsonRpcStreamingMessageRequest, JSONRPCError, JSONRPCErrorResponse, \
    JSONRPCRequest, AduibJSONRpcRequest, AduibJSONRPCResponse, \
    JsonRpcStreamingMessageResponse
from aduib_rpc.protocol.v2 import ErrorCode, ERROR_CODE_NAMES
from aduib_rpc.protocol.v2 import RpcError
from aduib_rpc.utils.error_handlers import exception_to_error
from aduib_rpc.utils.constant import DEFAULT_RPC_PATH

logger = logging.getLogger(__name__)


class ServerContextBuilder(ABC):
    """Abstract base class for building server content."""

    @abstractmethod
    def build_context(self, request:Request) -> ServerContext:
        """Builds and returns server content based on the provided data."""

class DefaultServerContextBuilder(ServerContextBuilder):
    """Default implementation of ServerContextBuilder."""

    def build_context(self, request:Request) -> ServerContext:
        """Builds and returns a default ServerContext."""
        state={}
        metadata = {}
        with contextlib.suppress(Exception):
            state['headers'] = dict(request.headers)
            headers = state.get("headers", {}) or {}
            tenant_id = (
                headers.get("X-Tenant-ID") or headers.get("x-tenant-id")
                or headers.get("X-Tenant") or headers.get("x-tenant")
            )
            if tenant_id:
                state["tenant_id"] = str(tenant_id)
        return ServerContext(state=state,metadata=metadata)

class RpcPathValidatorMiddleware(BaseHTTPMiddleware):
    """Middleware to validate the RPC path in incoming requests."""

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        if not request.url.path.startswith(DEFAULT_RPC_PATH):
            return JSONResponse(
                content={
                    "jsonrpc": "2.0",
                    "error": {
                        "code": -32601,
                        "message": "Method not found"
                    },
                    "id": None
                },
                status_code=404
            )
        response = await call_next(request)
        return response

class JsonRpcApp(ABC):

    RpcRequestModel=(
        JsonRpcMessageRequest
        | JsonRpcStreamingMessageRequest
    )

    MODEL:dict[str,type[RpcRequestModel]]={
        model.model_fields['method'].default: model
        for model in RpcRequestModel.__args__
    }

    def __init__(
        self,
        context_builder: ServerContextBuilder,
        request_handler: RequestHandler,
    ):
        """Initializes the JsonRpcApp.

        Args:
          context_builder: The ServerContextBuilder instance to build server context.
          request_handler: The underlying `RequestHandler` instance to delegate requests to.
        """
        self.context_builder = context_builder or DefaultServerContextBuilder()
        self.request_handler = request_handler
        self.handler = JSONRPCV2Handler(
            request_handler=request_handler,
        )
        self._method_map = self._build_method_map()

    def _build_method_map(self) -> dict[str, tuple[Callable[..., Any], bool, bool]]:
        return {
            "rpc.v2/AduibRpcService/Call": (self.handler.Call, False, False),
            "rpc.v2/AduibRpcService/CallServerStream": (self.handler.CallServerStream, True, False),
            "rpc.v2/AduibRpcService/CallClientStream": (self.handler.CallClientStream, False, True),
            "rpc.v2/AduibRpcService/CallBidirectional": (self.handler.CallBidirectional, True, True),
            "rpc.v2/TaskService/Submit": (self.handler.Submit, False, False),
            "rpc.v2/TaskService/Query": (self.handler.Query, False, False),
            "rpc.v2/TaskService/Cancel": (self.handler.Cancel, False, False),
            "rpc.v2/TaskService/Subscribe": (self.handler.Subscribe, True, False),
            "rpc.v2/HealthService/Check": (self.handler.Check, False, False),
            "rpc.v2/HealthService/Watch": (self.handler.Watch, True, False),
        }

    def _is_streaming(self, request: Request, method: str) -> bool:
        entry = self._method_map.get(method)
        if entry:
            return bool(entry[1])

        accept = request.headers.get("accept", "") or ""
        if "text/event-stream" in accept.lower():
            return True

        try:
            parsed = MethodName.parse_compat(method)
        except Exception:
            return False

        runtime = get_runtime()
        func = runtime.service_funcs.get(parsed.handler)
        if func is None:
            return False
        return bool(getattr(func, "server_stream", False) or getattr(func, "bidirectional_stream", False))

    def _init_middlewares(self, app:Any)->None:
        """Initializes middleware for the application.

        Args:
            app: The application instance to which the middleware will be added.
        """
        app.add_middleware(RpcPathValidatorMiddleware)


    def _generate_error_response(
        self,
        request_id: str,
        error: JSONRPCError | RpcError
    ) -> JSONResponse:
        """Generates a JSON-RPC error response.

        Args:
            id: The ID of the request that caused the error.
            code: The error code.
            message: A descriptive error message.
            data: Optional additional data about the error.

        Returns:
            A dictionary representing the JSON-RPC error response.
        """
        jsonrpc_error = error
        if isinstance(error, RpcError):
            payload = error.model_dump(mode="json", exclude_none=True)
            jsonrpc_error = JSONRPCError(
                code=int(payload.get("code") or 0),
                message=str(payload.get("message") or ""),
                data=payload,
            )
        error_response = JSONRPCErrorResponse(
            id=request_id,
            error=jsonrpc_error,
        )
        logger.log(
            logging.ERROR,
            "Request Error ID=%s, Code=%d, Message=%s",
            request_id,
            error_response.error.code,
            error_response.error.message,
            ', Data=' + str(error_response.error.data)
            if error_response.error.data
            else '',
        )
        return JSONResponse(
            content=error_response.model_dump(mode='json', exclude_none=True),
            status_code=200,
        )

    async def _handle_requests(
        self,
        request: Request,
    ) -> Response:
        """Handles a JSON-RPC request.

        Args:
            request: The incoming `Request` object.

        Returns:
            A `Response` object containing the JSON-RPC response.
        """
        request_id: str = None
        try:
            body = await request.json()
            if isinstance(body,dict):
                request_id = body.get('id')

            logger.debug("Request ID=%s, Body=%s", request_id, body)
        except Exception as e:
            return self._generate_error_response(
                request_id=request_id,
                error=exception_to_error(e, code=int(ErrorCode.INVALID_MESSAGE)),
            )

        try:
            base_request=JSONRPCRequest.model_validate(body)
            method = base_request.method
            if not method.strip().lstrip("/").startswith("rpc.v2/"):
                return self._generate_error_response(
                    request_id=body.get('id'),
                    error=RpcError(
                        code=int(ErrorCode.METHOD_NOT_FOUND),
                        name=ERROR_CODE_NAMES.get(int(ErrorCode.METHOD_NOT_FOUND), "UNKNOWN"),
                        message="JSON-RPC v2 requires method starting with 'rpc.v2/'",
                    ),
                )
            is_streaming = self._is_streaming(request, method)
            model_class = JsonRpcStreamingMessageRequest if is_streaming else JsonRpcMessageRequest
            rpc_request = model_class.model_validate(body)
        except Exception as e:
            logger.exception("Failed to validate request ID=%s", request_id)
            return self._generate_error_response(
                request_id=body.get('id'),
                error=exception_to_error(e, code=int(ErrorCode.INVALID_PARAMS)),
            )

        context = self.context_builder.build_context(request)
        request_id = rpc_request.id
        method_entry = self._method_map.get(method)

        try:
            if method_entry:
                handler_fn, is_streaming, expects_iter = method_entry
                if expects_iter:
                    async def _iter():
                        yield rpc_request
                    if is_streaming:
                        response_obj = handler_fn(_iter(), context)
                    else:
                        response_obj = await handler_fn(_iter(), context)
                else:
                    if is_streaming:
                        response_obj = handler_fn(rpc_request, context)
                    else:
                        response_obj = await handler_fn(rpc_request, context)
            else:
                if isinstance(rpc_request, JsonRpcStreamingMessageRequest):
                    response_obj = self.handler.on_stream_message(
                        request=rpc_request,
                        context=context,
                    )
                else:
                    response_obj = await self.handler.on_message(
                        request=rpc_request,
                        context=context,
                    )
            return self._create_response(
                request_id=request_id,
                response=response_obj,
                context=context,
            )
        except Exception as e:
            return self._generate_error_response(
                request_id=request_id,
                error=exception_to_error(e, code=int(ErrorCode.INTERNAL_ERROR)),
            )

    async def _process_streaming_request(self,
                                         request_id: str,
                                         request: AduibJSONRpcRequest,
                                         context: ServerContext,
                                         ) -> Response:
        """Processes a streaming JSON-RPC request.
        Args:
            request_id: The ID of the request.
            request: The `AduibJSONRpcRequest` object containing the request details.
            context: Context provided by the server.
        Returns:
            A `Response` object containing the JSON-RPC response.
        """
        request_obj = request.root
        response_obj: Any = None
        if isinstance(request_obj, JsonRpcStreamingMessageRequest):
            response_obj = self.handler.on_stream_message(
                request=request_obj,
                context=context,
            )

        if response_obj is None:
            payload = {
                "code": int(ErrorCode.INTERNAL_ERROR),
                "name": ERROR_CODE_NAMES.get(int(ErrorCode.INTERNAL_ERROR), "UNKNOWN"),
                "message": "unsupported request type",
            }
            response_obj = JSONRPCErrorResponse(
                id=request_id,
                error=JSONRPCError(
                    code=int(ErrorCode.INTERNAL_ERROR),
                    message="unsupported request type",
                    data=payload,
                )
            )

        return self._create_response(
            request_id=request_id,
            response=response_obj,
            context=context,
        )

    async def _process_non_streaming_request(self,
                                             request_id: str,
                                             request: AduibJSONRpcRequest,
                                             context: ServerContext,
                                             ) -> Response:
        """Processes a non-streaming JSON-RPC request.
        Args:
            request_id: The ID of the request.
            request: The `AduibJSONRpcRequest` object containing the request details.
            context: Context provided by the server.
        Returns:
            A `Response` object containing the JSON-RPC response.
        """
        request_obj=request.root
        response_obj:Any=None
        if isinstance(request_obj, JsonRpcMessageRequest):
            response_obj = await self.handler.on_message(
                    request=request_obj,
                    context=context,
                )

        if response_obj is None:
            payload = {
                "code": int(ErrorCode.INTERNAL_ERROR),
                "name": ERROR_CODE_NAMES.get(int(ErrorCode.INTERNAL_ERROR), "UNKNOWN"),
                "message": "unsupported request type",
            }
            response_obj = JSONRPCErrorResponse(
                id=request_id,
                error=JSONRPCError(
                    code=int(ErrorCode.INTERNAL_ERROR),
                    message="unsupported request type",
                    data=payload,
                )
            )

        return self._create_response(
            request_id=request_id,
            response=response_obj,
            context=context,
        )

    def _create_response(
        self,
        request_id: str,
        response: (
                JSONRPCErrorResponse
                | AduibJSONRPCResponse
                | AsyncGenerator[JsonRpcStreamingMessageResponse, None]
        ),
        context: ServerContext) -> Response:
        """Creates a JSON-RPC response.

        Args:
            request_id: The ID of the request.
            response: The response object to be serialized.
            context: Context provided by the server.

        Returns:
            A `Response` object containing the JSON-RPC response.
        """
        if isinstance(response, AsyncGenerator):
            async def event_generator(
                    stream: AsyncGenerator[JsonRpcStreamingMessageResponse, None],
            ) -> AsyncGenerator[dict[str, str], None]:
                async for item in stream:
                    yield {'data': item.root.model_dump_json(exclude_none=True)}

            return EventSourceResponse(
                event_generator(response)
            )
        if isinstance(response, JSONRPCErrorResponse):
            return JSONResponse(
                content=response.model_dump(mode='json', exclude_none=True),
                status_code=200,
            )

        return JSONResponse(
            content=response.root.model_dump(mode='json', exclude_none=True),
            status_code=200,
        )

    @abstractmethod
    def build(self,
              rpc_path: str = DEFAULT_RPC_PATH,
              **kwargs: Any,)->FastAPI|Starlette:
        """Builds and returns the FastAPI or Starlette application.
        Args:
            rpc_path: The RPC path for the application.
            **kwargs: Additional keyword arguments for the application.
        Returns:
            The configured FastAPI or Starlette application instance.
        """
