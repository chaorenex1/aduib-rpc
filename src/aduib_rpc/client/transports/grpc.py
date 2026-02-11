import logging
from typing import Any

from google.protobuf import json_format
from google.protobuf import struct_pb2
from grpc.aio import Channel

from aduib_rpc.client import ClientContext, ClientRequestInterceptor
from aduib_rpc.client.call_options import resolve_timeout_s
from aduib_rpc.client.config import ClientConfig
from aduib_rpc.client.transports.base import ClientTransport
from aduib_rpc.grpc import aduib_rpc_v2_pb2_grpc, aduib_rpc_v2_pb2
from aduib_rpc.protocol.v2 import HealthStatus
from aduib_rpc.protocol.v2.health import HealthCheckRequest, HealthCheckResponse
from aduib_rpc.protocol.v2.types import (
    AduibRpcRequest as V2Request,
    AduibRpcResponse as V2Response,
)
from aduib_rpc.utils.grpc_v2_utils import FromProto, ToProto
from aduib_rpc.server.tasks import (
    TaskCancelRequest,
    TaskCancelResponse,
    TaskEvent,
    TaskQueryRequest,
    TaskQueryResponse,
    TaskSubmitRequest,
    TaskSubmitResponse,
    TaskSubscribeRequest,
    TaskStatus,
)

logger = logging.getLogger(__name__)


