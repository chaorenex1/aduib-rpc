from __future__ import annotations

import contextlib
import json
import logging
from collections.abc import AsyncIterator

import grpc

from aduib_rpc.grpc import aduib_rpc_v2_pb2
from aduib_rpc.grpc.aduib_rpc_v2_pb2_grpc import (
    AduibRpcServiceServicer,
    HealthServiceServicer,
    TaskServiceServicer,
)
from aduib_rpc.protocol.v2.errors import error_code_to_grpc_status
from aduib_rpc.protocol.v2.types import AduibRpcResponse as V2Response
from aduib_rpc.protocol.v2.types import ResponseStatus
from aduib_rpc.server.context import ServerContext
from aduib_rpc.server.request_handlers.request_handler import RequestHandler
from aduib_rpc.utils.error_handlers import exception_to_error
from aduib_rpc.utils.grpc_v2_utils import FromProto as GrpcFromProto
from aduib_rpc.utils.grpc_v2_utils import ToProto as GrpcToProto

logger = logging.getLogger(__name__)


class DefaultGrpcV2ServerContextBuilder:
    def build_context(
        self,
        context: grpc.aio.ServicerContext,
        request: object | None = None,
    ) -> ServerContext:
        state: dict[str, object] = {}
        metadata: dict[str, str] = {}
        with contextlib.suppress(Exception):
            state["grpc_context"] = context
            metadata = {str(k): str(v) for k, v in (context.invocation_metadata() or ())}
            state["headers"] = metadata
        server_context = ServerContext(state=state, metadata=metadata)
        if request is not None:
            self._attach_request_metadata(server_context, request)
        else:
            self._attach_tenant_from_headers(server_context)
        return server_context

    def _attach_request_metadata(self, context: ServerContext, request: object) -> None:
        metadata = getattr(request, "metadata", None)
        tenant_id = getattr(metadata, "tenant_id", None) if metadata is not None else None
        if tenant_id:
            context.state["tenant_id"] = str(tenant_id)
            return
        self._attach_tenant_from_headers(context)

    @staticmethod
    def _attach_tenant_from_headers(context: ServerContext) -> None:
        headers = context.state.get("headers", {}) or {}
        tenant_id = (
            headers.get("X-Tenant-ID")
            or headers.get("x-tenant-id")
            or headers.get("X-Tenant")
            or headers.get("x-tenant")
        )
        if tenant_id:
            context.state["tenant_id"] = str(tenant_id)


