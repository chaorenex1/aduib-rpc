from google.protobuf import struct_pb2 as _struct_pb2
from google.protobuf.internal import containers as _containers
from google.protobuf.internal import enum_type_wrapper as _enum_type_wrapper
from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from collections.abc import Iterable as _Iterable, Mapping as _Mapping
from typing import ClassVar as _ClassVar, Optional as _Optional, Union as _Union

DESCRIPTOR: _descriptor.FileDescriptor

class ResponseStatus(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
    __slots__ = ()
    RESPONSE_STATUS_UNSPECIFIED: _ClassVar[ResponseStatus]
    RESPONSE_STATUS_SUCCESS: _ClassVar[ResponseStatus]
    RESPONSE_STATUS_ERROR: _ClassVar[ResponseStatus]
    RESPONSE_STATUS_PARTIAL: _ClassVar[ResponseStatus]

class AuthScheme(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
    __slots__ = ()
    AUTH_SCHEME_UNSPECIFIED: _ClassVar[AuthScheme]
    AUTH_SCHEME_BEARER: _ClassVar[AuthScheme]
    AUTH_SCHEME_API_KEY: _ClassVar[AuthScheme]
    AUTH_SCHEME_MTLS: _ClassVar[AuthScheme]

class Priority(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
    __slots__ = ()
    PRIORITY_UNSPECIFIED: _ClassVar[Priority]
    PRIORITY_LOW: _ClassVar[Priority]
    PRIORITY_NORMAL: _ClassVar[Priority]
    PRIORITY_HIGH: _ClassVar[Priority]
    PRIORITY_CRITICAL: _ClassVar[Priority]

class HealthStatus(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
    __slots__ = ()
    HEALTH_STATUS_UNSPECIFIED: _ClassVar[HealthStatus]
    HEALTH_STATUS_HEALTHY: _ClassVar[HealthStatus]
    HEALTH_STATUS_UNHEALTHY: _ClassVar[HealthStatus]
    HEALTH_STATUS_DEGRADED: _ClassVar[HealthStatus]
    HEALTH_STATUS_UNKNOWN: _ClassVar[HealthStatus]

class TaskStatus(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
    __slots__ = ()
    TASK_STATUS_UNSPECIFIED: _ClassVar[TaskStatus]
    TASK_STATUS_PENDING: _ClassVar[TaskStatus]
    TASK_STATUS_SCHEDULED: _ClassVar[TaskStatus]
    TASK_STATUS_RUNNING: _ClassVar[TaskStatus]
    TASK_STATUS_SUCCEEDED: _ClassVar[TaskStatus]
    TASK_STATUS_FAILED: _ClassVar[TaskStatus]
    TASK_STATUS_CANCELED: _ClassVar[TaskStatus]
    TASK_STATUS_RETRYING: _ClassVar[TaskStatus]

RESPONSE_STATUS_UNSPECIFIED: ResponseStatus
RESPONSE_STATUS_SUCCESS: ResponseStatus
RESPONSE_STATUS_ERROR: ResponseStatus
RESPONSE_STATUS_PARTIAL: ResponseStatus
AUTH_SCHEME_UNSPECIFIED: AuthScheme
AUTH_SCHEME_BEARER: AuthScheme
AUTH_SCHEME_API_KEY: AuthScheme
AUTH_SCHEME_MTLS: AuthScheme
PRIORITY_UNSPECIFIED: Priority
PRIORITY_LOW: Priority
PRIORITY_NORMAL: Priority
PRIORITY_HIGH: Priority
PRIORITY_CRITICAL: Priority
HEALTH_STATUS_UNSPECIFIED: HealthStatus
HEALTH_STATUS_HEALTHY: HealthStatus
HEALTH_STATUS_UNHEALTHY: HealthStatus
HEALTH_STATUS_DEGRADED: HealthStatus
HEALTH_STATUS_UNKNOWN: HealthStatus
TASK_STATUS_UNSPECIFIED: TaskStatus
TASK_STATUS_PENDING: TaskStatus
TASK_STATUS_SCHEDULED: TaskStatus
TASK_STATUS_RUNNING: TaskStatus
TASK_STATUS_SUCCEEDED: TaskStatus
TASK_STATUS_FAILED: TaskStatus
TASK_STATUS_CANCELED: TaskStatus
TASK_STATUS_RETRYING: TaskStatus

class Request(_message.Message):
    __slots__ = ("aduib_rpc", "id", "method", "name", "data", "trace_context", "metadata", "qos")
    ADUIB_RPC_FIELD_NUMBER: _ClassVar[int]
    ID_FIELD_NUMBER: _ClassVar[int]
    METHOD_FIELD_NUMBER: _ClassVar[int]
    NAME_FIELD_NUMBER: _ClassVar[int]
    DATA_FIELD_NUMBER: _ClassVar[int]
    TRACE_CONTEXT_FIELD_NUMBER: _ClassVar[int]
    METADATA_FIELD_NUMBER: _ClassVar[int]
    QOS_FIELD_NUMBER: _ClassVar[int]
    aduib_rpc: str
    id: str
    method: str
    name: str
    data: _struct_pb2.Struct
    trace_context: TraceContext
    metadata: RequestMetadata
    qos: QosConfig
    def __init__(
        self,
        aduib_rpc: _Optional[str] = ...,
        id: _Optional[str] = ...,
        method: _Optional[str] = ...,
        name: _Optional[str] = ...,
        data: _Optional[_Union[_struct_pb2.Struct, _Mapping]] = ...,
        trace_context: _Optional[_Union[TraceContext, _Mapping]] = ...,
        metadata: _Optional[_Union[RequestMetadata, _Mapping]] = ...,
        qos: _Optional[_Union[QosConfig, _Mapping]] = ...,
    ) -> None: ...

class Response(_message.Message):
    __slots__ = ("aduib_rpc", "id", "status", "result", "error", "trace_context", "metadata")
    ADUIB_RPC_FIELD_NUMBER: _ClassVar[int]
    ID_FIELD_NUMBER: _ClassVar[int]
    STATUS_FIELD_NUMBER: _ClassVar[int]
    RESULT_FIELD_NUMBER: _ClassVar[int]
    ERROR_FIELD_NUMBER: _ClassVar[int]
    TRACE_CONTEXT_FIELD_NUMBER: _ClassVar[int]
    METADATA_FIELD_NUMBER: _ClassVar[int]
    aduib_rpc: str
    id: str
    status: ResponseStatus
    result: _struct_pb2.Value
    error: RpcError
    trace_context: TraceContext
    metadata: ResponseMetadata
    def __init__(
        self,
        aduib_rpc: _Optional[str] = ...,
        id: _Optional[str] = ...,
        status: _Optional[_Union[ResponseStatus, str]] = ...,
        result: _Optional[_Union[_struct_pb2.Value, _Mapping]] = ...,
        error: _Optional[_Union[RpcError, _Mapping]] = ...,
        trace_context: _Optional[_Union[TraceContext, _Mapping]] = ...,
        metadata: _Optional[_Union[ResponseMetadata, _Mapping]] = ...,
    ) -> None: ...

class RpcError(_message.Message):
    __slots__ = ("code", "name", "message", "details", "debug")
    CODE_FIELD_NUMBER: _ClassVar[int]
    NAME_FIELD_NUMBER: _ClassVar[int]
    MESSAGE_FIELD_NUMBER: _ClassVar[int]
    DETAILS_FIELD_NUMBER: _ClassVar[int]
    DEBUG_FIELD_NUMBER: _ClassVar[int]
    code: int
    name: str
    message: str
    details: _containers.RepeatedCompositeFieldContainer[ErrorDetail]
    debug: DebugInfo
    def __init__(
        self,
        code: _Optional[int] = ...,
        name: _Optional[str] = ...,
        message: _Optional[str] = ...,
        details: _Optional[_Iterable[_Union[ErrorDetail, _Mapping]]] = ...,
        debug: _Optional[_Union[DebugInfo, _Mapping]] = ...,
    ) -> None: ...

class ErrorDetail(_message.Message):
    __slots__ = ("type", "field", "reason", "metadata")
    class MetadataEntry(_message.Message):
        __slots__ = ("key", "value")
        KEY_FIELD_NUMBER: _ClassVar[int]
        VALUE_FIELD_NUMBER: _ClassVar[int]
        key: str
        value: str
        def __init__(self, key: _Optional[str] = ..., value: _Optional[str] = ...) -> None: ...

    TYPE_FIELD_NUMBER: _ClassVar[int]
    FIELD_FIELD_NUMBER: _ClassVar[int]
    REASON_FIELD_NUMBER: _ClassVar[int]
    METADATA_FIELD_NUMBER: _ClassVar[int]
    type: str
    field: str
    reason: str
    metadata: _containers.ScalarMap[str, str]
    def __init__(
        self,
        type: _Optional[str] = ...,
        field: _Optional[str] = ...,
        reason: _Optional[str] = ...,
        metadata: _Optional[_Mapping[str, str]] = ...,
    ) -> None: ...

class DebugInfo(_message.Message):
    __slots__ = ("stack_trace", "internal_message", "timestamp_ms")
    STACK_TRACE_FIELD_NUMBER: _ClassVar[int]
    INTERNAL_MESSAGE_FIELD_NUMBER: _ClassVar[int]
    TIMESTAMP_MS_FIELD_NUMBER: _ClassVar[int]
    stack_trace: str
    internal_message: str
    timestamp_ms: int
    def __init__(
        self,
        stack_trace: _Optional[str] = ...,
        internal_message: _Optional[str] = ...,
        timestamp_ms: _Optional[int] = ...,
    ) -> None: ...

class TraceContext(_message.Message):
    __slots__ = ("trace_id", "span_id", "parent_span_id", "sampled", "baggage")
    class BaggageEntry(_message.Message):
        __slots__ = ("key", "value")
        KEY_FIELD_NUMBER: _ClassVar[int]
        VALUE_FIELD_NUMBER: _ClassVar[int]
        key: str
        value: str
        def __init__(self, key: _Optional[str] = ..., value: _Optional[str] = ...) -> None: ...

    TRACE_ID_FIELD_NUMBER: _ClassVar[int]
    SPAN_ID_FIELD_NUMBER: _ClassVar[int]
    PARENT_SPAN_ID_FIELD_NUMBER: _ClassVar[int]
    SAMPLED_FIELD_NUMBER: _ClassVar[int]
    BAGGAGE_FIELD_NUMBER: _ClassVar[int]
    trace_id: str
    span_id: str
    parent_span_id: str
    sampled: bool
    baggage: _containers.ScalarMap[str, str]
    def __init__(
        self,
        trace_id: _Optional[str] = ...,
        span_id: _Optional[str] = ...,
        parent_span_id: _Optional[str] = ...,
        sampled: bool = ...,
        baggage: _Optional[_Mapping[str, str]] = ...,
    ) -> None: ...

class RequestMetadata(_message.Message):
    __slots__ = (
        "timestamp_ms",
        "client_id",
        "client_version",
        "auth",
        "tenant_id",
        "headers",
        "long_task",
        "long_task_method",
        "long_task_timeout",
    )
    class HeadersEntry(_message.Message):
        __slots__ = ("key", "value")
        KEY_FIELD_NUMBER: _ClassVar[int]
        VALUE_FIELD_NUMBER: _ClassVar[int]
        key: str
        value: str
        def __init__(self, key: _Optional[str] = ..., value: _Optional[str] = ...) -> None: ...

    TIMESTAMP_MS_FIELD_NUMBER: _ClassVar[int]
    CLIENT_ID_FIELD_NUMBER: _ClassVar[int]
    CLIENT_VERSION_FIELD_NUMBER: _ClassVar[int]
    AUTH_FIELD_NUMBER: _ClassVar[int]
    TENANT_ID_FIELD_NUMBER: _ClassVar[int]
    HEADERS_FIELD_NUMBER: _ClassVar[int]
    LONG_TASK_FIELD_NUMBER: _ClassVar[int]
    LONG_TASK_METHOD_FIELD_NUMBER: _ClassVar[int]
    LONG_TASK_TIMEOUT_FIELD_NUMBER: _ClassVar[int]
    timestamp_ms: int
    client_id: str
    client_version: str
    auth: AuthContext
    tenant_id: str
    headers: _containers.ScalarMap[str, str]
    long_task: bool
    long_task_method: str
    long_task_timeout: int
    def __init__(
        self,
        timestamp_ms: _Optional[int] = ...,
        client_id: _Optional[str] = ...,
        client_version: _Optional[str] = ...,
        auth: _Optional[_Union[AuthContext, _Mapping]] = ...,
        tenant_id: _Optional[str] = ...,
        headers: _Optional[_Mapping[str, str]] = ...,
        long_task: bool = ...,
        long_task_method: _Optional[str] = ...,
        long_task_timeout: _Optional[int] = ...,
    ) -> None: ...

class ResponseMetadata(_message.Message):
    __slots__ = ("timestamp_ms", "duration_ms", "server_id", "server_version")
    TIMESTAMP_MS_FIELD_NUMBER: _ClassVar[int]
    DURATION_MS_FIELD_NUMBER: _ClassVar[int]
    SERVER_ID_FIELD_NUMBER: _ClassVar[int]
    SERVER_VERSION_FIELD_NUMBER: _ClassVar[int]
    timestamp_ms: int
    duration_ms: int
    server_id: str
    server_version: str
    def __init__(
        self,
        timestamp_ms: _Optional[int] = ...,
        duration_ms: _Optional[int] = ...,
        server_id: _Optional[str] = ...,
        server_version: _Optional[str] = ...,
    ) -> None: ...

class AuthContext(_message.Message):
    __slots__ = ("scheme", "credentials", "principal", "roles")
    SCHEME_FIELD_NUMBER: _ClassVar[int]
    CREDENTIALS_FIELD_NUMBER: _ClassVar[int]
    PRINCIPAL_FIELD_NUMBER: _ClassVar[int]
    ROLES_FIELD_NUMBER: _ClassVar[int]
    scheme: AuthScheme
    credentials: str
    principal: str
    roles: _containers.RepeatedScalarFieldContainer[str]
    def __init__(
        self,
        scheme: _Optional[_Union[AuthScheme, str]] = ...,
        credentials: _Optional[str] = ...,
        principal: _Optional[str] = ...,
        roles: _Optional[_Iterable[str]] = ...,
    ) -> None: ...

class QosConfig(_message.Message):
    __slots__ = ("priority", "timeout_ms", "retry", "idempotency_key")
    PRIORITY_FIELD_NUMBER: _ClassVar[int]
    TIMEOUT_MS_FIELD_NUMBER: _ClassVar[int]
    RETRY_FIELD_NUMBER: _ClassVar[int]
    IDEMPOTENCY_KEY_FIELD_NUMBER: _ClassVar[int]
    priority: Priority
    timeout_ms: int
    retry: RetryConfig
    idempotency_key: str
    def __init__(
        self,
        priority: _Optional[_Union[Priority, str]] = ...,
        timeout_ms: _Optional[int] = ...,
        retry: _Optional[_Union[RetryConfig, _Mapping]] = ...,
        idempotency_key: _Optional[str] = ...,
    ) -> None: ...

class RetryConfig(_message.Message):
    __slots__ = ("max_attempts", "initial_delay_ms", "max_delay_ms", "backoff_multiplier", "retryable_codes")
    MAX_ATTEMPTS_FIELD_NUMBER: _ClassVar[int]
    INITIAL_DELAY_MS_FIELD_NUMBER: _ClassVar[int]
    MAX_DELAY_MS_FIELD_NUMBER: _ClassVar[int]
    BACKOFF_MULTIPLIER_FIELD_NUMBER: _ClassVar[int]
    RETRYABLE_CODES_FIELD_NUMBER: _ClassVar[int]
    max_attempts: int
    initial_delay_ms: int
    max_delay_ms: int
    backoff_multiplier: float
    retryable_codes: _containers.RepeatedScalarFieldContainer[int]
    def __init__(
        self,
        max_attempts: _Optional[int] = ...,
        initial_delay_ms: _Optional[int] = ...,
        max_delay_ms: _Optional[int] = ...,
        backoff_multiplier: _Optional[float] = ...,
        retryable_codes: _Optional[_Iterable[int]] = ...,
    ) -> None: ...

class TaskRecord(_message.Message):
    __slots__ = (
        "task_id",
        "parent_task_id",
        "status",
        "priority",
        "created_at_ms",
        "scheduled_at_ms",
        "started_at_ms",
        "completed_at_ms",
        "attempt",
        "max_attempts",
        "next_retry_at_ms",
        "result",
        "error",
        "progress",
        "metadata",
        "tags",
    )
    class MetadataEntry(_message.Message):
        __slots__ = ("key", "value")
        KEY_FIELD_NUMBER: _ClassVar[int]
        VALUE_FIELD_NUMBER: _ClassVar[int]
        key: str
        value: str
        def __init__(self, key: _Optional[str] = ..., value: _Optional[str] = ...) -> None: ...

    TASK_ID_FIELD_NUMBER: _ClassVar[int]
    PARENT_TASK_ID_FIELD_NUMBER: _ClassVar[int]
    STATUS_FIELD_NUMBER: _ClassVar[int]
    PRIORITY_FIELD_NUMBER: _ClassVar[int]
    CREATED_AT_MS_FIELD_NUMBER: _ClassVar[int]
    SCHEDULED_AT_MS_FIELD_NUMBER: _ClassVar[int]
    STARTED_AT_MS_FIELD_NUMBER: _ClassVar[int]
    COMPLETED_AT_MS_FIELD_NUMBER: _ClassVar[int]
    ATTEMPT_FIELD_NUMBER: _ClassVar[int]
    MAX_ATTEMPTS_FIELD_NUMBER: _ClassVar[int]
    NEXT_RETRY_AT_MS_FIELD_NUMBER: _ClassVar[int]
    RESULT_FIELD_NUMBER: _ClassVar[int]
    ERROR_FIELD_NUMBER: _ClassVar[int]
    PROGRESS_FIELD_NUMBER: _ClassVar[int]
    METADATA_FIELD_NUMBER: _ClassVar[int]
    TAGS_FIELD_NUMBER: _ClassVar[int]
    task_id: str
    parent_task_id: str
    status: TaskStatus
    priority: Priority
    created_at_ms: int
    scheduled_at_ms: int
    started_at_ms: int
    completed_at_ms: int
    attempt: int
    max_attempts: int
    next_retry_at_ms: int
    result: _struct_pb2.Value
    error: RpcError
    progress: TaskProgress
    metadata: _containers.ScalarMap[str, str]
    tags: _containers.RepeatedScalarFieldContainer[str]
    def __init__(
        self,
        task_id: _Optional[str] = ...,
        parent_task_id: _Optional[str] = ...,
        status: _Optional[_Union[TaskStatus, str]] = ...,
        priority: _Optional[_Union[Priority, str]] = ...,
        created_at_ms: _Optional[int] = ...,
        scheduled_at_ms: _Optional[int] = ...,
        started_at_ms: _Optional[int] = ...,
        completed_at_ms: _Optional[int] = ...,
        attempt: _Optional[int] = ...,
        max_attempts: _Optional[int] = ...,
        next_retry_at_ms: _Optional[int] = ...,
        result: _Optional[_Union[_struct_pb2.Value, _Mapping]] = ...,
        error: _Optional[_Union[RpcError, _Mapping]] = ...,
        progress: _Optional[_Union[TaskProgress, _Mapping]] = ...,
        metadata: _Optional[_Mapping[str, str]] = ...,
        tags: _Optional[_Iterable[str]] = ...,
    ) -> None: ...

class TaskProgress(_message.Message):
    __slots__ = ("current", "total", "message", "percentage")
    CURRENT_FIELD_NUMBER: _ClassVar[int]
    TOTAL_FIELD_NUMBER: _ClassVar[int]
    MESSAGE_FIELD_NUMBER: _ClassVar[int]
    PERCENTAGE_FIELD_NUMBER: _ClassVar[int]
    current: int
    total: int
    message: str
    percentage: float
    def __init__(
        self,
        current: _Optional[int] = ...,
        total: _Optional[int] = ...,
        message: _Optional[str] = ...,
        percentage: _Optional[float] = ...,
    ) -> None: ...

class TaskSubmitRequest(_message.Message):
    __slots__ = ("target_method", "params", "priority")
    TARGET_METHOD_FIELD_NUMBER: _ClassVar[int]
    PARAMS_FIELD_NUMBER: _ClassVar[int]
    PRIORITY_FIELD_NUMBER: _ClassVar[int]
    target_method: str
    params: _struct_pb2.Struct
    priority: Priority
    def __init__(
        self,
        target_method: _Optional[str] = ...,
        params: _Optional[_Union[_struct_pb2.Struct, _Mapping]] = ...,
        priority: _Optional[_Union[Priority, str]] = ...,
    ) -> None: ...

class TaskSubmitResponse(_message.Message):
    __slots__ = ("task_id", "status", "created_at_ms")
    TASK_ID_FIELD_NUMBER: _ClassVar[int]
    STATUS_FIELD_NUMBER: _ClassVar[int]
    CREATED_AT_MS_FIELD_NUMBER: _ClassVar[int]
    task_id: str
    status: TaskStatus
    created_at_ms: int
    def __init__(
        self,
        task_id: _Optional[str] = ...,
        status: _Optional[_Union[TaskStatus, str]] = ...,
        created_at_ms: _Optional[int] = ...,
    ) -> None: ...

class TaskQueryRequest(_message.Message):
    __slots__ = ("task_id",)
    TASK_ID_FIELD_NUMBER: _ClassVar[int]
    task_id: str
    def __init__(self, task_id: _Optional[str] = ...) -> None: ...

class TaskQueryResponse(_message.Message):
    __slots__ = ("task",)
    TASK_FIELD_NUMBER: _ClassVar[int]
    task: TaskRecord
    def __init__(self, task: _Optional[_Union[TaskRecord, _Mapping]] = ...) -> None: ...

class TaskCancelRequest(_message.Message):
    __slots__ = ("task_id", "reason")
    TASK_ID_FIELD_NUMBER: _ClassVar[int]
    REASON_FIELD_NUMBER: _ClassVar[int]
    task_id: str
    reason: str
    def __init__(self, task_id: _Optional[str] = ..., reason: _Optional[str] = ...) -> None: ...

class TaskCancelResponse(_message.Message):
    __slots__ = ("task_id", "status", "canceled")
    TASK_ID_FIELD_NUMBER: _ClassVar[int]
    STATUS_FIELD_NUMBER: _ClassVar[int]
    CANCELED_FIELD_NUMBER: _ClassVar[int]
    task_id: str
    status: TaskStatus
    canceled: bool
    def __init__(
        self, task_id: _Optional[str] = ..., status: _Optional[_Union[TaskStatus, str]] = ..., canceled: bool = ...
    ) -> None: ...

class TaskSubscribeRequest(_message.Message):
    __slots__ = ("task_id", "events")
    TASK_ID_FIELD_NUMBER: _ClassVar[int]
    EVENTS_FIELD_NUMBER: _ClassVar[int]
    task_id: str
    events: _containers.RepeatedScalarFieldContainer[str]
    def __init__(self, task_id: _Optional[str] = ..., events: _Optional[_Iterable[str]] = ...) -> None: ...

class TaskEvent(_message.Message):
    __slots__ = ("event", "task", "timestamp_ms")
    EVENT_FIELD_NUMBER: _ClassVar[int]
    TASK_FIELD_NUMBER: _ClassVar[int]
    TIMESTAMP_MS_FIELD_NUMBER: _ClassVar[int]
    event: str
    task: TaskRecord
    timestamp_ms: int
    def __init__(
        self,
        event: _Optional[str] = ...,
        task: _Optional[_Union[TaskRecord, _Mapping]] = ...,
        timestamp_ms: _Optional[int] = ...,
    ) -> None: ...

class HealthCheckRequest(_message.Message):
    __slots__ = ("service",)
    SERVICE_FIELD_NUMBER: _ClassVar[int]
    service: str
    def __init__(self, service: _Optional[str] = ...) -> None: ...

class HealthCheckResponse(_message.Message):
    __slots__ = ("status", "services")
    class ServicesEntry(_message.Message):
        __slots__ = ("key", "value")
        KEY_FIELD_NUMBER: _ClassVar[int]
        VALUE_FIELD_NUMBER: _ClassVar[int]
        key: str
        value: HealthStatus
        def __init__(self, key: _Optional[str] = ..., value: _Optional[_Union[HealthStatus, str]] = ...) -> None: ...

    STATUS_FIELD_NUMBER: _ClassVar[int]
    SERVICES_FIELD_NUMBER: _ClassVar[int]
    status: HealthStatus
    services: _containers.ScalarMap[str, HealthStatus]
    def __init__(
        self, status: _Optional[_Union[HealthStatus, str]] = ..., services: _Optional[_Mapping[str, HealthStatus]] = ...
    ) -> None: ...
