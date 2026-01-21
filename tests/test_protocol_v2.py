from __future__ import annotations

import re
import uuid
from typing import Any

import pytest
from pydantic import ValidationError

from aduib_rpc.exceptions import BadRequestError, InvalidParamsError, RpcException
from aduib_rpc.protocol.compatibility import (
    negotiate_version,
    v1_to_v2_request,
    v2_to_v1_response,
)
from aduib_rpc.protocol.v2.metadata import (
    AuthScheme,
    Compression,
    ContentType,
    Pagination,
    RequestMetadata,
    ResponseMetadata,
)
from aduib_rpc.protocol.v2.qos import Priority, QosConfig, RetryConfig
from aduib_rpc.protocol.v2.stream import StreamMessage, StreamMessageType, StreamPayload, StreamState
from aduib_rpc.protocol.v2.types import (
    AduibRpcRequest,
    AduibRpcResponse,
    ErrorDetail,
    ResponseStatus,
    RpcError,
    TraceContext,
)
from aduib_rpc.types import AduibRpcRequest as V1Request

TRACE_ID_HEX = "0123456789abcdef0123456789abcdef"
SPAN_ID_HEX = "0123456789abcdef"
TRACE_ID_RE = re.compile(r"^[0-9a-fA-F]{32}$")
SPAN_ID_RE = re.compile(r"^[0-9a-fA-F]{16}$")


@pytest.fixture()
def trace_context_data() -> dict[str, Any]:
    """Return a valid trace context payload."""
    return {
        "trace_id": TRACE_ID_HEX,
        "span_id": SPAN_ID_HEX,
        "parent_span_id": "abcdef0123456789",
        "sampled": True,
        "baggage": {"region": "us-east-1", "tenant": "alpha"},
    }


@pytest.fixture()
def trace_context(trace_context_data: dict[str, Any]) -> TraceContext:
    """Build a TraceContext from the standard fixture data."""
    return TraceContext.model_validate(trace_context_data)


@pytest.fixture()
def error_details_payload() -> list[dict[str, Any]]:
    """Return a list of error detail dictionaries."""
    return [
        {"type": "urn:aduib:errors:invalid", "field": "limit", "reason": "too large"},
        {"type": "urn:aduib:errors:missing", "field": "name", "reason": "required"},
    ]


@pytest.fixture()
def error_details_objects(error_details_payload: list[dict[str, Any]]) -> list[ErrorDetail]:
    """Return error detail objects derived from payloads."""
    return [ErrorDetail.model_validate(item) for item in error_details_payload]


@pytest.fixture()
def request_metadata() -> RequestMetadata:
    """Return a RequestMetadata instance with deterministic values."""
    return RequestMetadata(
        timestamp_ms=1700000000000,
        client_id="client-123",
        client_version="1.2.3",
        tenant_id="tenant-1",
        accept=[ContentType.JSON, ContentType.MSGPACK],
        compression=Compression.GZIP,
        headers={"x-trace": "trace"},
    )


@pytest.fixture()
def qos_config() -> QosConfig:
    """Return a QosConfig instance for reuse in tests."""
    retry = RetryConfig(max_attempts=4, initial_delay_ms=200, max_delay_ms=800)
    return QosConfig(priority=Priority.HIGH, timeout_ms=5000, retry=retry)


@pytest.fixture()
def v2_request(trace_context: TraceContext, request_metadata: RequestMetadata, qos_config: QosConfig) -> AduibRpcRequest:
    """Create a v2 request fixture with nested metadata and QoS."""
    return AduibRpcRequest(
        id="req-123",
        method="rpc.v2/service/handler",
        name="service",
        data={"value": 42},
        trace_context=trace_context,
        metadata=request_metadata,
        qos=qos_config,
    )