class GrpcV2Handler(AduibRpcServiceServicer):
    """Pure v2 gRPC handler."""

    def __init__(
        self,
        request_handler: RequestHandler,
        context_builder: DefaultGrpcV2ServerContextBuilder | None = None,
    ) -> None:
        self.request_handler = request_handler
        self.context_builder = context_builder or DefaultGrpcV2ServerContextBuilder()

    async def Call(
        self,
        request: aduib_rpc_v2_pb2.Request,
        context: grpc.aio.ServicerContext,
    ) -> aduib_rpc_v2_pb2.Response:
        try:
            req = GrpcFromProto.request(request)
            server_context = self.context_builder.build_context(context, req)
            resp: V2Response = await self.request_handler.on_message(req, server_context)
            return GrpcToProto.response(resp)
        except Exception as exc:
            logger.exception("Error processing gRPC v2 Call")
            err = exception_to_error(exc)
            resp = V2Response(
                aduib_rpc="2.0",
                id=request.id,
                status=ResponseStatus.ERROR,
                error=err,
            )
            return GrpcToProto.response(resp)

    async def CallServerStream(
        self,
        request: aduib_rpc_v2_pb2.Request,
        context: grpc.aio.ServicerContext,
    ) -> AsyncIterator[aduib_rpc_v2_pb2.Response]:
        try:
            req = GrpcFromProto.request(request)
            server_context = self.context_builder.build_context(context, req)
            async for resp in self.request_handler.on_stream_message(req, server_context):
                yield GrpcToProto.response(resp)
        except Exception as exc:
            logger.exception("Error processing gRPC v2 CallServerStream")
            err = exception_to_error(exc)
            yield GrpcToProto.response(
                V2Response(
                    aduib_rpc="2.0",
                    id=request.id,
                    status=ResponseStatus.ERROR,
                    error=err,
                )
            )

    async def CallClientStream(self, request_iterator, context):
        try:
            iterator = request_iterator.__aiter__()
            try:
                first = await iterator.__anext__()
            except StopAsyncIteration:
                err = exception_to_error(ValueError("request stream is empty"))
                resp = V2Response(
                    aduib_rpc="2.0",
                    id="",
                    status=ResponseStatus.ERROR,
                    error=err,
                )
                return GrpcToProto.response(resp)

            req_first = GrpcFromProto.request(first)
            server_context = self.context_builder.build_context(context, req_first)

            async def _iter():
                yield req_first
                async for msg in iterator:
                    yield GrpcFromProto.request(msg)

            resp: V2Response = await self.request_handler.call_client_stream(_iter(), server_context)
            return GrpcToProto.response(resp)
        except Exception as exc:
            logger.exception("Error processing gRPC v2 CallClientStream")
            err = exception_to_error(exc)
            resp = V2Response(
                aduib_rpc="2.0",
                id=getattr(first, "id", "") if "first" in locals() else "",
                status=ResponseStatus.ERROR,
                error=err,
            )
            return GrpcToProto.response(resp)

    async def CallBidirectional(self, request_iterator, context) -> AsyncIterator[aduib_rpc_v2_pb2.Response]:
        try:
            iterator = request_iterator.__aiter__()
            try:
                first = await iterator.__anext__()
            except StopAsyncIteration:
                err = exception_to_error(ValueError("request stream is empty"))
                yield GrpcToProto.response(
                    V2Response(
                        aduib_rpc="2.0",
                        id="",
                        status=ResponseStatus.ERROR,
                        error=err,
                    )
                )
                return

            req_first = GrpcFromProto.request(first)
            server_context = self.context_builder.build_context(context, req_first)

            async def _iter():
                yield req_first
                async for msg in iterator:
                    yield GrpcFromProto.request(msg)

            async for resp in self.request_handler.call_bidirectional(_iter(), server_context):
                yield GrpcToProto.response(resp)
        except Exception as exc:
            logger.exception("Error processing gRPC v2 CallBidirectional")
            err = exception_to_error(exc)
            yield GrpcToProto.response(
                V2Response(
                    aduib_rpc="2.0",
                    id=getattr(first, "id", "") if "first" in locals() else "",
                    status=ResponseStatus.ERROR,
                    error=err,
                )
            )


