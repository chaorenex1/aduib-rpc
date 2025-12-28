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
from aduib_rpc.server.tasks.task_manager import InMemoryTaskManager, TaskNotFoundError
from aduib_rpc.types import AduibRpcResponse, AduibRpcRequest, AduibRPCError, AduibRpcError

logger = logging.getLogger(__name__)


class DefaultRequestHandler(RequestHandler):
    """Default implementation of RequestHandler with no-op methods."""

    def __init__(
            self,
            interceptors: list[ServerInterceptor] | None = None,
            request_executors: dict[str, RequestExecutor] | None = None,
            task_manager: InMemoryTaskManager | None = None,
    ):
        self.request_executors: dict[str, RequestExecutor] = request_executors or {}
        self.interceptors = interceptors or []
        self.task_manager = task_manager or InMemoryTaskManager()

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

                # built-in long task methods
                if context.method in {"task/submit", "task/status", "task/result"}:
                    return await self._handle_task_method(context)

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

                # built-in long task subscribe
                if context.method == "task/subscribe":
                    async for resp in self._handle_task_subscribe(context):
                        yield resp
                    return

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

    async def _handle_task_method(self, context: RequestContext) -> AduibRpcResponse:
        data = context.request.data or {}
        method = context.method

        if method == "task/submit":
            target_method = data.get("target_method")
            params = data.get("params") or {}
            options = data.get("options") or {}
            if not target_method:
                return AduibRpcResponse(
                    id=context.request_id,
                    status="error",
                    error=AduibRpcError(code=400, message="target_method is required", data=None),
                )

            ttl_seconds = options.get("ttl_seconds")

            async def call_target():
                parsed = MethodName.parse_compat(str(target_method))
                service_caller = ServiceCaller.from_service_caller(parsed.service)
                return await service_caller.call(parsed.handler, **(params or {}))

            rec = await self.task_manager.submit(call_target, ttl_seconds=ttl_seconds)
            result = {
                "task_id": rec.task_id,
                "status": rec.status.value,
                "created_at_ms": rec.created_at_ms,
            }
            return AduibRpcResponse(id=context.request_id, result=result)

        if method in {"task/status", "task/result"}:
            task_id = data.get("task_id")
            if not task_id:
                return AduibRpcResponse(
                    id=context.request_id,
                    status="error",
                    error=AduibRpcError(code=400, message="task_id is required", data=None),
                )
            try:
                rec = await self.task_manager.get(str(task_id))
            except TaskNotFoundError:
                return AduibRpcResponse(
                    id=context.request_id,
                    status="error",
                    error=AduibRpcError(code=404, message="task not found", data={"task_id": task_id}),
                )

            base = {
                "task_id": rec.task_id,
                "status": rec.status.value,
                "created_at_ms": rec.created_at_ms,
                "updated_at_ms": rec.updated_at_ms,
            }

            if method == "task/status":
                if rec.error is not None:
                    base["error"] = rec.error.model_dump()
                return AduibRpcResponse(id=context.request_id, result=base)

            # task/result
            if rec.status.value == "succeeded":
                base["value"] = rec.value
            elif rec.error is not None:
                base["error"] = rec.error.model_dump()
            return AduibRpcResponse(id=context.request_id, result=base)

        return AduibRpcResponse(
            id=context.request_id,
            status="error",
            error=AduibRpcError(code=400, message=f"Unknown task method: {method}", data=None),
        )

    async def _handle_task_subscribe(self, context: RequestContext) -> AsyncGenerator[AduibRpcResponse]:
        data = context.request.data or {}
        task_id = data.get("task_id")
        if not task_id:
            yield AduibRpcResponse(
                id=context.request_id,
                status="error",
                error=AduibRpcError(code=400, message="task_id is required", data=None),
            )
            return

        try:
            q = await self.task_manager.subscribe(str(task_id))
        except TaskNotFoundError:
            yield AduibRpcResponse(
                id=context.request_id,
                status="error",
                error=AduibRpcError(code=404, message="task not found", data={"task_id": task_id}),
            )
            return

        try:
            while True:
                ev = await q.get()
                payload = {
                    "event": ev.event,
                    "task": {
                        "task_id": ev.task.task_id,
                        "status": ev.task.status.value,
                        "created_at_ms": ev.task.created_at_ms,
                        "updated_at_ms": ev.task.updated_at_ms,
                    },
                }
                if ev.task.error is not None:
                    payload["task"]["error"] = ev.task.error.model_dump()
                if ev.task.status.value == "succeeded":
                    payload["task"]["value"] = ev.task.value

                yield AduibRpcResponse(id=context.request_id, result=payload)

                if ev.event == "completed" or ev.task.status.value in {"succeeded", "failed", "canceled"}:
                    return
        finally:
            await self.task_manager.unsubscribe(str(task_id), q)

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
