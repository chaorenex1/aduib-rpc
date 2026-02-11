from __future__ import annotations

import asyncio
import json
import inspect
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from aduib_rpc.client.midwares import ClientContext
from aduib_rpc.client.transports.base import ClientTransport
from aduib_rpc.protocol.v2.types import AduibRpcResponse, ResponseStatus, RpcError
from aduib_rpc.protocol.v2.health import HealthCheckRequest, HealthCheckResponse, HealthStatus
from aduib_rpc.server.tasks import (
    TaskCancelRequest,
    TaskCancelResponse,
    TaskEvent,
    TaskProgress,
    TaskQueryRequest,
    TaskQueryResponse,
    TaskRecord,
    TaskStatus,
    TaskSubmitRequest,
    TaskSubmitResponse,
    TaskSubscribeRequest,
)
from aduib_rpc.server.tasks.types import TaskMethod
from aduib_rpc.types import AduibRpcRequest


def _parse_target(url: str) -> tuple[str, int]:
    if "://" in url:
        parsed = urlparse(url)
        host = parsed.hostname
        port = parsed.port
    else:
        host = None
        port = None
        if ":" in url:
            host_part, port_part = url.rsplit(":", 1)
            host = host_part
            try:
                port = int(port_part)
            except ValueError:
                port = None
        else:
            host = url
    if not host or port is None:
        raise ValueError(f"Invalid thrift target: {url!r}")
    return host, int(port)


def _status_from_thrift(value: int) -> ResponseStatus:
    if value == 2:
        return ResponseStatus.ERROR
    if value == 3:
        return ResponseStatus.PARTIAL
    return ResponseStatus.SUCCESS


def _rpc_error_from_thrift(error) -> RpcError:
    if error is None:
        return RpcError(code=0, name="UNKNOWN", message="")
    return RpcError(code=int(error.code), name=str(error.name), message=str(error.message))


def _response_from_thrift(resp) -> AduibRpcResponse:
    status = _status_from_thrift(int(resp.status or 0))
    result = None
    error = None
    payload = getattr(resp, "payload", None)
    if payload is not None:
        if getattr(payload, "error", None) is not None:
            error = _rpc_error_from_thrift(payload.error)
        elif getattr(payload, "result_json", None) is not None:
            try:
                result = json.loads(payload.result_json)
            except Exception:
                result = None
    return AduibRpcResponse(
        aduib_rpc=resp.aduib_rpc or "2.0",
        id=getattr(resp, "id", None),
        status=status,
        result=result,
        error=error,
    )


def _task_status_from_thrift(value: int) -> TaskStatus:
    return TaskStatus.from_thrift(value)


def _coerce_task_status(value: Any) -> TaskStatus:
    raw = getattr(value, "value", value)
    if isinstance(raw, TaskStatus):
        return raw
    if isinstance(raw, str):
        try:
            return TaskStatus(raw)
        except Exception:
            return TaskStatus.PENDING
    if isinstance(raw, int):
        return _task_status_from_thrift(raw)
    return TaskStatus.PENDING


def _task_progress_from_thrift(progress) -> TaskProgress | None:
    if progress is None:
        return None
    return TaskProgress(
        current=int(getattr(progress, "current", 0)),
        total=int(getattr(progress, "total", 0)),
        message=getattr(progress, "message", None),
        percentage=float(getattr(progress, "percentage", 0.0))
        if getattr(progress, "percentage", None) is not None
        else None,
    )


def _task_record_from_thrift(record) -> TaskRecord:
    result = None
    if getattr(record, "result_json", None):
        try:
            result = json.loads(record.result_json)
        except Exception:
            result = None
    error = getattr(record, "error", None)
    return TaskRecord(
        task_id=str(getattr(record, "task_id", "")),
        parent_task_id=getattr(record, "parent_task_id", None),
        status=_task_status_from_thrift(getattr(record, "status", 0)),
        priority=int(getattr(record, "priority", 0)),
        created_at_ms=int(getattr(record, "created_at_ms", 0)),
        scheduled_at_ms=getattr(record, "scheduled_at_ms", None),
        started_at_ms=getattr(record, "started_at_ms", None),
        completed_at_ms=getattr(record, "completed_at_ms", None),
        attempt=int(getattr(record, "attempt", 1)),
        max_attempts=int(getattr(record, "max_attempts", 3)),
        next_retry_at_ms=getattr(record, "next_retry_at_ms", None),
        result=result,
        error=error,
        progress=_task_progress_from_thrift(getattr(record, "progress", None)),
        metadata=dict(getattr(record, "metadata", None) or {}),
        tags=list(getattr(record, "tags", None) or []),
    )


