from __future__ import annotations

import json
from typing import Any

from thrift.Thrift import TApplicationException

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
from aduib_rpc.server.tasks import (
    TaskCancelRequest,
    TaskEvent,
    TaskProgress,
    TaskQueryRequest,
    TaskRecord,
    TaskStatus,
    TaskSubmitRequest,
    TaskSubscribeRequest,
)
from aduib_rpc.utils.error_handlers import exception_to_error


class FromThrift:
    """Utility class for converting thrift messages to native Python types."""

    @classmethod
    def trace_context(cls, value) -> TraceContext:
        payload: dict[str, Any] = {
            "trace_id": str(getattr(value, "trace_id", "") or ""),
            "span_id": str(getattr(value, "span_id", "") or ""),
            "sampled": bool(getattr(value, "sampled", True)),
        }
        if getattr(value, "parent_span_id", None) is not None:
            payload["parent_span_id"] = str(value.parent_span_id)
        baggage = dict(getattr(value, "baggage", None) or {})
        if baggage:
            payload["baggage"] = {str(k): str(v) for k, v in baggage.items()}
        return TraceContext(**payload)

    @classmethod
    def auth_context(cls, value) -> AuthContext:
        payload: dict[str, Any] = {
            "scheme": AuthScheme.from_thrift(getattr(value, "scheme", None)),
            "roles": list(getattr(value, "roles", None) or []) or None,
        }
        if getattr(value, "credentials", None) is not None:
            payload["credentials"] = str(value.credentials)
        if getattr(value, "principal", None) is not None:
            payload["principal"] = str(value.principal)
        return AuthContext(**payload)

    @classmethod
    def error_detail(cls, value) -> ErrorDetail:
        metadata = dict(getattr(value, "metadata", None) or {}) or None
        payload: dict[str, Any] = {
            "type": str(getattr(value, "type", "") or ""),
            "reason": str(getattr(value, "reason", "") or ""),
            "metadata": metadata,
        }
        if getattr(value, "field", None) is not None:
            payload["field"] = str(value.field)
        return ErrorDetail(**payload)

    @classmethod
    def debug_info(cls, value) -> DebugInfo:
        payload: dict[str, Any] = {
            "timestamp_ms": int(getattr(value, "timestamp_ms", 0) or 0),
        }
        if getattr(value, "stack_trace", None) is not None:
            payload["stack_trace"] = str(value.stack_trace)
        if getattr(value, "internal_message", None) is not None:
            payload["internal_message"] = str(value.internal_message)
        return DebugInfo(**payload)

    @classmethod
    def rpc_error(cls, value) -> RpcError:
        details = [cls.error_detail(item) for item in getattr(value, "details", None) or [] if item is not None]
        debug_value = getattr(value, "debug", None)
        debug = cls.debug_info(debug_value) if debug_value is not None else None
        return RpcError(
            code=int(getattr(value, "code", 0) or 0),
            name=str(getattr(value, "name", "") or "UNKNOWN"),
            message=str(getattr(value, "message", "") or ""),
            details=[item for item in details if item is not None] or None,
            debug=debug,
        )

    @classmethod
    def request_metadata(cls, value) -> RequestMetadata:
        payload: dict[str, Any] = {
            "timestamp_ms": int(getattr(value, "timestamp_ms", 0) or 0),
            "long_task": bool(getattr(value, "long_task", False)),
        }
        if getattr(value, "client_id", None) is not None:
            payload["client_id"] = str(value.client_id)
        if getattr(value, "client_version", None) is not None:
            payload["client_version"] = str(value.client_version)
        auth_value = getattr(value, "auth", None)
        if auth_value is not None:
            payload["auth"] = cls.auth_context(auth_value)
        if getattr(value, "tenant_id", None) is not None:
            payload["tenant_id"] = str(value.tenant_id)
        headers = dict(getattr(value, "headers", None) or {})
        if headers:
            payload["headers"] = {str(k): str(v) for k, v in headers.items()}
        if getattr(value, "long_task_method", None) is not None:
            payload["long_task_method"] = str(value.long_task_method)
        if getattr(value, "long_task_timeout", None) is not None:
            payload["long_task_timeout"] = int(value.long_task_timeout)
        return RequestMetadata(**payload)

    @classmethod
    @classmethod
    def response_metadata(cls, value) -> ResponseMetadata:
        payload: dict[str, Any] = {
            "timestamp_ms": int(getattr(value, "timestamp_ms", 0) or 0),
            "duration_ms": int(getattr(value, "duration_ms", 0) or 0),
        }
        if getattr(value, "server_id", None) is not None:
            payload["server_id"] = str(value.server_id)
        if getattr(value, "server_version", None) is not None:
            payload["server_version"] = str(value.server_version)
        return ResponseMetadata(**payload)

    @classmethod
    def retry_policy(cls, value) -> RetryPolicy:
        defaults = RetryPolicy()
        max_attempts = int(getattr(value, "max_attempts", 0) or defaults.max_attempts)
        initial_delay_ms = int(getattr(value, "initial_delay_ms", 0) or defaults.initial_delay_ms)
        max_delay_ms = int(getattr(value, "max_delay_ms", 0) or defaults.max_delay_ms)
        backoff_multiplier = float(getattr(value, "backoff_multiplier", 0) or defaults.backoff_multiplier)
        retryable_codes = set(getattr(value, "retryable_codes", None) or []) or None
        return RetryPolicy(
            max_attempts=max_attempts,
            initial_delay_ms=initial_delay_ms,
            max_delay_ms=max_delay_ms,
            backoff_multiplier=backoff_multiplier,
            retryable_codes=retryable_codes,
        )

    @classmethod
    def qos_config(cls, value) -> QosConfig:
        retry_value = getattr(value, "retry_config", None)
        if retry_value is None:
            retry_value = getattr(value, "retry", None)
        retry = cls.retry_policy(retry_value) if retry_value is not None else None
        timeout_ms = int(value.timeout_ms) if getattr(value, "timeout_ms", None) is not None else None
        idempotency_key = str(value.idempotency_key) if getattr(value, "idempotency_key", None) is not None else None
        return QosConfig(
            priority=Priority.from_thrift(getattr(value, "priority", None)),
            timeout_ms=timeout_ms,
            retry=retry,
            idempotency_key=idempotency_key,
        )

    @classmethod
    def task_progress(cls, value) -> TaskProgress:
        return TaskProgress(
            current=int(getattr(value, "current", 0) or 0),
            total=int(getattr(value, "total", 0) or 0),
            message=getattr(value, "message", None),
            percentage=float(getattr(value, "percentage", 0.0))
            if getattr(value, "percentage", None) is not None
            else None,
        )

    @classmethod
    def task_record(cls, value) -> TaskRecord:
        result = None
        raw_result = getattr(value, "result", None)
        if raw_result is not None:
            result = cls.safe_json_loads(raw_result)
        return TaskRecord(
            task_id=str(getattr(value, "task_id", "") or ""),
            parent_task_id=getattr(value, "parent_task_id", None),
            status=TaskStatus.from_thrift(getattr(value, "status", None)),
            priority=Priority.from_thrift(getattr(value, "priority", None)),
            created_at_ms=int(getattr(value, "created_at_ms", 0) or 0),
            scheduled_at_ms=getattr(value, "scheduled_at_ms", None),
            started_at_ms=getattr(value, "started_at_ms", None),
            completed_at_ms=getattr(value, "completed_at_ms", None),
            attempt=int(getattr(value, "attempt", 0) or 0),
            max_attempts=int(getattr(value, "max_attempts", 0) or 0),
            next_retry_at_ms=getattr(value, "next_retry_at_ms", None),
            result=result,
            error=cls.rpc_error(getattr(value, "error", None))
            if getattr(value, "error", None) is not None
            else None,
            progress=cls.task_progress(getattr(value, "progress", None))
            if getattr(value, "progress", None) is not None
            else None,
            metadata=dict(getattr(value, "metadata", None) or {}) or None,
            tags=list(getattr(value, "tags", None) or []) or None,
        )

    @classmethod
    def task_event(cls, value) -> TaskEvent:
        return TaskEvent(
            event=str(getattr(value, "event", "") or ""),
            task=cls.task_record(value.task),
            timestamp_ms=int(getattr(value, "timestamp_ms", 0) or 0),
        )

    @classmethod
    def request(cls, task) -> V2Request:
        # task is thrift_v2.ttypes.Request
        data = {}
        if getattr(task, "data_json", None):
            try:
                data = json.loads(task.data_json)
            except Exception:
                data = {}

        return V2Request(
            aduib_rpc=task.aduib_rpc or "2.0",
            id=task.id,
            method=task.method,
            name=getattr(task, "name", None),
            data=data,
            trace_context=cls.trace_context(getattr(task, "trace_context", None))
            if getattr(task, "trace_context", None) is not None
            else None,
            metadata=cls.request_metadata(getattr(task, "metadata", None))
            if getattr(task, "metadata", None) is not None
            else None,
            qos=cls.qos_config(getattr(task, "qos", None)) if getattr(task, "qos", None) is not None else None,
        )

    @classmethod
    def task_submit_request(cls, value) -> TaskSubmitRequest:
        payload: dict[str, Any] = {
            "target_method": str(getattr(value, "target_method", "") or ""),
        }
        if getattr(value, "params_json", None):
            payload["params"] = cls.safe_json_loads(value.params_json)
        if getattr(value, "priority", None) is not None:
            payload["priority"] = cls.priority(getattr(value, "priority", None))
        if getattr(value, "max_attempts", None) is not None:
            payload["max_attempts"] = int(value.max_attempts)
        if getattr(value, "timeout_ms", None) is not None:
            payload["timeout_ms"] = int(value.timeout_ms)
        if getattr(value, "scheduled_at_ms", None) is not None:
            payload["scheduled_at_ms"] = int(value.scheduled_at_ms)
        if getattr(value, "idempotency_key", None) is not None:
            payload["idempotency_key"] = str(value.idempotency_key)
        if getattr(value, "metadata", None):
            payload["metadata"] = dict(value.metadata)
        return TaskSubmitRequest.model_validate(payload)

    @classmethod
    def task_query_request(cls, value) -> TaskQueryRequest:
        return TaskQueryRequest(task_id=str(getattr(value, "task_id", "") or ""))

    @classmethod
    def task_cancel_request(cls, value) -> TaskCancelRequest:
        payload: dict[str, Any] = {
            "task_id": str(getattr(value, "task_id", "") or ""),
        }
        if getattr(value, "reason", None) is not None:
            payload["reason"] = str(value.reason)
        return TaskCancelRequest.model_validate(payload)

    @classmethod
    def task_subscribe_request(cls, value) -> TaskSubscribeRequest:
        payload: dict[str, Any] = {
            "task_id": str(getattr(value, "task_id", "") or ""),
        }
        events = list(getattr(value, "events", None) or [])
        if events:
            payload["events"] = [str(item) for item in events]
        return TaskSubscribeRequest.model_validate(payload)

    @classmethod
    def health_request(cls, value) -> HealthCheckRequest:
        service = getattr(value, "service_name", None)
        if service is None:
            service = getattr(value, "service", None)
        if service:
            return HealthCheckRequest(service=str(service))
        return HealthCheckRequest()

    @classmethod
    def response(cls, response) -> V2Response:
        payload = getattr(response, "payload", None)
        result = None
        error = None
        if payload is not None:
            if getattr(payload, "error", None) is not None:
                error = cls.rpc_error(payload.error)
            elif getattr(payload, "result_json", None) is not None:
                result = cls.safe_json_loads(getattr(payload, "result_json", None))
        return V2Response(
            aduib_rpc=getattr(response, "aduib_rpc", None) or "2.0",
            id=getattr(response, "id", None),
            status=ResponseStatus.from_thrift(getattr(response, "status", None)),
            result=result,
            error=error,
            trace_context=cls.trace_context(getattr(response, "trace_context", None))
            if getattr(response, "trace_context", None) is not None
            else None,
            metadata=cls.response_metadata(getattr(response, "metadata", None))
            if getattr(response, "metadata", None) is not None
            else None,
        )

    @classmethod
    def safe_json_loads(cls, value: str) -> dict[str, Any]:
        if not value:
            return {}
        try:
            return json.loads(value)
        except Exception:
            return {}

    @classmethod
    def priority(cls, value: Any) -> Priority:
        return Priority.from_thrift(value)

    @classmethod
    def health_response(cls, value) -> HealthCheckResponse:
        services = {str(k): HealthStatus.from_thrift(v) for k, v in (getattr(value, "services", None) or {}).items()}
        return HealthCheckResponse(
            status=HealthStatus.from_thrift(getattr(value, "status", None)),
            services=services or None,
        )