@pytest.fixture()
def v2_success_response(trace_context: TraceContext) -> AduibRpcResponse:
    """Create a successful v2 response fixture."""
    return AduibRpcResponse(
        id="req-123",
        status=ResponseStatus.SUCCESS,
        result={"ok": True},
        trace_context=trace_context,
    )


def _compute_has_next(total: int, page: int, page_size: int) -> bool:
    """Compute whether another page of results exists."""
    return page * page_size < total


@pytest.mark.parametrize(
    "member, expected",
    [
        (ResponseStatus.SUCCESS, "success"),
        (ResponseStatus.ERROR, "error"),
        (ResponseStatus.PARTIAL, "partial"),
    ],
)
def test_response_status_values(member: ResponseStatus, expected: str) -> None:
    """Validate ResponseStatus enum values."""
    assert member.value == expected


def test_trace_context_accepts_valid_ids(trace_context: TraceContext) -> None:
    """Accept valid trace and span identifiers."""
    assert TRACE_ID_RE.fullmatch(trace_context.trace_id)
    assert SPAN_ID_RE.fullmatch(trace_context.span_id)


def test_trace_context_baggage_optional() -> None:
    """Allow trace context instances without baggage."""
    context = TraceContext(trace_id=TRACE_ID_HEX, span_id=SPAN_ID_HEX)
    assert context.baggage is None


@pytest.mark.parametrize(
    "trace_id",
    [
        "xyz",
        "g123456789abcdef0123456789abcde",
        "0123456789abcdef0123456789abcde",
    ],
)
def test_trace_context_invalid_trace_id(trace_id: str) -> None:
    """Reject trace IDs that are not 32-character hex strings."""
    with pytest.raises(ValidationError):
        TraceContext(trace_id=trace_id, span_id=SPAN_ID_HEX)


@pytest.mark.parametrize(
    "span_id",
    [
        "xyz",
        "g123456789abcdef",
        "0123456789abcde",
    ],
)
def test_trace_context_invalid_span_id(span_id: str) -> None:
    """Reject span IDs that are not 16-character hex strings."""
    with pytest.raises(ValidationError):
        TraceContext(trace_id=TRACE_ID_HEX, span_id=span_id)


def test_trace_context_validator_raises_value_error() -> None:
    """Raise ValueError when validators see invalid hex strings."""
    with pytest.raises(ValueError):
        TraceContext.validate_trace_id("invalid")
    with pytest.raises(ValueError):
        TraceContext.validate_span_id("invalid")


def test_rpc_error_from_exception_maps_basic_fields() -> None:
    """Map exception fields into RpcError attributes."""
    exc = BadRequestError(message="bad input")
    error = RpcError.from_exception(exc)
    assert error.code == exc.code
    assert error.message == "bad input"
    assert error.name == "BAD_REQUEST"
    assert error.details is None


def test_rpc_error_from_exception_maps_details_list(error_details_payload: list[dict[str, Any]]) -> None:
    """Convert detail payloads into ErrorDetail objects."""
    exc = InvalidParamsError(message="invalid", data=error_details_payload)
    error = RpcError.from_exception(exc)
    assert error.details is not None
    assert all(isinstance(detail, ErrorDetail) for detail in error.details)
    assert error.details[0].field == "limit"


def test_rpc_error_from_exception_ignores_non_list_data() -> None:
    """Ignore non-list data when building RpcError details."""
    exc = RpcException(code=9999, message="unknown", data={"key": "value"})
    error = RpcError.from_exception(exc)
    assert error.details is None


def test_aduib_rpc_request_default_version() -> None:
    """Default aduib_rpc version should be 2.0 for v2 requests."""
    request = AduibRpcRequest(id="req-1", method="rpc.v2/service/handler")
    assert request.aduib_rpc == "2.0"


def test_aduib_rpc_request_roundtrip(v2_request: AduibRpcRequest) -> None:
    """Round-trip serialize and deserialize v2 requests.

    Note: metadata and qos fields use Any type to avoid circular imports,
    so we compare the serialized dumps instead of object equality.
    """
    payload = v2_request.model_dump()
    restored = AduibRpcRequest.model_validate(payload)
    # Compare dumps since metadata/qos remain as dicts after roundtrip
    assert restored.model_dump() == payload