class ThriftTransport(ClientTransport):
    """Thrift transport for Aduib RPC (v2 wire)."""

    def __init__(
        self,
        url: str,
        *,
        timeout_s: float | None = None,
        pool_minsize: int = 1,
        pool_maxsize: int = 10,
    ):
        self._host, self._port = _parse_target(url)
        self._timeout_s = timeout_s
        self._pool_minsize = pool_minsize
        self._pool_maxsize = pool_maxsize
        self._pool = None
        self._task_pool = None
        self._health_pool = None
        self._pool_lock = asyncio.Lock()
        self._thrift_module = None
        self._closed = False

    def _get_thrift_path(self) -> Path:
        return Path(__file__).resolve().parents[2] / "proto" / "aduib_rpc_v2.thrift"

    def _normalize_thrift_specs(self, module) -> None:
        try:
            values = module.__dict__.values()
        except Exception:
            return
        for obj in values:
            if not isinstance(obj, type):
                continue
            spec = getattr(obj, "thrift_spec", None)
            if isinstance(spec, (list, tuple)):
                obj.thrift_spec = {i: field for i, field in enumerate(spec) if field}

    def _load_thrift_module(self):
        if self._thrift_module is not None:
            return self._thrift_module
        try:
            import aiothrift
        except ImportError as exc:  # pragma: no cover
            raise RuntimeError("aiothrift is required for ThriftTransport") from exc
        thrift_path = self._get_thrift_path()
        self._thrift_module = aiothrift.load(str(thrift_path), module_name="aduib_rpc_v2_thrift")
        self._normalize_thrift_specs(self._thrift_module)
        return self._thrift_module

    def _request_to_thrift(self, request: AduibRpcRequest):
        from aduib_rpc.utils.thrift_v2_utils import ToThrift

        module = self._load_thrift_module()
        return ToThrift.request(request, ttypes=module)

    def _build_multiplexed_proto_factory(self, service_name: str):
        try:
            from thriftpy2.protocol import TBinaryProtocolFactory
        except Exception:
            return None

        base_factory = TBinaryProtocolFactory()

        class _MultiplexedProtocol:
            __slots__ = ("_proto", "_service")

            def __init__(self, proto):
                self._proto = proto
                self._service = service_name

            def write_message_begin(self, name, ttype, seqid):
                return self._proto.write_message_begin(
                    f"{self._service}:{name}", ttype, seqid
                )

            def writeMessageBegin(self, name, ttype, seqid):
                return self._proto.writeMessageBegin(
                    f"{self._service}:{name}", ttype, seqid
                )

            def __getattr__(self, item):
                return getattr(self._proto, item)

        class _MultiplexedProtocolFactory:
            __slots__ = ("_factory",)

            def __init__(self, factory):
                self._factory = factory

            def get_protocol(self, trans):
                return _MultiplexedProtocol(self._factory.get_protocol(trans))

        return _MultiplexedProtocolFactory(base_factory)

    def _make_multiplexed_protocol_cls(self, service_name: str):
        try:
            from aiothrift.protocol import TBinaryProtocol
            from thriftpy2.protocol.multiplex import TMultiplexedProtocol
        except Exception:
            return None

        class _MultiplexedProtocol:
            __slots__ = ("_proto",)

            def __init__(self, trans):
                base = TBinaryProtocol(trans)
                self._proto = TMultiplexedProtocol(base, service_name)

            def __getattr__(self, item):
                return getattr(self._proto, item)

        return _MultiplexedProtocol

    async def _create_multiplexed_pool(self, service, *, service_name: str):
        try:
            import aiothrift
            from aiothrift.pool import ThriftPool
            from aiothrift.connection import create_connection
        except ImportError as exc:  # pragma: no cover
            raise RuntimeError("aiothrift is required for ThriftTransport") from exc

        protocol_cls = self._make_multiplexed_protocol_cls(service_name)
        if protocol_cls is None:
            raise RuntimeError("Thrift multiplexed protocol is unavailable")

        class _MultiplexedPool(ThriftPool):
            def __init__(self, *args, **kwargs):
                self._protocol_cls = kwargs.pop("protocol_cls")
                super().__init__(*args, **kwargs)

            def _create_new_connection(self):
                return create_connection(
                    self._service,
                    self._address,
                    timeout=self._timeout,
                    framed=self._framed,
                    protocol_cls=self._protocol_cls,
                )

        pool = _MultiplexedPool(
            service,
            (self._host, self._port),
            minsize=self._pool_minsize,
            maxsize=self._pool_maxsize,
            timeout=self._timeout_s,
            framed=False,
            protocol_cls=protocol_cls,
        )
        try:
            await pool.fill_free(override_min=False)
        except Exception:
            pool.close()
            raise
        return pool

    async def _create_pool(self, service, *, service_name: str | None):
        try:
            import aiothrift
        except ImportError as exc:  # pragma: no cover
            raise RuntimeError("aiothrift is required for ThriftTransport") from exc

        if service_name:
            return await self._create_multiplexed_pool(service, service_name=service_name)

        kwargs: dict[str, Any] = {
            "address": (self._host, self._port),
            "minsize": self._pool_minsize,
            "maxsize": self._pool_maxsize,
        }
        if self._timeout_s is not None:
            kwargs["timeout"] = self._timeout_s

        proto_factory = None
        if service_name:
            proto_factory = self._build_multiplexed_proto_factory(service_name)

        try:
            import inspect

            sig = inspect.signature(aiothrift.create_pool)
            if proto_factory is not None:
                if "proto_factory" in sig.parameters:
                    kwargs["proto_factory"] = proto_factory
                elif "protocol_factory" in sig.parameters:
                    kwargs["protocol_factory"] = proto_factory
        except Exception:
            pass

        return await aiothrift.create_pool(service, **kwargs)

    async def _get_client(self):
        if self._closed:
            raise RuntimeError("ThriftTransport is closed")
        if self._pool is not None and not self._is_pool_closed(self._pool):
            return self._pool
        async with self._pool_lock:
            if self._pool is not None and not self._is_pool_closed(self._pool):
                return self._pool
            if self._is_pool_closed(self._pool):
                self._pool = None
            module = self._load_thrift_module()
            self._pool = await self._create_pool(
                module.AduibRpcService,
                service_name="AduibRpcService",
            )
            return self._pool

    async def _get_task_client(self):
        if self._closed:
            raise RuntimeError("ThriftTransport is closed")
        if self._task_pool is not None and not self._is_pool_closed(self._task_pool):
            return self._task_pool
        async with self._pool_lock:
            if self._task_pool is not None and not self._is_pool_closed(self._task_pool):
                return self._task_pool
            if self._is_pool_closed(self._task_pool):
                self._task_pool = None
            module = self._load_thrift_module()
            self._task_pool = await self._create_pool(
                module.TaskService,
                service_name="TaskService",
            )
            return self._task_pool

    async def _get_health_client(self):
        if self._closed:
            raise RuntimeError("ThriftTransport is closed")
        if self._health_pool is not None and not self._is_pool_closed(self._health_pool):
            return self._health_pool
        async with self._pool_lock:
            if self._health_pool is not None and not self._is_pool_closed(self._health_pool):
                return self._health_pool
            if self._is_pool_closed(self._health_pool):
                self._health_pool = None
            module = self._load_thrift_module()
            self._health_pool = await self._create_pool(
                module.HealthService,
                service_name="HealthService",
            )
            return self._health_pool

    @staticmethod
    def _is_pool_closed(pool) -> bool:
        if pool is None:
            return True
        return bool(getattr(pool, "closed", False))

    async def _close_pool(self, pool) -> None:
        if pool is None:
            return
        try:
            close = getattr(pool, "close", None)
            if callable(close):
                close()
        finally:
            wait_closed = getattr(pool, "wait_closed", None)
            if callable(wait_closed):
                result = wait_closed()
                if inspect.isawaitable(result):
                    await result

    async def aclose(self) -> None:
        if self._closed:
            return
        self._closed = True
        async with self._pool_lock:
            pools = (self._pool, self._task_pool, self._health_pool)
            self._pool = None
            self._task_pool = None
            self._health_pool = None
        for pool in pools:
            await self._close_pool(pool)

    async def close(self) -> None:
        await self.aclose()

    async def completion(
        self,
        request: AduibRpcRequest,
        *,
        context: ClientContext,
    ) -> AduibRpcResponse:
        client = await self._get_client()
        resp = await client.Call(self._request_to_thrift(request))
        return _response_from_thrift(resp)

    async def call(
        self,
        request: AduibRpcRequest,
        *,
        context: ClientContext,
    ) -> AduibRpcResponse:
        client = await self._get_client()
        resp = await client.Call(self._request_to_thrift(request))
        return _response_from_thrift(resp)

    async def completion_stream(
        self,
        request: AduibRpcRequest,
        *,
        context: ClientContext,
    ):
        client = await self._get_client()
        items = await client.CallServerStream(self._request_to_thrift(request))
        responses = [_response_from_thrift(item) for item in (items or [])]
        for response in responses:
            yield response

    async def call_server_stream(
        self,
        request: AduibRpcRequest,
        *,
        context: ClientContext,
    ):
        client = await self._get_client()
        items = await client.CallServerStream(self._request_to_thrift(request))
        responses = [_response_from_thrift(item) for item in (items or [])]
        for response in responses:
            yield response

    async def call_client_stream(
        self,
        requests,
        *,
        context: ClientContext,
    ) -> AduibRpcResponse:
        items = [req async for req in requests]
        if not items:
            raise ValueError("request stream is empty")
        client = await self._get_client()
        thrift_requests = [self._request_to_thrift(req) for req in items]
        resp = await client.CallClientStream(thrift_requests)
        return _response_from_thrift(resp)

    async def call_bidirectional(
        self,
        requests,
        *,
        context: ClientContext,
    ):
        items = [req async for req in requests]
        if not items:
            raise ValueError("request stream is empty")
        client = await self._get_client()
        thrift_requests = [self._request_to_thrift(req) for req in items]
        resp = await client.CallBidirectional(thrift_requests)
        responses = [_response_from_thrift(item) for item in (resp or [])]
        for response in responses:
            yield response

    async def task_submit(
        self,
        submit: TaskSubmitRequest,
        *,
        context: ClientContext,
    ) -> TaskSubmitResponse:
        module = self._load_thrift_module()
        req = module.TaskSubmitRequest(
            target_method=str(submit.target_method),
            params_json=json.dumps(submit.params or {}, ensure_ascii=False),
            priority=int(getattr(submit.priority, "value", submit.priority)),
        )

        client = await self._get_task_client()
        resp = await client.Submit(req)
        return TaskSubmitResponse(
            task_id=str(getattr(resp, "task_id", "")),
            status=_coerce_task_status(getattr(resp, "status", TaskStatus.PENDING)),
            created_at_ms=int(getattr(resp, "created_at_ms", 0)),
        )

    async def task_query(
        self,
        query: TaskQueryRequest,
        *,
        context: ClientContext,
    ) -> TaskQueryResponse:
        module = self._load_thrift_module()
        req = module.TaskQueryRequest(task_id=str(query.task_id))
        client = await self._get_task_client()
        resp = await client.Query(req)
        record = _task_record_from_thrift(resp.task)
        return TaskQueryResponse(task=record)

    async def task_cancel(
        self,
        cancel: TaskCancelRequest,
        *,
        context: ClientContext,
    ) -> TaskCancelResponse:
        module = self._load_thrift_module()
        req = module.TaskCancelRequest(task_id=str(cancel.task_id))
        if cancel.reason is not None:
            req.reason = str(cancel.reason)
        client = await self._get_task_client()
        resp = await client.Cancel(req)
        return TaskCancelResponse(
            task_id=str(getattr(resp, "task_id", cancel.task_id)),
            status=_coerce_task_status(getattr(resp, "status", TaskStatus.FAILED)),
            canceled=bool(getattr(resp, "canceled", False)),
        )

    async def task_subscribe(
        self,
        sub: TaskSubscribeRequest,
        *,
        context: ClientContext,
    ):
        module = self._load_thrift_module()
        req = module.TaskSubscribeRequest(task_id=str(sub.task_id))
        if sub.events:
            req.events = [str(ev) for ev in sub.events]
        client = await self._get_task_client()
        items = await client.Subscribe(req)
        for item in (items or []):
            record = _task_record_from_thrift(item.task)
            yield TaskEvent(event=item.event, task=record, timestamp_ms=int(item.timestamp_ms))

    async def health_check(self, request: HealthCheckRequest, *, context: ClientContext) -> HealthCheckResponse:
        module = self._load_thrift_module()
        req = module.HealthCheckRequest()
        if hasattr(req, "service_name"):
            req.service_name = request.service
        else:
            req.service = request.service
        client = await self._get_health_client()
        resp = await client.Check(req)
        services = {str(k): _health_status_from_thrift(v) for k, v in (resp.services or {}).items()}
        return HealthCheckResponse(status=_health_status_from_thrift(resp.status), services=services or None)

    async def health_watch(self, request: HealthCheckRequest, *, context: ClientContext):
        module = self._load_thrift_module()
        req = module.HealthCheckRequest()
        if hasattr(req, "service_name"):
            req.service_name = request.service
        else:
            req.service = request.service
        client = await self._get_health_client()
        items = await client.Watch(req)
        for item in (items or []):
            services = {str(k): _health_status_from_thrift(v) for k, v in (item.services or {}).items()}
            yield HealthCheckResponse(status=_health_status_from_thrift(item.status), services=services or None)


def _health_status_from_thrift(value: int) -> HealthStatus:
    return HealthStatus.from_thrift(value)