class ToThrift:
    """Utility class for converting native Python types to thrift messages."""

    @staticmethod
    def _resolve_type(ttypes, name: str):
        if ttypes is None:
            from aduib_rpc.thrift_v2 import ttypes as default_ttypes

            ttypes = default_ttypes
        if hasattr(ttypes, "ttypes"):
            ttypes = ttypes.ttypes
        return getattr(ttypes, name)

    @staticmethod
    def _coerce_str_map(value: dict[str, Any]) -> dict[str, str]:
        return {str(k): str(v) for k, v in value.items()}

    @staticmethod
    def _coerce_str_list(value: Any) -> list[str]:
        if isinstance(value, list):
            return [str(item) for item in value]
        return [str(value)]

    @staticmethod
    def json_dumps_safe(obj) -> str:
        try:
            return json.dumps(obj, ensure_ascii=False)
        except Exception:
            return json.dumps({"_unserializable": True})

    @classmethod
    def trace_context(cls, value: TraceContext, *, ttypes=None):
        payload = value.model_dump(exclude_none=True)
        ThriftTraceContext = cls._resolve_type(ttypes, "TraceContext")

        msg = ThriftTraceContext(
            trace_id=str(payload.get("trace_id") or ""),
            span_id=str(payload.get("span_id") or ""),
            sampled=bool(payload.get("sampled", True)),
        )
        if payload.get("parent_span_id") is not None:
            msg.parent_span_id = str(payload.get("parent_span_id"))
        baggage = payload.get("baggage") or {}
        if isinstance(baggage, dict):
            msg.baggage = {str(k): str(v) for k, v in baggage.items()}
        return msg

    @classmethod
    def auth_context(cls, value: AuthContext, *, ttypes=None):
        payload = value.model_dump(exclude_none=True)
        ThriftAuthContext = cls._resolve_type(ttypes, "AuthContext")

        msg = ThriftAuthContext(
            scheme=AuthScheme.to_thrift(payload.get("scheme")),
        )
        if payload.get("credentials") is not None:
            msg.credentials = str(payload.get("credentials"))
        if payload.get("principal") is not None:
            msg.principal = str(payload.get("principal"))
        roles = payload.get("roles") or []
        if roles:
            msg.roles = [str(role) for role in roles]
        return msg

    @classmethod
    def request_metadata(cls, value: RequestMetadata, *, ttypes=None):
        payload = value.model_dump(exclude_none=True)
        ThriftRequestMetadata = cls._resolve_type(ttypes, "RequestMetadata")

        msg = ThriftRequestMetadata(
            timestamp_ms=int(payload.get("timestamp_ms") or 0),
        )
        if payload.get("client_id") is not None:
            msg.client_id = str(payload.get("client_id"))
        if payload.get("client_version") is not None:
            msg.client_version = str(payload.get("client_version"))
        auth_value = value.auth
        if auth_value is not None:
            msg.auth = cls.auth_context(auth_value, ttypes=ttypes)
        if value.tenant_id is not None:
            msg.tenant_id = str(value.tenant_id)
        headers_value = value.headers
        if headers_value:
            msg.headers = cls._coerce_str_map(headers_value)
        if value.long_task is not None:
            msg.long_task = bool(value.long_task)
        if value.long_task_method is not None:
            msg.long_task_method = str(value.long_task_method)
        if value.long_task_timeout is not None:
            msg.long_task_timeout = int(value.long_task_timeout)
        return msg

    @classmethod
    @classmethod
    def response_metadata(cls, value: ResponseMetadata, *, ttypes=None):
        payload = value.model_dump(exclude_none=True)
        ThriftResponseMetadata = cls._resolve_type(ttypes, "ResponseMetadata")

        msg = ThriftResponseMetadata(
            timestamp_ms=int(payload.get("timestamp_ms") or 0),
            duration_ms=int(payload.get("duration_ms") or 0),
        )
        if value.server_id is not None:
            msg.server_id = str(value.server_id)
        if value.server_version is not None:
            msg.server_version = str(value.server_version)
        return msg

    @classmethod
    def retry_config(cls, value: RetryPolicy, *, ttypes=None):
        payload = {
            "max_attempts": value.max_attempts,
            "initial_delay_ms": value.initial_delay_ms,
            "max_delay_ms": value.max_delay_ms,
            "backoff_multiplier": value.backoff_multiplier,
            "retryable_codes": list(value.retryable_codes) if value.retryable_codes else [],
        }
        ThriftRetryConfig = cls._resolve_type(ttypes, "RetryConfig")

        msg = ThriftRetryConfig(
            max_attempts=int(payload.get("max_attempts") or 0),
            initial_delay_ms=int(payload.get("initial_delay_ms") or 0),
            max_delay_ms=int(payload.get("max_delay_ms") or 0),
            backoff_multiplier=float(payload.get("backoff_multiplier") or 0),
        )
        retryable_codes = payload.get("retryable_codes") or []
        if retryable_codes:
            msg.retryable_codes = [int(code) for code in retryable_codes if code is not None]
        return msg

    @classmethod
    def qos_config(cls, value: QosConfig, *, ttypes=None):
        ThriftQosConfig = cls._resolve_type(ttypes, "QosConfig")

        msg = ThriftQosConfig(priority=Priority.to_thrift(value.priority))
        if value.timeout_ms is not None:
            msg.timeout_ms = int(value.timeout_ms)
        if value.retry is not None:
            msg.retry_config = cls.retry_config(value.retry, ttypes=ttypes)
        if value.idempotency_key is not None:
            msg.idempotency_key = str(value.idempotency_key)
        return msg

    @classmethod
    def request(cls, request: V2Request, *, ttypes=None):
        payload = request.model_dump(exclude_none=True)

        ThriftRequest = cls._resolve_type(ttypes, "Request")
        data_json = cls.json_dumps_safe(payload.get("data") or {})
        msg = ThriftRequest(
            aduib_rpc=str(payload.get("aduib_rpc") or "2.0"),
            id=str(payload.get("id") or ""),
            method=str(payload.get("method") or ""),
            name=str(payload.get("name")) if payload.get("name") is not None else None,
            data_json=data_json or "{}",
        )

        trace_context_value = getattr(request, "trace_context", None)
        if trace_context_value is not None:
            msg.trace_context = cls.trace_context(trace_context_value, ttypes=ttypes)
        metadata_value = getattr(request, "metadata", None)
        if metadata_value is not None:
            msg.metadata = cls.request_metadata(metadata_value, ttypes=ttypes)
        qos_value = getattr(request, "qos", None)
        if qos_value is not None:
            msg.qos = cls.qos_config(qos_value, ttypes=ttypes)
        return msg

    @classmethod
    def response_status(cls, status: Any) -> int:
        return ResponseStatus.to_thrift(status)

    @classmethod
    def priority(cls, value: Priority | int | str) -> int:
        return Priority.to_thrift(value)

    @classmethod
    def task_status(cls, value: TaskStatus | str | int) -> int:
        return TaskStatus.to_thrift(value)

    @classmethod
    def health_status(cls, value: Any) -> int:
        return HealthStatus.to_thrift(value)

    @classmethod
    def error_detail(cls, detail: ErrorDetail):
        from aduib_rpc.thrift_v2.ttypes import ErrorDetail as ThriftErrorDetail

        payload = detail.model_dump() if hasattr(detail, "model_dump") else {
            "type": getattr(detail, "type", ""),
            "field": getattr(detail, "field", None),
            "reason": getattr(detail, "reason", ""),
            "metadata": getattr(detail, "metadata", None),
        }

        msg = ThriftErrorDetail(
            type=str(payload.get("type") or ""),
            reason=str(payload.get("reason") or ""),
        )
        if payload.get("field") is not None:
            msg.field = str(payload.get("field"))
        metadata = payload.get("metadata") or {}
        if isinstance(metadata, dict):
            msg.metadata = {str(k): str(v) for k, v in metadata.items()}
        return msg

    @classmethod
    def debug_info(cls, debug: DebugInfo):
        from aduib_rpc.thrift_v2.ttypes import DebugInfo as ThriftDebugInfo

        payload = debug.model_dump() if hasattr(debug, "model_dump") else {
            "stack_trace": getattr(debug, "stack_trace", None),
            "internal_message": getattr(debug, "internal_message", None),
            "timestamp_ms": getattr(debug, "timestamp_ms", 0),
        }

        msg = ThriftDebugInfo(timestamp_ms=int(payload.get("timestamp_ms") or 0))
        if payload.get("stack_trace") is not None:
            msg.stack_trace = str(payload.get("stack_trace"))
        if payload.get("internal_message") is not None:
            msg.internal_message = str(payload.get("internal_message"))
        return msg

    @classmethod
    def rpc_error(cls, error: RpcError):
        from aduib_rpc.thrift_v2.ttypes import RpcError as ThriftRpcError

        payload = error.model_dump(exclude_none=True) if hasattr(error, "model_dump") else {
            "code": getattr(error, "code", 0),
            "name": getattr(error, "name", None) or "ERROR",
            "message": getattr(error, "message", ""),
            "details": getattr(error, "details", None),
            "debug": getattr(error, "debug", None),
        }

        rpc_error = ThriftRpcError(
            code=int(payload.get("code", -1)),
            name=str(payload.get("name", "ERROR")),
            message=str(payload.get("message", "")),
        )

        details = payload.get("details") or []
        detail_items = []
        for item in details:
            if item is None:
                continue
            detail_items.append(cls.error_detail(item))
        if detail_items:
            rpc_error.details = detail_items

        debug_value = payload.get("debug")
        if debug_value is not None:
            rpc_error.debug = cls.debug_info(debug_value)

        return rpc_error

    @classmethod
    def task_progress(cls, progress: TaskProgress):
        from aduib_rpc.thrift_v2.ttypes import TaskProgress as ThriftTaskProgress

        return ThriftTaskProgress(
            current=int(getattr(progress, "current", 0)),
            total=int(getattr(progress, "total", 0)),
            message=getattr(progress, "message", None),
            percentage=getattr(progress, "percentage", None),
        )

    @classmethod
    def task_record(cls, record: TaskRecord):
        from aduib_rpc.thrift_v2.ttypes import TaskRecord as ThriftTaskRecord

        result_value = None
        if getattr(record, "result", None) is not None:
            result_value = cls.json_dumps_safe(getattr(record, "result"))

        return ThriftTaskRecord(
            task_id=str(getattr(record, "task_id", "")),
            parent_task_id=getattr(record, "parent_task_id", None),
            status=cls.task_status(getattr(record, "status")),
            priority=cls.priority(getattr(record, "priority")),
            created_at_ms=int(getattr(record, "created_at_ms", 0)),
            scheduled_at_ms=getattr(record, "scheduled_at_ms", None),
            started_at_ms=getattr(record, "started_at_ms", None),
            completed_at_ms=getattr(record, "completed_at_ms", None),
            attempt=int(getattr(record, "attempt", 0)),
            max_attempts=int(getattr(record, "max_attempts", 0)),
            next_retry_at_ms=getattr(record, "next_retry_at_ms", None),
            result=result_value,
            error=cls.rpc_error(getattr(record, "error", None))
            if getattr(record, "error", None) is not None
            else None,
            progress=cls.task_progress(getattr(record, "progress", None))
            if getattr(record, "progress", None) is not None
            else None,
            metadata=cls._coerce_str_map(getattr(record, "metadata", None))
            if getattr(record, "metadata", None)
            else None,
            tags=cls._coerce_str_list(getattr(record, "tags", None))
            if getattr(record, "tags", None)
            else None,
        )

    @classmethod
    def task_event(cls, event: TaskEvent):
        from aduib_rpc.thrift_v2.ttypes import TaskEvent as ThriftTaskEvent

        return ThriftTaskEvent(
            event=str(getattr(event, "event", "")),
            task=cls.task_record(getattr(event, "task")),
            timestamp_ms=int(getattr(event, "timestamp_ms", 0)),
        )

    @classmethod
    def response_payload(cls, resp: V2Response):
        from aduib_rpc.thrift_v2.ttypes import ResponsePayload as ThriftResponsePayload

        if resp.is_success():
            return ThriftResponsePayload(result_json=cls.json_dumps_safe(resp.result))
        err = resp.error
        if err is None:
            err = RpcError(code=0, name="UNKNOWN", message="")
        return ThriftResponsePayload(error=cls.rpc_error(err))

    @classmethod
    def error_payload(cls, exc: Exception):
        err = exception_to_error(exc)
        from aduib_rpc.thrift_v2.ttypes import ResponsePayload as ThriftResponsePayload
        return ThriftResponsePayload(error=cls.rpc_error(err))

    @classmethod
    def raise_app_error(cls, exc: Exception) -> None:
        err = exception_to_error(exc)
        if hasattr(err, "model_dump"):
            payload = err.model_dump(mode="json", exclude_none=True)
        else:
            payload = {"code": 0, "name": "UNKNOWN", "message": str(err)}
        raise TApplicationException(
            TApplicationException.INTERNAL_ERROR,
            json.dumps(payload, ensure_ascii=False),
        )

    @classmethod
    def health_response(cls, payload: HealthCheckResponse):
        from aduib_rpc.thrift_v2.ttypes import HealthCheckResponse as ThriftHealthCheckResponse

        status = getattr(payload, "status", None)
        services_raw = getattr(payload, "services", None) or {}
        services = {str(k): cls.health_status(v) for k, v in services_raw.items()}
        return ThriftHealthCheckResponse(
            status=cls.health_status(status),
            services=services,
        )