@pytest.mark.parametrize(
    "status, error, expected",
    [
        (ResponseStatus.SUCCESS, None, True),
        (ResponseStatus.ERROR, None, False),
        (ResponseStatus.SUCCESS, RpcError(code=4000, name="ERR", message="boom"), False),
        (ResponseStatus.PARTIAL, None, False),
    ],
)
def test_aduib_rpc_response_is_success(
    status: ResponseStatus, error: RpcError | None, expected: bool
) -> None:
    """Return success only when status is SUCCESS and error is None."""
    response = AduibRpcResponse(id="req-1", status=status, error=error)
    assert response.is_success() is expected


def test_aduib_rpc_response_rejects_result_and_error() -> None:
    """Reject responses that include both result and error."""
    with pytest.raises(ValidationError):
        AduibRpcResponse(
            id="req-1",
            status=ResponseStatus.ERROR,
            result={"ok": False},
            error=RpcError(code=4000, name="ERR", message="boom"),
        )


@pytest.mark.parametrize(
    "member, expected",
    [
        (AuthScheme.BEARER, "bearer"),
        (AuthScheme.API_KEY, "api_key"),
        (AuthScheme.MTLS, "mtls"),
        (AuthScheme.BASIC, "basic"),
    ],
)
def test_auth_scheme_values(member: AuthScheme, expected: str) -> None:
    """Validate AuthScheme enum values."""
    assert member.value == expected


@pytest.mark.parametrize(
    "member, expected",
    [
        (ContentType.JSON, "application/json"),
        (ContentType.MSGPACK, "application/msgpack"),
        (ContentType.PROTOBUF, "application/protobuf"),
        (ContentType.AVRO, "application/avro"),
    ],
)
def test_content_type_values(member: ContentType, expected: str) -> None:
    """Validate ContentType enum values."""
    assert member.value == expected


@pytest.mark.parametrize(
    "member, expected",
    [
        (Compression.NONE, "none"),
        (Compression.GZIP, "gzip"),
        (Compression.ZSTD, "zstd"),
        (Compression.LZ4, "lz4"),
    ],
)
def test_compression_values(member: Compression, expected: str) -> None:
    """Validate Compression enum values."""
    assert member.value == expected


def test_request_metadata_defaults() -> None:
    """Use default values for optional request metadata fields."""
    meta = RequestMetadata(timestamp_ms=1700000000000)
    assert meta.content_type == ContentType.JSON
    assert meta.accept is None
    assert meta.compression is None


def test_request_metadata_accepts_custom_values(request_metadata: RequestMetadata) -> None:
    """Accept populated metadata fields without validation errors."""
    assert request_metadata.content_type == ContentType.JSON
    assert request_metadata.compression == Compression.GZIP
    assert request_metadata.headers == {"x-trace": "trace"}


@pytest.mark.parametrize("content_type", ["text/plain", "application/xml"])
def test_request_metadata_rejects_invalid_content_type(content_type: str) -> None:
    """Reject unsupported content types."""
    with pytest.raises(ValidationError):
        RequestMetadata(timestamp_ms=1700000000000, content_type=content_type)


@pytest.mark.parametrize(
    "payload",
    [
        {"timestamp_ms": 1700000000000},
        {"timestamp_ms": 1700000000000, "duration_ms": None},
    ],
)
def test_response_metadata_allows_optional_duration(payload: dict[str, Any]) -> None:
    """Allow omitting or nulling duration_ms in response metadata."""
    meta = ResponseMetadata.model_validate(payload)
    assert meta.timestamp_ms == 1700000000000


