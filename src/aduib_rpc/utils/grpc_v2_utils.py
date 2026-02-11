from __future__ import annotations

from typing import Any

from google.protobuf import json_format, struct_pb2

from aduib_rpc.grpc import aduib_rpc_v2_pb2
from aduib_rpc.protocol.v2.health import HealthCheckRequest, HealthCheckResponse, HealthStatus
from aduib_rpc.protocol.v2.metadata import (
    AuthContext,
    AuthScheme,
    RequestMetadata,
    ResponseMetadata,
)
from aduib_rpc.protocol.v2.qos import Priority, QosConfig
from aduib_rpc.protocol.v2.types import (
    AduibRpcRequest as V2Request,
    AduibRpcResponse as V2Response,
    DebugInfo,
    ErrorDetail,
    RpcError,
    ResponseStatus,
    TraceContext,
)
from aduib_rpc.resilience import RetryPolicy
from aduib_rpc.server.tasks.types import (
    TaskCancelRequest,
    TaskEvent,
    TaskProgress,
    TaskQueryRequest,
    TaskRecord,
    TaskStatus,
    TaskSubmitRequest,
    TaskSubscribeRequest,
    TaskSubmitResponse,
)


class FromProto:
    """Utility class for converting protobuf messages to native Python types."""

    @classmethod
    def struct_to_dict(cls, value: struct_pb2.Struct) -> dict:
        return json_format.MessageToDict(value)

    @classmethod
    def value(cls, value: struct_pb2.Value) -> Any:
        return json_format.MessageToDict(value)

    @classmethod
    def trace_context(cls, value: aduib_rpc_v2_pb2.TraceContext) -> TraceContext:
        payload: dict[str, Any] = {
            "trace_id": str(getattr(value, "trace_id", "") or ""),
            "span_id": str(getattr(value, "span_id", "") or ""),
            "sampled": bool(getattr(value, "sampled", True)),
        }
        if value.HasField("parent_span_id"):
            payload["parent_span_id"] = str(value.parent_span_id)
        baggage = dict(getattr(value, "baggage", None) or {})
        if baggage:
            payload["baggage"] = {str(k): str(v) for k, v in baggage.items()}
        return TraceContext(**payload)

    @classmethod
    def auth_context(cls, value: aduib_rpc_v2_pb2.AuthContext) -> AuthContext:
        payload: dict[str, Any] = {
            "scheme": AuthScheme.from_proto(getattr(value, "scheme", None)),
            "roles": list(value.roles) if getattr(value, "roles", None) else None,
        }
        if value.HasField("credentials"):
            payload["credentials"] = str(value.credentials)
        if value.HasField("principal"):
            payload["principal"] = str(value.principal)
        return AuthContext(**payload)

    @classmethod
    def error_detail(cls, value: aduib_rpc_v2_pb2.ErrorDetail) -> ErrorDetail:
        metadata = dict(value.metadata) if getattr(value, "metadata", None) else None
        payload: dict[str, Any] = {
            "type": str(getattr(value, "type", "") or ""),
            "reason": str(getattr(value, "reason", "") or ""),
            "metadata": metadata,
        }
        if value.HasField("field"):
            payload["field"] = str(value.field)
        return ErrorDetail(**payload)

    @classmethod
    def debug_info(cls, value: aduib_rpc_v2_pb2.DebugInfo) -> DebugInfo:
        payload: dict[str, Any] = {
            "timestamp_ms": int(getattr(value, "timestamp_ms", 0) or 0),
        }
        if value.HasField("stack_trace"):
            payload["stack_trace"] = str(value.stack_trace)
        if value.HasField("internal_message"):
            payload["internal_message"] = str(value.internal_message)
        return DebugInfo(**payload)

    @classmethod
    def rpc_error(cls, value: aduib_rpc_v2_pb2.RpcError) -> RpcError:
        details = [cls.error_detail(item) for item in value.details] if value.details else None
        debug = cls.debug_info(value.debug) if value.HasField("debug") else None
        return RpcError(
            code=int(getattr(value, "code", 0) or 0),
            name=str(getattr(value, "name", "") or "UNKNOWN"),
            message=str(getattr(value, "message", "") or ""),
            details=[item for item in details if item is not None] if details else None,
            debug=debug,
        )

    @classmethod
    def request_metadata(cls, value: aduib_rpc_v2_pb2.RequestMetadata) -> RequestMetadata:
        payload: dict[str, Any] = {
            "timestamp_ms": int(getattr(value, "timestamp_ms", 0) or 0),
            "long_task": bool(value.long_task) if value.HasField("long_task") else False,
        }
        if value.HasField("client_id"):
            payload["client_id"] = str(value.client_id)
        if value.HasField("client_version"):
            payload["client_version"] = str(value.client_version)
        if value.HasField("auth"):
            payload["auth"] = cls.auth_context(value.auth)
        if value.HasField("tenant_id"):
            payload["tenant_id"] = str(value.tenant_id)
        headers = dict(value.headers) if value.headers else None
        if headers:
            payload["headers"] = {str(k): str(v) for k, v in headers.items()}
        if value.HasField("long_task_method"):
            payload["long_task_method"] = str(value.long_task_method)
        if value.HasField("long_task_timeout"):
            payload["long_task_timeout"] = int(value.long_task_timeout)
        return RequestMetadata(**payload)

    @classmethod
    @classmethod
    def response_metadata(cls, value: aduib_rpc_v2_pb2.ResponseMetadata) -> ResponseMetadata:
        payload: dict[str, Any] = {
            "timestamp_ms": int(getattr(value, "timestamp_ms", 0) or 0),
            "duration_ms": int(getattr(value, "duration_ms", 0) or 0),
        }
        if value.HasField("server_id"):
            payload["server_id"] = str(value.server_id)
        if value.HasField("server_version"):
            payload["server_version"] = str(value.server_version)
        return ResponseMetadata(**payload)

    @classmethod
    def retry_policy(cls, value: aduib_rpc_v2_pb2.RetryConfig) -> RetryPolicy:
        defaults = RetryPolicy()
        max_attempts = int(getattr(value, "max_attempts", 0) or defaults.max_attempts)
        initial_delay_ms = int(getattr(value, "initial_delay_ms", 0) or defaults.initial_delay_ms)
        max_delay_ms = int(getattr(value, "max_delay_ms", 0) or defaults.max_delay_ms)
        backoff_multiplier = float(getattr(value, "backoff_multiplier", 0) or defaults.backoff_multiplier)
        retryable_codes = set(value.retryable_codes) if value.retryable_codes else None
        return RetryPolicy(
            max_attempts=max_attempts,
            initial_delay_ms=initial_delay_ms,
            max_delay_ms=max_delay_ms,
            backoff_multiplier=backoff_multiplier,
            retryable_codes=retryable_codes,
        )

    @classmethod
    def qos_config(cls, value: aduib_rpc_v2_pb2.QosConfig) -> QosConfig:
        retry = cls.retry_policy(value.retry) if value.HasField("retry") else None
        timeout_ms = int(value.timeout_ms) if value.HasField("timeout_ms") else None
        idempotency_key = str(value.idempotency_key) if value.HasField("idempotency_key") else None
        return QosConfig(
            priority=Priority.from_proto(value.priority),
            timeout_ms=timeout_ms,
            retry=retry,
            idempotency_key=idempotency_key,
        )

    @classmethod
    def request(cls, request: aduib_rpc_v2_pb2.Request) -> V2Request:
        return V2Request(
            aduib_rpc=request.aduib_rpc,
            id=request.id,
            method=request.method,
            name=request.name if request.HasField("name") else None,
            data=cls.struct_to_dict(request.data) if request.HasField("data") else None,
            trace_context=cls.trace_context(request.trace_context) if request.HasField("trace_context") else None,
            metadata=cls.request_metadata(request.metadata) if request.HasField("metadata") else None,
            qos=cls.qos_config(request.qos) if request.HasField("qos") else None,
        )

    @classmethod
    def pb2_request(cls, request: V2Request) -> aduib_rpc_v2_pb2.Request:
        return ToProto.request(request)

    @classmethod
    def task_submit_request(cls, value: aduib_rpc_v2_pb2.TaskSubmitRequest) -> TaskSubmitRequest:
        payload: dict[str, Any] = {
            "target_method": str(getattr(value, "target_method", "") or ""),
            "priority": Priority.from_proto(getattr(value, "priority", None)),
            "max_attempts": int(getattr(value, "max_attempts", 0) or 0),
        }
        if value.HasField("params"):
            payload["params"] = cls.struct_to_dict(value.params)
        if value.HasField("timeout_ms"):
            payload["timeout_ms"] = int(value.timeout_ms)
        if value.HasField("scheduled_at_ms"):
            payload["scheduled_at_ms"] = int(value.scheduled_at_ms)
        if value.HasField("idempotency_key"):
            payload["idempotency_key"] = str(value.idempotency_key)
        metadata = dict(value.metadata) if value.metadata else None
        if metadata:
            payload["metadata"] = {str(k): str(v) for k, v in metadata.items()}
        return TaskSubmitRequest.model_validate(payload)

    @classmethod
    def task_query_request(cls, value: aduib_rpc_v2_pb2.TaskQueryRequest) -> TaskQueryRequest:
        return TaskQueryRequest(task_id=str(getattr(value, "task_id", "") or ""))

    @classmethod
    def task_cancel_request(cls, value: aduib_rpc_v2_pb2.TaskCancelRequest) -> TaskCancelRequest:
        payload: dict[str, Any] = {
            "task_id": str(getattr(value, "task_id", "") or ""),
        }
        if value.HasField("reason"):
            payload["reason"] = str(value.reason)
        return TaskCancelRequest.model_validate(payload)

    @classmethod
    def task_subscribe_request(cls, value: aduib_rpc_v2_pb2.TaskSubscribeRequest) -> TaskSubscribeRequest:
        events = list(value.events) if value.events else None
        payload: dict[str, Any] = {"task_id": str(getattr(value, "task_id", "") or "")}
        if events:
            payload["events"] = [str(item) for item in events]
        return TaskSubscribeRequest.model_validate(payload)

    @classmethod
    def health_request(cls, value: aduib_rpc_v2_pb2.HealthCheckRequest) -> HealthCheckRequest:
        if value.HasField("service"):
            return HealthCheckRequest(service=str(value.service))
        return HealthCheckRequest()

    @classmethod
    def priority(cls, value: int) -> Priority:
        return Priority.from_proto(value)

    @classmethod
    def task_progress(cls, value: aduib_rpc_v2_pb2.TaskProgress) -> TaskProgress:
        payload: dict[str, Any] = {
            "current": int(getattr(value, "current", 0) or 0),
            "total": int(getattr(value, "total", 0) or 0),
        }
        if value.HasField("message"):
            payload["message"] = str(value.message)
        if value.HasField("percentage"):
            payload["percentage"] = float(value.percentage)
        return TaskProgress(**payload)

    @classmethod
    def task_record(cls, value: aduib_rpc_v2_pb2.TaskRecord) -> TaskRecord:
        payload: dict[str, Any] = {
            "task_id": str(getattr(value, "task_id", "") or ""),
            "status": TaskStatus.from_proto(getattr(value, "status", None)),
            "priority": Priority.from_proto(getattr(value, "priority", None)),
            "created_at_ms": int(getattr(value, "created_at_ms", 0) or 0),
            "attempt": int(getattr(value, "attempt", 0) or 0),
            "max_attempts": int(getattr(value, "max_attempts", 0) or 0),
        }
        if value.HasField("parent_task_id"):
            payload["parent_task_id"] = str(value.parent_task_id)
        if value.HasField("scheduled_at_ms"):
            payload["scheduled_at_ms"] = int(value.scheduled_at_ms)
        if value.HasField("started_at_ms"):
            payload["started_at_ms"] = int(value.started_at_ms)
        if value.HasField("completed_at_ms"):
            payload["completed_at_ms"] = int(value.completed_at_ms)
        if value.HasField("next_retry_at_ms"):
            payload["next_retry_at_ms"] = int(value.next_retry_at_ms)
        if value.HasField("result"):
            payload["result"] = cls.value(value.result)
        if value.HasField("error"):
            payload["error"] = cls.rpc_error(value.error)
        if value.HasField("progress"):
            payload["progress"] = cls.task_progress(value.progress)
        metadata = dict(value.metadata) if value.metadata else None
        if metadata:
            payload["metadata"] = {str(k): str(v) for k, v in metadata.items()}
        tags = list(value.tags) if value.tags else None
        if tags:
            payload["tags"] = [str(tag) for tag in tags]
        return TaskRecord(**payload)

    @classmethod
    def task_event(cls, value: aduib_rpc_v2_pb2.TaskEvent) -> TaskEvent:
        return TaskEvent(
            event=str(getattr(value, "event", "") or ""),
            task=cls.task_record(value.task),
            timestamp_ms=int(getattr(value, "timestamp_ms", 0) or 0),
        )

    @classmethod
    def response(cls, response: aduib_rpc_v2_pb2.Response) -> V2Response:
        payload_kind = response.WhichOneof("payload")
        result = None
        error = None
        if payload_kind == "result":
            result = cls.value(response.result)
        elif payload_kind == "error":
            error = cls.rpc_error(response.error)
        return V2Response(
            aduib_rpc=response.aduib_rpc or "2.0",
            id=response.id,
            status=ResponseStatus.from_proto(response.status),
            result=result,
            error=error,
            trace_context=cls.trace_context(response.trace_context) if response.HasField("trace_context") else None,
            metadata=cls.response_metadata(response.metadata) if response.HasField("metadata") else None,
        )

    @classmethod
    def health_response(cls, value: aduib_rpc_v2_pb2.HealthCheckResponse) -> HealthCheckResponse:
        services = {str(k): HealthStatus.from_proto(v) for k, v in value.services.items()} if value.services else None
        return HealthCheckResponse(
            status=HealthStatus.from_proto(getattr(value, "status", None)),
            services=services or None,
        )

    @classmethod
    def task_submit_response(cls, resp: aduib_rpc_v2_pb2.TaskSubmitResponse) -> TaskSubmitResponse:
        return TaskSubmitResponse(
            task_id=resp.task_id,
            status=TaskStatus.from_proto(resp.status),
            created_at_ms=int(resp.created_at_ms),
        )


