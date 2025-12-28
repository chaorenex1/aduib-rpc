import logging
import uuid
from collections.abc import AsyncGenerator

from aduib_rpc.rpc.methods import MethodName
from aduib_rpc.server.context import ServerContext, ServerInterceptor
from aduib_rpc.server.rpc_execution import get_request_executor
from aduib_rpc.server.rpc_execution.context import RequestContext
from aduib_rpc.server.rpc_execution.request_executor import RequestExecutor, add_request_executor
from aduib_rpc.server.rpc_execution.service_call import ServiceCaller
from aduib_rpc.server.request_handlers import RequestHandler
from aduib_rpc.types import AduibRpcResponse, AduibRpcRequest, AduibRPCError

logger = logging.getLogger(__name__)


class DefaultRequestHandler(RequestHandler):
    """Default implementation of RequestHandler with no-op methods."""

    def __init__(
            self,
            interceptors: list[ServerInterceptor] | None = None,
            request_executors: dict[str, RequestExecutor] | None = None,
    ):
        self.request_executors: dict[str, RequestExecutor] = request_executors or {}
        self.interceptors = interceptors or []

        if request_executors:
            for method, executor in request_executors.items():
                add_request_executor(method, executor)


    async def on_message(
            self,
            message: AduibRpcRequest,
            context: ServerContext | None = None,

    )-> AduibRpcResponse:
        """Handles the 'message' method.
        Args:
            message: The incoming request object.
            context: Context provided by the server.

        Returns:
            The `AduibRpcResponse` object containing the response.
        """
        try:
            intercepted: AduibRPCError | None = None
            if self.interceptors:
                for interceptor in self.interceptors:
                    intercepted = await interceptor.intercept(message, context)
                    if intercepted:
                        break
            if not intercepted:
                context: RequestContext = self._setup_request_context(message, context)
                request_executor = self._validate_request_executor(context)
                if request_executor is None:
                    method = MethodName.parse_compat(context.method)
                    service_caller = ServiceCaller.from_service_caller(method.service)
                    response = await service_caller.call(method.handler, **(context.request.data or {}))
                    return AduibRpcResponse(id=context.request_id, result=response)
                else:
                    response = request_executor.execute(context)
                    return AduibRpcResponse(id=context.request_id, result=response)
            else:
                return AduibRpcResponse(id=context.request_id, result=None, status='error',
                                       error=intercepted)
        except Exception:
            logger.exception("Error processing message")
            raise

    async def on_stream_message(self, message: AduibRpcRequest,
                                context: ServerContext | None = None,
                                ) -> AsyncGenerator[AduibRpcResponse]:
        """Handles the 'stream_message' method.

        Args:
            message: The incoming request object.
            context: Context provided by the server.

        Yields:
            The `AduibRpcResponse` objects containing the streaming responses.
        """
        try:
            intercepted: AduibRPCError | None = None
            if self.interceptors:
                for interceptor in self.interceptors:
                    intercepted = await interceptor.intercept(message, context)
            if not intercepted:
                context: RequestContext = self._setup_request_context(message, context)
                request_executor = self._validate_request_executor(context)
                if request_executor is None:
                    method = MethodName.parse_compat(context.method)
                    service_caller = ServiceCaller.from_service_caller(method.service)
                    response = await service_caller.call(method.handler, **(context.request.data or {}))
                    yield AduibRpcResponse(id=context.request_id, result=response)
                else:
                    async for response in request_executor.execute(context):
                        yield AduibRpcResponse(id=context.request_id, result=response)
            else:
                yield AduibRpcResponse(id=context.request_id, result=None, status='error',
                                       error=intercepted)
        except Exception:
            logger.exception("Error processing stream message")
            raise

    def _setup_request_context(self,
                               message: AduibRpcRequest,
            context: ServerContext | None = None) -> RequestContext:
        """Sets up and returns a RequestContext based on the provided ServerContext."""
        context_id:str=str(uuid.uuid4())
        request_id:str=message.id or str(uuid.uuid4())
        request_context = RequestContext(
            context_id=context_id,
            request_id=request_id,
            request=message,
            server_context=context,
        )
        return request_context

    def _validate_request_executor(self, context: RequestContext) -> RequestExecutor | None:
        """Validates and returns the RequestExecutor instance."""
        request_executor: RequestExecutor | None = get_request_executor(method=context.method)
        if request_executor is None:
            logger.error("RequestExecutor for %s not found", context.model_name)
        return request_executor