@pytest.mark.parametrize("page", [0, -1])
def test_pagination_page_validation(page: int) -> None:
    """Reject pagination pages less than 1."""
    with pytest.raises(ValidationError):
        Pagination(total=10, page=page, page_size=5, has_next=False)


@pytest.mark.parametrize("page_size", [0, -10])
def test_pagination_page_size_validation(page_size: int) -> None:
    """Reject pagination page sizes less than 1."""
    with pytest.raises(ValidationError):
        Pagination(total=10, page=1, page_size=page_size, has_next=False)


@pytest.mark.parametrize(
    "total, page, page_size, expected",
    [
        (5, 1, 10, False),
        (25, 1, 10, True),
        (25, 2, 10, True),
        (25, 3, 10, False),
        (100, 9, 10, True),
    ],
)
def test_pagination_has_next_calculation(
    total: int, page: int, page_size: int, expected: bool
) -> None:
    """Store the calculated has_next value for pagination."""
    has_next = _compute_has_next(total, page, page_size)
    pagination = Pagination(
        total=total,
        page=page,
        page_size=page_size,
        has_next=has_next,
    )
    assert pagination.has_next is expected


def test_priority_enum_values() -> None:
    """Validate Priority enum numeric values."""
    assert {member.name: member.value for member in Priority} == {
        "LOW": 0,
        "NORMAL": 1,
        "HIGH": 2,
        "CRITICAL": 3,
    }


@pytest.mark.parametrize("max_attempts", [0, -1])
def test_retry_config_rejects_invalid_max_attempts(max_attempts: int) -> None:
    """Reject retry configurations with invalid max_attempts."""
    with pytest.raises(ValidationError):
        RetryConfig(max_attempts=max_attempts)


def test_retry_config_rejects_invalid_max_delay() -> None:
    """Reject max_delay_ms values below initial_delay_ms."""
    with pytest.raises(ValidationError):
        RetryConfig(initial_delay_ms=200, max_delay_ms=100)


def test_retry_config_rejects_invalid_initial_delay() -> None:
    """Reject non-positive initial_delay_ms values."""
    with pytest.raises(ValidationError):
        RetryConfig(initial_delay_ms=0)


def test_retry_config_defaults() -> None:
    """Apply expected default retry configuration values."""
    retry = RetryConfig()
    assert retry.max_attempts == 3
    assert retry.initial_delay_ms == 100
    assert retry.max_delay_ms == 10000


def test_qos_config_defaults() -> None:
    """Use defaults for QoS configuration values."""
    qos = QosConfig()
    assert qos.priority == Priority.NORMAL
    assert qos.retry is None


def test_qos_config_accepts_retry(qos_config: QosConfig) -> None:
    """Accept retry configurations embedded in QoS."""
    assert qos_config.retry is not None
    assert qos_config.retry.max_attempts == 4


def test_qos_config_timeout_validation() -> None:
    """Reject non-positive timeout values."""
    with pytest.raises(ValidationError):
        QosConfig(timeout_ms=0)


@pytest.mark.parametrize(
    "member, expected",
    [
        (StreamMessageType.DATA, "data"),
        (StreamMessageType.HEARTBEAT, "heartbeat"),
        (StreamMessageType.ERROR, "error"),
        (StreamMessageType.END, "end"),
        (StreamMessageType.CANCEL, "cancel"),
        (StreamMessageType.ACK, "ack"),
    ],
)
def test_stream_message_type_values(member: StreamMessageType, expected: str) -> None:
    """Validate StreamMessageType enum values."""
    assert member.value == expected


@pytest.mark.parametrize(
    "member, expected",
    [
        (StreamState.CREATED, "created"),
        (StreamState.ACTIVE, "active"),
        (StreamState.ERROR, "error"),
        (StreamState.CANCELLED, "cancelled"),
        (StreamState.COMPLETED, "completed"),
    ],
)
def test_stream_state_values(member: StreamState, expected: str) -> None:
    """Validate StreamState enum values."""
    assert member.value == expected