class GrpcV2TaskHandler(TaskServiceServicer):
    """TaskService gRPC handler wired to RequestHandler."""

    def __init__(
        self,
        request_handler: RequestHandler,
        context_builder: DefaultGrpcV2ServerContextBuilder | None = None,
    ) -> None:
        self.request_handler = request_handler
        self.context_builder = context_builder or DefaultGrpcV2ServerContextBuilder()

    async def Submit(self, request, context):
        try:
            submit = GrpcFromProto.task_submit_request(request)
            server_context = self.context_builder.build_context(context, submit)
            resp = await self.request_handler.task_submit(submit, server_context)
            return aduib_rpc_v2_pb2.TaskSubmitResponse(
                task_id=str(GrpcToProto.read_attr(resp, "task_id", "")),
                status=GrpcToProto.task_status(GrpcToProto.read_attr(resp, "status", None)),
                created_at_ms=int(GrpcToProto.read_attr(resp, "created_at_ms", 0)),
            )
        except Exception as exc:
            logger.exception("Error processing TaskService.Submit")
            err = exception_to_error(exc)
            status_name = error_code_to_grpc_status(int(err.code))
            status = getattr(grpc.StatusCode, status_name, grpc.StatusCode.UNKNOWN)
            details = json.dumps(err.model_dump(mode="json", exclude_none=True), ensure_ascii=False)
            await context.abort(status, details)

    async def Query(self, request, context):
        try:
            query = GrpcFromProto.task_query_request(request)
            server_context = self.context_builder.build_context(context, query)
            resp = await self.request_handler.task_query(query, server_context)
            task_value = GrpcToProto.read_attr(resp, "task", None)
            task = GrpcToProto.task_record(task_value) if task_value is not None else aduib_rpc_v2_pb2.TaskRecord()
            return aduib_rpc_v2_pb2.TaskQueryResponse(task=task)
        except Exception as exc:
            logger.exception("Error processing TaskService.Query")
            err = exception_to_error(exc)
            status_name = error_code_to_grpc_status(int(err.code))
            status = getattr(grpc.StatusCode, status_name, grpc.StatusCode.UNKNOWN)
            details = json.dumps(err.model_dump(mode="json", exclude_none=True), ensure_ascii=False)
            await context.abort(status, details)

    async def Cancel(self, request, context):
        try:
            cancel = GrpcFromProto.task_cancel_request(request)
            server_context = self.context_builder.build_context(context, cancel)
            resp = await self.request_handler.task_cancel(cancel, server_context)
            return aduib_rpc_v2_pb2.TaskCancelResponse(
                task_id=str(GrpcToProto.read_attr(resp, "task_id", "")),
                status=GrpcToProto.task_status(GrpcToProto.read_attr(resp, "status", None)),
                canceled=bool(GrpcToProto.read_attr(resp, "canceled", False)),
            )
        except Exception as exc:
            logger.exception("Error processing TaskService.Cancel")
            err = exception_to_error(exc)
            status_name = error_code_to_grpc_status(int(err.code))
            status = getattr(grpc.StatusCode, status_name, grpc.StatusCode.UNKNOWN)
            details = json.dumps(err.model_dump(mode="json", exclude_none=True), ensure_ascii=False)
            await context.abort(status, details)

    async def Subscribe(self, request, context):
        try:
            sub = GrpcFromProto.task_subscribe_request(request)
            server_context = self.context_builder.build_context(context, sub)
            async for event in self.request_handler.task_subscribe(sub, server_context):
                yield GrpcToProto.task_event(event)
        except Exception as exc:
            logger.exception("Error processing TaskService.Subscribe")
            err = exception_to_error(exc)
            status_name = error_code_to_grpc_status(int(err.code))
            status = getattr(grpc.StatusCode, status_name, grpc.StatusCode.UNKNOWN)
            details = json.dumps(err.model_dump(mode="json", exclude_none=True), ensure_ascii=False)
            await context.abort(status, details)


class GrpcV2HealthHandler(HealthServiceServicer):
    """HealthService gRPC handler wired to RequestHandler."""

    def __init__(
        self,
        request_handler: RequestHandler,
        context_builder: DefaultGrpcV2ServerContextBuilder | None = None,
    ) -> None:
        self.request_handler = request_handler
        self.context_builder = context_builder or DefaultGrpcV2ServerContextBuilder()

    async def Check(self, request, context):
        try:
            health = GrpcFromProto.health_request(request)
            server_context = self.context_builder.build_context(context, health)
            resp = await self.request_handler.health_check(health, server_context)
            return GrpcToProto.health_response(resp)
        except Exception as exc:
            logger.exception("Error processing HealthService.Check")
            err = exception_to_error(exc)
            status_name = error_code_to_grpc_status(int(err.code))
            status = getattr(grpc.StatusCode, status_name, grpc.StatusCode.UNKNOWN)
            details = json.dumps(err.model_dump(mode="json", exclude_none=True), ensure_ascii=False)
            await context.abort(status, details)

    async def Watch(self, request, context):
        try:
            health = GrpcFromProto.health_request(request)
            server_context = self.context_builder.build_context(context, health)
            async for item in self.request_handler.health_watch(health, server_context):
                yield GrpcToProto.health_response(item)
        except Exception as exc:
            logger.exception("Error processing HealthService.Watch")
            err = exception_to_error(exc)
            status_name = error_code_to_grpc_status(int(err.code))
            status = getattr(grpc.StatusCode, status_name, grpc.StatusCode.UNKNOWN)
            details = json.dumps(err.model_dump(mode="json", exclude_none=True), ensure_ascii=False)
            await context.abort(status, details)