def request_from_thrift(task) -> V2Request:
    return FromThrift.request(task)


def response_to_thrift(resp: V2Response, response_cls):
    status = ToThrift.response_status(resp.status)
    payload = ToThrift.response_payload(resp)
    trace_context_value = getattr(resp, "trace_context", None)
    trace_context = ToThrift.trace_context(trace_context_value) if trace_context_value is not None else None
    metadata_value = getattr(resp, "metadata", None)
    metadata = ToThrift.response_metadata(metadata_value) if metadata_value is not None else None

    try:
        return response_cls(
            aduib_rpc=resp.aduib_rpc,
            id=resp.id or "",
            status=status,
            payload=payload,
            trace_context=trace_context,
            metadata=metadata,
        )
    except TypeError:
        legacy_meta = None
        if getattr(resp, "metadata", None) is not None:
            try:
                legacy_meta = dict(resp.metadata)  # type: ignore[arg-type]
            except Exception:
                legacy_meta = None
        result_json = getattr(payload, "result_json", None) if payload is not None else None
        thrift_error = getattr(payload, "error", None) if payload is not None else None
        return response_cls(
            aduib_rpc=resp.aduib_rpc,
            id=resp.id or "",
            status=status,
            result_json=result_json,
            error=thrift_error,
            metadata=legacy_meta,
        )


def json_dumps_safe(obj) -> str:
    return ToThrift.json_dumps_safe(obj)