class GrpcTransport(ClientTransport):
    """A gRPC transport for the Aduib RPC client (v2 wire)."""

    def __init__(
        self,
        channel: Channel,
    ):
        self.channel = channel
        self.stub = aduib_rpc_v2_pb2_grpc.AduibRpcServiceStub(channel)
        self.task_stub = aduib_rpc_v2_pb2_grpc.TaskServiceStub(channel)
        self.health_stub = aduib_rpc_v2_pb2_grpc.HealthServiceStub(channel)

    @classmethod
    def create(
        cls,
        url: str,
        config: ClientConfig,
        interceptors: list[ClientRequestInterceptor],
    ) -> "GrpcTransport":
        if config.grpc_channel_factory is None:
            raise ValueError("grpc_channel_factory is required when using gRPC")
        channel = config.grpc_channel_factory(url)
        if channel is None:
            raise ValueError("grpc_channel_factory returned None")
        return cls(channel)

    def _build_grpc_metadata(self, meta: dict[str, Any] | None) -> list[tuple[str, str]]:
        grpc_metadata: list[tuple[str, str]] = []
        if meta:
            for key, value in meta.items():
                grpc_metadata.append((str(key), str(value)))

        try:
            from aduib_rpc.telemetry.grpc_metadata import inject_otel_to_grpc_metadata

            grpc_metadata = inject_otel_to_grpc_metadata(grpc_metadata)
        except Exception:
            pass
        return grpc_metadata

    def _resolve_deadline(self, request: V2Request | None, context: ClientContext) -> float | None:
        cfg_timeout = getattr(context.state.get("config"), "grpc_timeout", None)
        meta = request.meta if request is not None else None
        return resolve_timeout_s(config_timeout_s=cfg_timeout, meta=meta, context_http_kwargs=None)

    async def completion(self, request: V2Request, *, context: ClientContext) -> V2Response:
        grpc_metadata = self._build_grpc_metadata(request.meta)
        deadline = self._resolve_deadline(request, context)
        resp = await self.stub.Call(ToProto.request(request), metadata=grpc_metadata, timeout=deadline)
        return FromProto.response(resp)

    async def call(self, request: V2Request, *, context: ClientContext) -> V2Response:
        grpc_metadata = self._build_grpc_metadata(request.meta)
        deadline = self._resolve_deadline(request, context)
        resp = await self.stub.Call(ToProto.request(request), metadata=grpc_metadata, timeout=deadline)
        return FromProto.response(resp)

    async def completion_stream(self, request: V2Request, *, context: ClientContext):
        grpc_metadata = self._build_grpc_metadata(request.meta)
        deadline = self._resolve_deadline(request, context)
        req_msg = ToProto.request(request)
        stream = self.stub.CallServerStream(req_msg, metadata=grpc_metadata, timeout=deadline)

        async for msg in stream:
            yield FromProto.response(msg)

    async def call_server_stream(
        self,
        request: V2Request,
        *,
        context: ClientContext,
    ):
        grpc_metadata = self._build_grpc_metadata(request.meta)
        deadline = self._resolve_deadline(request, context)
        req_msg = ToProto.request(request)
        stream = self.stub.CallServerStream(req_msg, metadata=grpc_metadata, timeout=deadline)
        async for msg in stream:
            yield FromProto.response(msg)

    async def call_client_stream(
        self,
        requests,
        *,
        context: ClientContext,
    ) -> V2Response:
        iterator = requests.__aiter__()
        try:
            first = await iterator.__anext__()
        except StopAsyncIteration:
            raise ValueError("request stream is empty")

        grpc_metadata = self._build_grpc_metadata(getattr(first, "meta", None))
        deadline = self._resolve_deadline(first, context)

        async def _iter():
            yield ToProto.request(first)
            async for req in iterator:
                yield ToProto.request(req)

        resp = await self.stub.CallClientStream(_iter(), metadata=grpc_metadata, timeout=deadline)
        return FromProto.response(resp)

    async def call_bidirectional(
        self,
        requests,
        *,
        context: ClientContext,
    ):
        iterator = requests.__aiter__()
        try:
            first = await iterator.__anext__()
        except StopAsyncIteration:
            raise ValueError("request stream is empty")

        grpc_metadata = self._build_grpc_metadata(getattr(first, "meta", None))
        deadline = self._resolve_deadline(first, context)

        async def _iter():
            yield ToProto.request(first)
            async for req in iterator:
                yield ToProto.request(req)

        stream = self.stub.CallBidirectional(_iter(), metadata=grpc_metadata, timeout=deadline)
        async for msg in stream:
            yield FromProto.response(msg)

    async def task_submit(self, submit: TaskSubmitRequest, *, context: ClientContext) -> TaskSubmitResponse:
        msg = ToProto.task_submit_request(submit)
        grpc_metadata = self._build_grpc_metadata(None)
        deadline = self._resolve_deadline(None, context)
        resp = await self.task_stub.Submit(msg, metadata=grpc_metadata, timeout=deadline)
        return FromProto.task_submit_response(resp)

    async def task_query(self, query: TaskQueryRequest, *, context: ClientContext) -> TaskQueryResponse:
        msg = aduib_rpc_v2_pb2.TaskQueryRequest(task_id=str(query.task_id))
        grpc_metadata = self._build_grpc_metadata(None)
        deadline = self._resolve_deadline(None, context)
        resp = await self.task_stub.Query(msg, metadata=grpc_metadata, timeout=deadline)
        return TaskQueryResponse(task=FromProto.task_record(resp.task))

    async def task_cancel(
        self,
        cancel: TaskCancelRequest,
        *,
        context: ClientContext,
    ) -> TaskCancelResponse:
        msg = aduib_rpc_v2_pb2.TaskCancelRequest(task_id=str(cancel.task_id))
        if cancel.reason is not None:
            msg.reason = str(cancel.reason)
        grpc_metadata = self._build_grpc_metadata(None)
        deadline = self._resolve_deadline(None, context)
        resp = await self.task_stub.Cancel(msg, metadata=grpc_metadata, timeout=deadline)
        return TaskCancelResponse(
            task_id=resp.task_id,
            status=TaskStatus.from_proto(resp.status),
            canceled=bool(resp.canceled),
        )

    async def task_subscribe(
        self,
        sub: TaskSubscribeRequest,
        *,
        context: ClientContext,
    ):
        msg = aduib_rpc_v2_pb2.TaskSubscribeRequest(task_id=str(sub.task_id))
        if sub.events:
            msg.events.extend([str(ev) for ev in sub.events])
        grpc_metadata = self._build_grpc_metadata(None)
        deadline = self._resolve_deadline(None, context)
        stream = self.task_stub.Subscribe(msg, metadata=grpc_metadata, timeout=deadline)
        async for item in stream:
            task = FromProto.task_record(item.task)
            yield TaskEvent(event=item.event, task=task, timestamp_ms=int(item.timestamp_ms))

    async def health_check(self, request: HealthCheckRequest, *, context: ClientContext) -> HealthCheckResponse:
        msg = aduib_rpc_v2_pb2.HealthCheckRequest()
        msg.service = request.service

        grpc_metadata = self._build_grpc_metadata(None)
        deadline = self._resolve_deadline(None, context)
        resp = await self.health_stub.Check(msg, metadata=grpc_metadata, timeout=deadline)
        services = {k: HealthStatus.from_proto(v) for k, v in resp.services.items()}
        return HealthCheckResponse(status=HealthStatus.from_proto(resp.status), services=services or None)

    async def health_watch(self, request: HealthCheckRequest, *, context: ClientContext):
        msg = aduib_rpc_v2_pb2.HealthCheckRequest()
        msg.service = request.service

        grpc_metadata = self._build_grpc_metadata(None)
        deadline = self._resolve_deadline(None, context)
        stream = self.health_stub.Watch(msg, metadata=grpc_metadata, timeout=deadline)
        async for resp in stream:
            services = {k: HealthStatus.from_proto(v) for k, v in resp.services.items()}
            yield HealthCheckResponse(status=HealthStatus.from_proto(resp.status), services=services or None)