def test_stream_message_accepts_zero_sequence() -> None:
    """Allow stream messages to start at sequence 0."""
    payload = StreamPayload(data={"chunk": 1})
    message = StreamMessage(
        type=StreamMessageType.DATA,
        sequence=0,
        payload=payload,
        timestamp_ms=1700000000000,
    )
    assert message.sequence == 0


@pytest.mark.parametrize("sequence", [-1, -10])
def test_stream_message_rejects_negative_sequence(sequence: int) -> None:
    """Reject negative sequence values."""
    with pytest.raises(ValidationError):
        StreamMessage(
            type=StreamMessageType.DATA,
            sequence=sequence,
            payload=None,
            timestamp_ms=1700000000000,
        )


@pytest.mark.parametrize(
    "request_id",
    [
        None,
        123,
        "req-abc",
    ],
)
def test_v1_to_v2_request_maps_fields(request_id: str | int | None) -> None:
    """Map basic fields and generate trace context during conversion."""
    v1_request = V1Request(method="rpc.v1/service/handler", data={"x": 1}, id=request_id)
    v2_request = v1_to_v2_request(v1_request)
    assert v2_request.aduib_rpc == "2.0"
    assert v2_request.method == "rpc.v1/service/handler"
    assert v2_request.data == {"x": 1}
    assert v2_request.trace_context is not None
    assert TRACE_ID_RE.fullmatch(v2_request.trace_context.trace_id)
    assert SPAN_ID_RE.fullmatch(v2_request.trace_context.span_id)
    if request_id is None:
        uuid.UUID(v2_request.id)
    else:
        assert v2_request.id == str(request_id)


def test_v1_to_v2_request_sets_metadata_timestamp() -> None:
    """Attach request metadata with a timestamp during conversion."""
    v1_request = V1Request(method="rpc.v1/service/handler", data={"x": 1}, id="req-1")
    v2_request = v1_to_v2_request(v1_request)
    assert v2_request.metadata is not None
    assert isinstance(v2_request.metadata, RequestMetadata)
    assert v2_request.metadata.timestamp_ms > 0


def test_v2_to_v1_response_maps_success(v2_success_response: AduibRpcResponse) -> None:
    """Map success responses to v1 envelopes."""
    v1_response = v2_to_v1_response(v2_success_response)
    assert v1_response.status == "success"
    assert v1_response.result == {"ok": True}
    assert v1_response.error is None


def test_v2_to_v1_response_maps_error(error_details_objects: list[ErrorDetail]) -> None:
    """Map error responses to v1 envelopes with extra data."""
    v2_error = RpcError(
        code=4000,
        name="RESOURCE_NOT_FOUND",
        message="missing",
        details=error_details_objects,
    )
    v2_response = AduibRpcResponse(id="req-1", status=ResponseStatus.ERROR, error=v2_error)
    v1_response = v2_to_v1_response(v2_response)
    assert v1_response.status == "error"
    assert v1_response.error is not None
    assert v1_response.error.code == 4000
    assert v1_response.error.message == "missing"
    assert v1_response.error.data is not None
    assert v1_response.error.data["name"] == "RESOURCE_NOT_FOUND"
    assert v1_response.error.data["details"] == error_details_objects


def test_negotiate_version_prefers_v2() -> None:
    """Prefer version 2.0 when both sides support it."""
    version = negotiate_version(["1.0", "2.0"], ["2.0", "1.0"])
    assert version == "2.0"


def test_negotiate_version_falls_back_to_v1() -> None:
    """Fall back to version 1.0 when 2.0 is unavailable."""
    version = negotiate_version(["1.0"], ["1.0", "2.0"])
    assert version == "1.0"


def test_negotiate_version_no_compatible_versions() -> None:
    """Raise ValueError when no compatible versions exist."""
    with pytest.raises(ValueError):
        negotiate_version(["3.0"], ["2.0"])
