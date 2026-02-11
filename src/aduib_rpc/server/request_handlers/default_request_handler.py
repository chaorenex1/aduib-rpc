import asyncio
import inspect
import logging
import time
import uuid
from collections.abc import AsyncGenerator, AsyncIterator
from typing import Any

from aduib_rpc.exceptions import RpcException
from aduib_rpc.protocol.v2 import (
    AduibRpcResponse,
    AduibRpcRequest,
    ResponseStatus,
    RpcError,
)
from aduib_rpc.protocol.v2.errors import ERROR_CODE_NAMES, ErrorCode
from aduib_rpc.protocol.v2.health import HealthCheckRequest, HealthStatus, HealthCheckResponse
from aduib_rpc.protocol.v2.qos import Priority
from aduib_rpc.server.context import InterceptContext, ServerContext, ServerInterceptor, InterceptorChain
from aduib_rpc.server.request_handlers import RequestHandler
from aduib_rpc.server.rpc_execution import get_request_executor, MethodName
from aduib_rpc.server.rpc_execution.context import RequestContext
from aduib_rpc.server.rpc_execution.request_executor import RequestExecutor, add_request_executor
from aduib_rpc.server.rpc_execution.service_call import ServiceCaller
from aduib_rpc.server.tasks.task_manager import InMemoryTaskManager, TaskNotFoundError
from aduib_rpc.server.tasks.types import (
    TaskMethod,
    TaskCancelRequest,
    TaskCancelResponse,
    TaskEvent,
    TaskQueryRequest,
    TaskQueryResponse,
    TaskRecord,
    TaskStatus,
    TaskSubmitRequest,
    TaskSubmitResponse,
    TaskSubscribeRequest,
)

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
        self._chain = InterceptorChain(self.interceptors)

        if request_executors:
            for method, executor in request_executors.items():
                add_request_executor(method, executor)

    async def on_message(
        self,
        message: AduibRpcRequest,
        context: ServerContext | None = None,
    ) -> AduibRpcResponse:
        """Handles the 'message' method.
        Args:
            message: The incoming request object.
            context: Context provided by the server.

        Returns:
            The `AduibRpcResponse` object containing the response.
        """
        server_context = context or ServerContext()
        async for response in self._chain.execute(
            message,
            server_context,
            self._handle_unary,
            is_stream=False,
        ):
            return response

        return AduibRpcResponse(
            id=message.id,
            status=ResponseStatus.ERROR,
            error=RpcError(
                code=int(ErrorCode.INTERNAL_ERROR),
                name=ERROR_CODE_NAMES.get(int(ErrorCode.INTERNAL_ERROR), "UNKNOWN"),
                message="No response",
            ),
        )

    async def call(
        self,
        request: AduibRpcRequest,
        context: ServerContext | None = None,
    ) -> AduibRpcResponse:
        """Handles AduibRpcService.Call."""
        return await self.on_message(request, context)

    async def call_server_stream(
        self,
        request: AduibRpcRequest,
        context: ServerContext | None = None,
    ) -> AsyncGenerator[AduibRpcResponse, None]:
        """Handles AduibRpcService.CallServerStream."""
        async for response in self.on_stream_message(request, context):
            yield response

    async def call_client_stream(
        self,
        requests: AsyncIterator[AduibRpcRequest],
        context: ServerContext | None = None,
    ) -> AduibRpcResponse:
        """Handles AduibRpcService.CallClientStream."""
        request = await self._collect_stream_request(requests)
        return await self.on_message(request, context)

    async def call_bidirectional(
        self,
        requests: AsyncIterator[AduibRpcRequest],
        context: ServerContext | None = None,
    ) -> AsyncGenerator[AduibRpcResponse, None]:
        """Handles AduibRpcService.CallBidirectional."""
        request = await self._collect_stream_request(requests)
        async for response in self.on_stream_message(request, context):
            yield response

    async def on_stream_message(
        self,
        message: AduibRpcRequest,
        context: ServerContext | None = None,
    ) -> AsyncGenerator[AduibRpcResponse]:
        """Handles the 'stream_message' method.

        Args:
            message: The incoming request object.
            context: Context provided by the server.

        Yields:
            The `AduibRpcResponse` objects containing the streaming responses.
        """
        server_context = context or ServerContext()
        async for response in self._chain.execute(
            message,
            server_context,
            self._handle_stream,
            is_stream=True,
        ):
            yield response

    async def _handle_unary(
        self,
        ctx: InterceptContext,
    ) -> AsyncIterator[AduibRpcResponse]:
        response = await self._dispatch_unary(ctx.request, ctx.server_context)
        yield response

    async def _handle_stream(
        self,
        ctx: InterceptContext,
    ) -> AsyncIterator[AduibRpcResponse]:
        stream = self._dispatch_stream(ctx.request, ctx.server_context)
        if inspect.isawaitable(stream):
            stream = await stream
        async for response in stream:
            yield response

    async def task_submit(
        self,
        request: TaskSubmitRequest,
        context: ServerContext | None = None,
    ) -> TaskSubmitResponse:
        aduib_rpc_request = AduibRpcRequest.model_validate(request.params)
        server_context = context or ServerContext()
        request_context = self._setup_request_context(aduib_rpc_request, server_context)
        async for resp in self._handle_task_method(request_context):
            self._raise_for_error(resp, "task/submit failed")
            result = resp.result or {}
            return TaskSubmitResponse(
                task_id=str(result.get("task_id", "")),
                status=self._map_task_status(result.get("status")),
                created_at_ms=int(result.get("created_at_ms") or 0),
            )
        return None

    async def task_query(
        self,
        request: TaskQueryRequest,
        context: ServerContext | None = None,
    ) -> TaskQueryResponse:
        try:
            rec = await self.task_manager.get(str(request.task_id))
        except TaskNotFoundError as exc:
            raise RpcException(
                code=int(ErrorCode.RESOURCE_NOT_FOUND),
                message="task not found",
                data={"task_id": request.task_id},
                cause=exc,
            )
        return TaskQueryResponse(task=self._task_record_from_manager(rec))

    async def task_cancel(
        self,
        request: TaskCancelRequest,
        context: ServerContext | None = None,
    ) -> TaskCancelResponse:
        canceled = False
        cancel_fn = getattr(self.task_manager, "cancel", None)
        if callable(cancel_fn):
            try:
                result = cancel_fn(str(request.task_id), reason=request.reason)
                if asyncio.iscoroutine(result):
                    canceled = bool(await result)
                else:
                    canceled = bool(result)
            except Exception:
                canceled = False
        try:
            rec = await self.task_manager.get(str(request.task_id))
            status = self._map_task_status(rec.status)
        except TaskNotFoundError:
            status = TaskStatus.FAILED
        return TaskCancelResponse(
            task_id=str(request.task_id),
            status=status,
            canceled=canceled,
        )

    async def task_subscribe(
        self,
        request: TaskSubscribeRequest,
        context: ServerContext | None = None,
    ) -> AsyncGenerator[TaskEvent, None]:
        q = await self.task_manager.subscribe(str(request.task_id))
        try:
            while True:
                ev = await q.get()
                event_name, task = self._normalize_task_event(ev)
                if request.events and event_name not in request.events:
                    continue
                record = self._task_record_from_manager(task)
                ts = (
                    getattr(task, "completed_at_ms", None)
                    or getattr(task, "started_at_ms", None)
                    or getattr(task, "created_at_ms", None)
                    or int(time.time() * 1000)
                )
                yield TaskEvent(event=event_name, task=record, timestamp_ms=ts)
                if event_name == "completed" or record.is_terminal:
                    return
        finally:
            await self.task_manager.unsubscribe(str(request.task_id), q)

    async def health_check(
        self,
        request: HealthCheckRequest,
        context: ServerContext | None = None,
    ) -> HealthCheckResponse:
        service = request.service
        services: dict[str, str] = {}
        if service:
            services[str(service)] = HealthStatus.HEALTHY
        return HealthCheckResponse(status=HealthStatus.HEALTHY, services=services or None)

    async def health_watch(
        self,
        request: HealthCheckRequest,
        context: ServerContext | None = None,
    ) -> AsyncGenerator[HealthCheckResponse, None]:
        yield await self.health_check(request, context)

    async def _handle_task_method(self, context: RequestContext) -> AsyncGenerator[AduibRpcResponse, None]:
        data = context.request.data or {}
        request_meta = context.request.metadata if context.request else None
        method = request_meta.long_task_method if request_meta and request_meta.long_task_method else context.method

        if method == TaskMethod.SUBMIT_TASK:
            ttl_seconds = request_meta.long_task_timeout if request_meta else None
            rec = await self._submit_task(
                lambda: self.on_message(context.request, context.server_context),
                ttl_seconds=ttl_seconds,
            )
            result = {
                "task_id": rec.task_id,
                "status": rec.status.value,
                "created_at_ms": rec.created_at_ms,
            }
            yield AduibRpcResponse(id=context.request_id, status=ResponseStatus.SUCCESS, result=result)
            return

        if method in {TaskMethod.STATUS_TASK, TaskMethod.RESULT_TASK}:
            task_id = data.get("task_id")
            if not task_id:
                code = int(ErrorCode.MISSING_REQUIRED_FIELD)
                yield AduibRpcResponse(
                    id=context.request_id,
                    status=ResponseStatus.ERROR,
                    error=RpcError(
                        code=code, name=ERROR_CODE_NAMES.get(code, "UNKNOWN"), message="task_id is required"
                    ),
                )
                return
            try:
                rec = await self.task_manager.get(str(task_id))
            except TaskNotFoundError:
                code = int(ErrorCode.RESOURCE_NOT_FOUND)
                yield AduibRpcResponse(
                    id=context.request_id,
                    status=ResponseStatus.ERROR,
                    error=RpcError(
                        code=code,
                        name=ERROR_CODE_NAMES.get(code, "UNKNOWN"),
                        message="task not found",
                        details=[
                            {
                                "type": "aduib.rpc/task",
                                "field": "task_id",
                                "reason": "not found",
                                "metadata": {"task_id": task_id},
                            }
                        ],
                    ),
                )
                return

            updated_at_ms = (
                getattr(rec, "completed_at_ms", None)
                or getattr(rec, "started_at_ms", None)
                or getattr(rec, "created_at_ms", 0)
            )
            base = {
                "task_id": rec.task_id,
                "status": rec.status.value,
                "created_at_ms": rec.created_at_ms,
                "updated_at_ms": updated_at_ms,
            }

            if method == TaskMethod.STATUS_TASK:
                if rec.error is not None:
                    base["error"] = self._serialize_task_error(rec.error)
                yield AduibRpcResponse(id=context.request_id, status=ResponseStatus.SUCCESS, result=base)
                return

            # task/result
            if rec.status.value == "succeeded":
                base["value"] = rec.result
            elif rec.error is not None:
                base["error"] = self._serialize_task_error(rec.error)
            yield AduibRpcResponse(id=context.request_id, status=ResponseStatus.SUCCESS, result=base)
            return

        if method == TaskMethod.QUERY_TASK:
            task_id = data.get("task_id")
            if not task_id:
                code = int(ErrorCode.MISSING_REQUIRED_FIELD)
                yield AduibRpcResponse(
                    id=context.request_id,
                    status=ResponseStatus.ERROR,
                    error=RpcError(
                        code=code, name=ERROR_CODE_NAMES.get(code, "UNKNOWN"), message="task_id is required"
                    ),
                )
                return
            try:
                rec = await self.task_manager.get(str(task_id))
            except TaskNotFoundError:
                code = int(ErrorCode.RESOURCE_NOT_FOUND)
                yield AduibRpcResponse(
                    id=context.request_id,
                    status=ResponseStatus.ERROR,
                    error=RpcError(
                        code=code,
                        name=ERROR_CODE_NAMES.get(code, "UNKNOWN"),
                        message="task not found",
                        details=[
                            {
                                "type": "aduib.rpc/task",
                                "field": "task_id",
                                "reason": "not found",
                                "metadata": {"task_id": task_id},
                            }
                        ],
                    ),
                )
                return
            record = self._task_record_from_manager(rec)
            yield AduibRpcResponse(
                id=context.request_id,
                status=ResponseStatus.SUCCESS,
                result={"task": record.model_dump()},
            )
            return

        if method == TaskMethod.CANCEL_TASK:
            task_id = data.get("task_id")
            if not task_id:
                code = int(ErrorCode.MISSING_REQUIRED_FIELD)
                yield AduibRpcResponse(
                    id=context.request_id,
                    status=ResponseStatus.ERROR,
                    error=RpcError(
                        code=code, name=ERROR_CODE_NAMES.get(code, "UNKNOWN"), message="task_id is required"
                    ),
                )
                return
            cancel_resp = await self.task_cancel(
                TaskCancelRequest(task_id=str(task_id), reason=data.get("reason")),
                context.server_context,
            )
            yield AduibRpcResponse(
                id=context.request_id,
                status=ResponseStatus.SUCCESS,
                result=cancel_resp.model_dump(),
            )
            return
        if method == TaskMethod.SUBSCRIBE_TASK:
            async for resp in self._handle_task_subscribe(context):
                yield resp
            return

        code = int(ErrorCode.METHOD_NOT_FOUND)
        yield AduibRpcResponse(
            id=context.request_id,
            status=ResponseStatus.ERROR,
            error=RpcError(
                code=code,
                name=ERROR_CODE_NAMES.get(code, "UNKNOWN"),
                message=f"Unknown task method: {method}",
            ),
        )

    async def _handle_task_subscribe(self, context: RequestContext) -> AsyncGenerator[AduibRpcResponse, None]:
        data = context.request.data or {}
        task_id = data.get("task_id")
        if not task_id:
            code = int(ErrorCode.MISSING_REQUIRED_FIELD)
            yield AduibRpcResponse(
                id=context.request_id,
                status=ResponseStatus.ERROR,
                error=RpcError(code=code, name=ERROR_CODE_NAMES.get(code, "UNKNOWN"), message="task_id is required"),
            )
            return

        try:
            q = await self.task_manager.subscribe(str(task_id))
        except TaskNotFoundError:
            code = int(ErrorCode.RESOURCE_NOT_FOUND)
            yield AduibRpcResponse(
                id=context.request_id,
                status=ResponseStatus.ERROR,
                error=RpcError(
                    code=code,
                    name=ERROR_CODE_NAMES.get(code, "UNKNOWN"),
                    message="task not found",
                    details=[
                        {
                            "type": "aduib.rpc/task",
                            "field": "task_id",
                            "reason": "not found",
                            "metadata": {"task_id": task_id},
                        }
                    ],
                ),
            )
            return

        try:
            while True:
                ev = await q.get()
                event_name, task = self._normalize_task_event(ev)
                updated_at_ms = (
                    getattr(task, "completed_at_ms", None)
                    or getattr(task, "started_at_ms", None)
                    or getattr(task, "created_at_ms", 0)
                )
                payload = {
                    "event": event_name,
                    "task": {
                        "task_id": task.task_id,
                        "status": task.status.value,
                        "created_at_ms": task.created_at_ms,
                        "updated_at_ms": updated_at_ms,
                    },
                }
                if task.error is not None:
                    payload["task"]["error"] = self._serialize_task_error(task.error)
                if task.status.value == "succeeded":
                    payload["task"]["value"] = task.result

                yield AduibRpcResponse(id=context.request_id, status=ResponseStatus.SUCCESS, result=payload)

                if event_name == "completed" or task.status.value in {"succeeded", "failed", "canceled"}:
                    return
        finally:
            await self.task_manager.unsubscribe(str(task_id), q)

    def _setup_request_context(self, message: AduibRpcRequest, context: ServerContext | None = None) -> RequestContext:
        """Sets up and returns a RequestContext based on the provided ServerContext."""
        context_id: str = str(uuid.uuid4())
        request_id: str = message.id or str(uuid.uuid4())
        if message.id is None:
            message.id = request_id
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
            logger.warning("RequestExecutor for %s not found", context.model_name)
        return request_executor

    async def _dispatch_unary(
        self,
        message: AduibRpcRequest,
        server_context: ServerContext,
    ) -> AduibRpcResponse:
        request_context = self._setup_request_context(message, server_context)
        request_executor = self._validate_request_executor(request_context)

        if self._is_long_task(message):
            response = self._handle_task_method(request_context)
            if inspect.isawaitable(response):
                response = await response
            if hasattr(response, "__aiter__"):
                async for item in response:
                    return item
                return AduibRpcResponse(
                    id=request_context.request_id,
                    status=ResponseStatus.ERROR,
                    error=RpcError(
                        code=int(ErrorCode.INTERNAL_ERROR),
                        name=ERROR_CODE_NAMES.get(int(ErrorCode.INTERNAL_ERROR), "UNKNOWN"),
                        message="No response",
                    ),
                )
            return response

        if request_executor is None:
            compat = MethodName.parse_compat(message.method)
            service_caller = ServiceCaller.from_service_caller(compat.service)
            response = await service_caller.call(compat.handler, **(request_context.request.data or {}))
            return AduibRpcResponse(
                id=request_context.request_id,
                status=ResponseStatus.SUCCESS,
                result=response,
            )

        response = request_executor.execute(request_context)
        return AduibRpcResponse(
            id=request_context.request_id,
            status=ResponseStatus.SUCCESS,
            result=response,
        )

    async def _dispatch_stream(
        self,
        message: AduibRpcRequest,
        server_context: ServerContext,
    ) -> AsyncGenerator[AduibRpcResponse, None]:
        request_context = self._setup_request_context(message, server_context)
        request_executor = self._validate_request_executor(request_context)
        compat = MethodName.parse_compat(message.method)

        if self._is_long_task(message):
            response = self._handle_task_method(request_context)
            if inspect.isawaitable(response):
                response = await response
            async for resp in self._iter_stream_result(response, request_context.request_id):
                yield resp
            return

        if request_executor is None:
            service_caller = ServiceCaller.from_service_caller(compat.service)
            result = await service_caller.call(compat.handler, **(request_context.request.data or {}))
        else:
            result = request_executor.execute(request_context)
            if inspect.isawaitable(result):
                result = await result

        async for response in self._iter_stream_result(result, request_context.request_id):
            yield response

    async def _iter_stream_result(
        self,
        result: Any,
        request_id: str,
    ) -> AsyncGenerator[AduibRpcResponse, None]:
        if hasattr(result, "__aiter__"):
            async for item in result:
                yield self._coerce_stream_item(item, request_id)
            return
        yield self._coerce_stream_item(result, request_id)

    def _coerce_stream_item(
        self,
        item: Any,
        request_id: str,
    ) -> AduibRpcResponse:
        if isinstance(item, AduibRpcResponse):
            if item.id is None:
                item.id = request_id
            return item
        if isinstance(item, RpcError):
            return AduibRpcResponse(
                id=request_id,
                status=ResponseStatus.ERROR,
                error=item,
            )
        return AduibRpcResponse(
            id=request_id,
            status=ResponseStatus.SUCCESS,
            result=item,
        )

    async def _submit_task(
        self,
        coro_factory,
        *,
        ttl_seconds: int | None,
    ):
        # InMemoryTaskManager expects a callable returning an awaitable.
        return await self.task_manager.submit(lambda: coro_factory(), ttl_seconds=ttl_seconds)

    def _normalize_task_event(self, ev):
        if hasattr(ev, "event") and hasattr(ev, "task"):
            return ev.event, ev.task
        if isinstance(ev, dict) and "event" in ev and "task" in ev:
            return ev["event"], ev["task"]
        raise ValueError("Unsupported task event payload")

    def _serialize_task_error(self, error: Any) -> dict[str, Any]:
        if error is None:
            return {}
        if hasattr(error, "model_dump"):
            return error.model_dump()
        if isinstance(error, dict):
            return error
        return {"message": str(error)}

    def _resolve_health_method(self, method: str | None) -> str | None:
        if not method:
            return None
        try:
            parsed = MethodName.parse_compat(method)
        except Exception:
            return None
        service = parsed.service.lower()
        handler = parsed.handler.lower()
        if service in {"healthservice", "health"} and handler in {"check", "watch"}:
            return handler
        return None

    def _raise_for_error(self, response: AduibRpcResponse, message: str) -> None:
        if response.is_success():
            return
        err = response.error
        if err is None:
            raise RpcException(code=int(ErrorCode.INTERNAL_ERROR), message=message)
        data = err.model_dump() if hasattr(err, "model_dump") else {"code": err.code, "message": err.message}
        raise RpcException(code=int(err.code), message=err.message, data=data)

    def _map_task_status(self, status: Any) -> TaskStatus:
        raw = getattr(status, "value", status)
        value = str(raw).lower() if raw is not None else ""
        mapping = {
            "queued": TaskStatus.PENDING,
            "pending": TaskStatus.PENDING,
            "scheduled": TaskStatus.SCHEDULED,
            "running": TaskStatus.RUNNING,
            "retrying": TaskStatus.RETRYING,
            "succeeded": TaskStatus.SUCCEEDED,
            "failed": TaskStatus.FAILED,
            "canceled": TaskStatus.CANCELED,
            "expired": TaskStatus.FAILED,
        }
        return mapping.get(value, TaskStatus.PENDING)

    def _priority_from_manager(self, value: Any) -> Priority:
        try:
            num = int(value)
        except Exception:
            return Priority.NORMAL
        if num <= 0:
            return Priority.LOW
        if num == 1:
            return Priority.NORMAL
        if num == 2:
            return Priority.HIGH
        return Priority.CRITICAL

    def _task_record_from_manager(self, record: Any) -> TaskRecord:
        return TaskRecord(
            task_id=str(getattr(record, "task_id", "")),
            parent_task_id=None,
            status=self._map_task_status(getattr(record, "status", None)),
            priority=self._priority_from_manager(getattr(record, "priority", None)),
            created_at_ms=int(getattr(record, "created_at_ms", 0)),
            scheduled_at_ms=None,
            started_at_ms=getattr(record, "started_at_ms", None),
            completed_at_ms=getattr(record, "completed_at_ms", None),
            attempt=int(getattr(record, "retry_count", 0)) + 1,
            max_attempts=int(getattr(record, "max_retries", 0)) + 1,
            next_retry_at_ms=None,
            result=getattr(record, "result", None),
            error=getattr(record, "error", None),
            progress=None,
            metadata=getattr(record, "metadata", None),
            tags=None,
        )

    def _is_long_task(self, request: AduibRpcRequest) -> bool:
        """Determine if the request is for a long-running task."""
        return bool(request.metadata and request.metadata.long_task)