class ToProto:
    """Utility class for converting native Python types to protobuf messages."""

    @staticmethod
    def read_attr(obj: Any, name: str, default: Any = None) -> Any:
        return getattr(obj, name, default)

    @classmethod
    def trace_context(cls, value: TraceContext) -> aduib_rpc_v2_pb2.TraceContext:
        payload = value.model_dump(exclude_none=True)
        msg = aduib_rpc_v2_pb2.TraceContext(
            trace_id=str(payload.get("trace_id") or ""),
            span_id=str(payload.get("span_id") or ""),
            sampled=bool(payload.get("sampled", True)),
        )
        if payload.get("parent_span_id") is not None:
            msg.parent_span_id = str(payload.get("parent_span_id"))
        baggage = payload.get("baggage") or {}
        if isinstance(baggage, dict):
            msg.baggage.update({str(k): str(v) for k, v in baggage.items()})
        return msg

    @classmethod
    def auth_context(cls, value: AuthContext) -> aduib_rpc_v2_pb2.AuthContext:
        payload = value.model_dump(exclude_none=True)
        msg = aduib_rpc_v2_pb2.AuthContext(
            scheme=AuthScheme.to_proto(payload.get("scheme")),
        )
        if payload.get("credentials") is not None:
            msg.credentials = str(payload.get("credentials"))
        if payload.get("principal") is not None:
            msg.principal = str(payload.get("principal"))
        roles = payload.get("roles") or []
        if roles:
            msg.roles.extend([str(role) for role in roles])
        return msg

    @classmethod
    def request_metadata(cls, value: RequestMetadata) -> aduib_rpc_v2_pb2.RequestMetadata:
        payload = value.model_dump(exclude_none=True)
        msg = aduib_rpc_v2_pb2.RequestMetadata(
            timestamp_ms=int(value.timestamp_ms or 0),
        )
        if value.client_id is not None:
            msg.client_id = str(value.client_id)
        if value.client_version is not None:
            msg.client_version = str(value.client_version)
        auth_value = value.auth
        if auth_value is not None:
            msg.auth.CopyFrom(cls.auth_context(auth_value))
        if value.tenant_id is not None:
            msg.tenant_id = str(value.tenant_id)
        headers = value.headers or {}
        if isinstance(headers, dict):
            msg.headers.update({str(k): str(v) for k, v in headers.items()})
        if value.long_task is not None:
            msg.long_task = bool(value.long_task)
        if value.long_task_method is not None:
            msg.long_task_method = str(value.long_task_method)
        if value.long_task_timeout is not None:
            msg.long_task_timeout = int(value.long_task_timeout)
        return msg

    @classmethod
    @classmethod
    def response_metadata(cls, value: ResponseMetadata) -> aduib_rpc_v2_pb2.ResponseMetadata:
        payload = value.model_dump(exclude_none=True)
        msg = aduib_rpc_v2_pb2.ResponseMetadata(
            timestamp_ms=int(value.timestamp_ms or 0),
            duration_ms=int(value.duration_ms or 0),
        )
        if value.server_id is not None:
            msg.server_id = str(value.server_id)
        if value.server_version is not None:
            msg.server_version = str(value.server_version)
        return msg

    @classmethod
    def retry_config(cls, value: RetryPolicy) -> aduib_rpc_v2_pb2.RetryConfig:
        payload = {
            "max_attempts": value.max_attempts,
            "initial_delay_ms": value.initial_delay_ms,
            "max_delay_ms": value.max_delay_ms,
            "backoff_multiplier": value.backoff_multiplier,
            "retryable_codes": list(value.retryable_codes) if value.retryable_codes else [],
        }
        msg = aduib_rpc_v2_pb2.RetryConfig(
            max_attempts=int(payload.get("max_attempts") or 0),
            initial_delay_ms=int(payload.get("initial_delay_ms") or 0),
            max_delay_ms=int(payload.get("max_delay_ms") or 0),
            backoff_multiplier=float(payload.get("backoff_multiplier") or 0),
        )
        retryable_codes = payload.get("retryable_codes") or []
        if retryable_codes:
            msg.retryable_codes.extend([int(code) for code in retryable_codes if code is not None])
        return msg

    @classmethod
    def qos_config(cls, value: QosConfig) -> aduib_rpc_v2_pb2.QosConfig:
        msg = aduib_rpc_v2_pb2.QosConfig(priority=Priority.to_proto(value.priority))
        if value.timeout_ms is not None:
            msg.timeout_ms = int(value.timeout_ms)
        if value.retry is not None:
            msg.retry.CopyFrom(cls.retry_config(value.retry))
        if value.idempotency_key is not None:
            msg.idempotency_key = str(value.idempotency_key)
        return msg

    @classmethod
    def value(cls, obj: Any) -> struct_pb2.Value:
        return json_format.ParseDict(obj, struct_pb2.Value())

    @classmethod
    def _dict_to_struct(cls, payload: Any) -> struct_pb2.Struct:
        struct_value = struct_pb2.Struct()
        if payload is None:
            return struct_value
        if not isinstance(payload, dict):
            try:
                json_format.ParseDict(payload, struct_value)
                return struct_value
            except Exception:
                payload = {"value": payload}
        try:
            json_format.ParseDict(payload, struct_value)
            return struct_value
        except Exception:
            pass
        try:
            if hasattr(struct_value, "update"):
                struct_value.update(payload)
                return struct_value
        except Exception:
            pass
        try:
            if hasattr(struct_value, "__setitem__"):
                for key, value in payload.items():
                    struct_value[str(key)] = value
                return struct_value
        except Exception:
            pass
        try:
            if hasattr(struct_value, "fields"):
                for key, value in payload.items():
                    struct_value.fields[str(key)].CopyFrom(cls.value(value))
        except Exception:
            pass
        return struct_value

    @classmethod
    def _fill_struct(cls, target: struct_pb2.Struct, payload: Any) -> None:
        if payload is None:
            return
        if not isinstance(payload, dict):
            try:
                json_format.ParseDict(payload, target)
                return
            except Exception:
                payload = {"value": payload}
        try:
            json_format.ParseDict(payload, target)
            return
        except Exception:
            pass
        try:
            if hasattr(target, "update"):
                target.update(payload)
                return
        except Exception:
            pass
        try:
            if hasattr(target, "__setitem__"):
                for key, value in payload.items():
                    target[str(key)] = value
        except Exception:
            pass

    @classmethod
    def request(cls, request: V2Request) -> aduib_rpc_v2_pb2.Request:
        msg = aduib_rpc_v2_pb2.Request(
            aduib_rpc=str(request.aduib_rpc or "2.0"),
            id=str(request.id or ""),
            method=str(request.method or ""),
        )
        if request.name is not None:
            msg.name = str(request.name)
        if request.data is not None:
            cls._fill_struct(msg.data, request.data)
        if request.trace_context is not None:
            msg.trace_context.CopyFrom(cls.trace_context(request.trace_context))
        if request.metadata is not None:
            msg.metadata.CopyFrom(cls.request_metadata(request.metadata))
        if request.qos is not None:
            msg.qos.CopyFrom(cls.qos_config(request.qos))
        return msg

    @classmethod
    def status(cls, status: object) -> int:
        return ResponseStatus.to_proto(status)

    @classmethod
    def response(cls, resp: V2Response) -> aduib_rpc_v2_pb2.Response:
        msg = aduib_rpc_v2_pb2.Response(
            aduib_rpc=resp.aduib_rpc,
            id=resp.id or "",
            status=cls.status(resp.status),
        )
        if resp.is_success():
            msg.result.CopyFrom(cls.value(resp.result))
        else:
            if resp.error is not None:
                msg.error.CopyFrom(
                    aduib_rpc_v2_pb2.RpcError(
                        code=int(resp.error.code),
                        name=resp.error.name,
                        message=resp.error.message,
                    )
                )
        trace_context_value = getattr(resp, "trace_context", None)
        if trace_context_value is not None:
            msg.trace_context.CopyFrom(cls.trace_context(trace_context_value))
        metadata_value = getattr(resp, "metadata", None)
        if metadata_value is not None:
            msg.metadata.CopyFrom(cls.response_metadata(metadata_value))
        return msg

    @classmethod
    def priority(cls, priority: Priority | int) -> int:
        return Priority.to_proto(priority)

    @classmethod
    def task_status(cls, status: Any) -> int:
        return TaskStatus.to_proto(status)

    @classmethod
    def health_status(cls, status: Any) -> int:
        return HealthStatus.to_proto(status)

    @classmethod
    def rpc_error(cls, error: RpcError) -> aduib_rpc_v2_pb2.RpcError:
        payload = (
            error.model_dump()
            if hasattr(error, "model_dump")
            else {
                "code": getattr(error, "code", 0),
                "name": getattr(error, "name", None) or "UNKNOWN",
                "message": getattr(error, "message", ""),
                "details": getattr(error, "details", None),
                "debug": getattr(error, "debug", None),
            }
        )

        rpc_error = aduib_rpc_v2_pb2.RpcError(
            code=int(payload.get("code") or 0),
            name=str(payload.get("name") or "UNKNOWN"),
            message=str(payload.get("message") or ""),
        )

        details = payload.get("details") or []
        for item in details:
            if hasattr(item, "model_dump"):
                item = item.model_dump()
            if not isinstance(item, dict):
                continue
            detail = aduib_rpc_v2_pb2.ErrorDetail(
                type=str(item.get("type") or ""),
                reason=str(item.get("reason") or ""),
            )
            if item.get("field") is not None:
                detail.field = str(item.get("field"))
            metadata = item.get("metadata") or {}
            if isinstance(metadata, dict):
                detail.metadata.update({str(k): str(v) for k, v in metadata.items()})
            rpc_error.details.append(detail)

        debug = payload.get("debug")
        if debug:
            if hasattr(debug, "model_dump"):
                debug = debug.model_dump()
            if isinstance(debug, dict):
                debug_info = aduib_rpc_v2_pb2.DebugInfo(timestamp_ms=int(debug.get("timestamp_ms") or 0))
                if debug.get("stack_trace") is not None:
                    debug_info.stack_trace = str(debug.get("stack_trace"))
                if debug.get("internal_message") is not None:
                    debug_info.internal_message = str(debug.get("internal_message"))
                rpc_error.debug.CopyFrom(debug_info)

        return rpc_error

    @classmethod
    def task_progress(cls, progress: TaskProgress) -> aduib_rpc_v2_pb2.TaskProgress:
        payload = progress.model_dump()
        msg = aduib_rpc_v2_pb2.TaskProgress(
            current=int(payload.get("current") or 0),
            total=int(payload.get("total") or 0),
        )
        if payload.get("message") is not None:
            msg.message = str(payload.get("message"))
        if payload.get("percentage") is not None:
            msg.percentage = float(payload.get("percentage"))
        return msg

    @classmethod
    def task_record(cls, record: TaskRecord) -> aduib_rpc_v2_pb2.TaskRecord:
        msg = aduib_rpc_v2_pb2.TaskRecord(
            task_id=str(getattr(record, "task_id", "")),
            status=cls.task_status(getattr(record, "status")),
            priority=cls.priority(getattr(record, "priority")),
            created_at_ms=int(getattr(record, "created_at_ms", 0)),
            attempt=int(getattr(record, "attempt", 0)),
            max_attempts=int(getattr(record, "max_attempts", 0)),
        )
        if getattr(record, "parent_task_id", None) is not None:
            msg.parent_task_id = str(getattr(record, "parent_task_id"))
        if getattr(record, "scheduled_at_ms", None) is not None:
            msg.scheduled_at_ms = int(getattr(record, "scheduled_at_ms"))
        if getattr(record, "started_at_ms", None) is not None:
            msg.started_at_ms = int(getattr(record, "started_at_ms"))
        if getattr(record, "completed_at_ms", None) is not None:
            msg.completed_at_ms = int(getattr(record, "completed_at_ms"))
        if getattr(record, "next_retry_at_ms", None) is not None:
            msg.next_retry_at_ms = int(getattr(record, "next_retry_at_ms"))

        result = getattr(record, "result", None)
        if result is not None:
            try:
                msg.result.CopyFrom(cls.value(result))
            except Exception:
                msg.result.CopyFrom(cls.value(str(result)))

        error = getattr(record, "error", None)
        if error is not None:
            msg.error.CopyFrom(cls.rpc_error(error))

        progress_value = getattr(record, "progress", None)
        if progress_value is not None:
            msg.progress.CopyFrom(cls.task_progress(progress_value))

        metadata = getattr(record, "metadata", None) or {}
        if isinstance(metadata, dict):
            msg.metadata.update({str(k): str(v) for k, v in metadata.items()})
        tags = getattr(record, "tags", None) or []
        if tags:
            msg.tags.extend([str(tag) for tag in tags])

        return msg

    @classmethod
    def task_event(cls, event: TaskEvent) -> aduib_rpc_v2_pb2.TaskEvent:
        task = getattr(event, "task", None)
        return aduib_rpc_v2_pb2.TaskEvent(
            event=str(getattr(event, "event", "")),
            task=cls.task_record(task),
            timestamp_ms=int(getattr(event, "timestamp_ms", 0)),
        )

    @classmethod
    def health_response(cls, payload: HealthCheckResponse) -> aduib_rpc_v2_pb2.HealthCheckResponse:
        status = getattr(payload, "status", None)
        services = getattr(payload, "services", None) or {}
        msg = aduib_rpc_v2_pb2.HealthCheckResponse(status=cls.health_status(status))
        if isinstance(services, dict):
            msg.services.update({str(k): cls.health_status(v) for k, v in services.items()})
        return msg

    @classmethod
    def task_submit_request(cls, submit: TaskSubmitRequest) -> aduib_rpc_v2_pb2.TaskSubmitRequest:
        msg = aduib_rpc_v2_pb2.TaskSubmitRequest(
            target_method=str(submit.target_method),
            priority=Priority.from_proto(submit.priority),
        )
        if submit.params is not None:
            cls._fill_struct(msg.params, submit.params)
        return msg
