from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest

from aduib_rpc.exceptions import (
    AlreadyExistsError,
    BadRequestError,
    CircuitBreakerOpenError,
    CompressionError,
    ConflictError,
    DependencyError,
    GoneError,
    InsufficientScopeError,
    InternalError,
    InvalidFieldValueError,
    InvalidMessageError,
    InvalidParamsError,
    InvalidTokenError,
    MethodNotFoundError,
    MissingRequiredFieldError,
    PermissionDeniedError,
    ProtocolError,
    RateLimitedError,
    ResourceExhaustedError,
    ResourceNotFoundError,
    RequestTooLargeError,
    RpcException,
    RpcNotImplementedError,
    RpcTimeoutError,
    SerializationError,
    ServiceNotFoundError,
    ServiceUnavailableError,
    TokenExpiredError,
    UnauthenticatedError,
    UnauthorizedError,
    UnsupportedVersionError,
    UpstreamTimeoutError,
    UpstreamUnavailableError,
)
from aduib_rpc.protocol.v2.errors import (
    ERROR_CODE_NAMES,
    ErrorCode,
    error_code_to_grpc_status,
    error_code_to_http_status,
    exception_from_code,
)


EXCEPTION_DEFAULTS = [
    (ProtocolError, 1000, "Protocol error"),
    (UnsupportedVersionError, 1001, "Unsupported protocol version"),
    (InvalidMessageError, 1002, "Invalid message"),
    (SerializationError, 1003, "Serialization error"),
    (CompressionError, 1004, "Compression error"),
    (BadRequestError, 2000, "Bad request"),
    (InvalidParamsError, 2001, "Invalid params"),
    (MissingRequiredFieldError, 2002, "Missing required field"),
    (InvalidFieldValueError, 2003, "Invalid field value"),
    (RequestTooLargeError, 2004, "Request too large"),
    (UnauthenticatedError, 3000, "Unauthenticated"),
    (InvalidTokenError, 3001, "Invalid token"),
    (TokenExpiredError, 3002, "Token expired"),
    (UnauthorizedError, 3010, "Unauthorized"),
    (PermissionDeniedError, 3011, "Permission denied"),
    (InsufficientScopeError, 3012, "Insufficient scope"),
    (ResourceNotFoundError, 4000, "Resource not found"),
    (MethodNotFoundError, 4001, "Method not found"),
    (ServiceNotFoundError, 4002, "Service not found"),
    (AlreadyExistsError, 4010, "Already exists"),
    (ConflictError, 4011, "Conflict"),
    (GoneError, 4020, "Gone"),
    (InternalError, 5000, "Internal error"),
    (RpcNotImplementedError, 5001, "Not implemented"),
    (ServiceUnavailableError, 5002, "Service unavailable"),
    (RpcTimeoutError, 5003, "RPC timeout"),
    (CircuitBreakerOpenError, 5010, "Circuit breaker open"),
    (RateLimitedError, 5020, "Rate limited"),
    (ResourceExhaustedError, 5021, "Resource exhausted"),
    (DependencyError, 6000, "Dependency error"),
    (UpstreamTimeoutError, 6001, "Upstream timeout"),
    (UpstreamUnavailableError, 6002, "Upstream unavailable"),
]


@pytest.mark.parametrize("exc_class, expected_code, expected_message", EXCEPTION_DEFAULTS)
def test_all_exception_classes_have_default_code(exc_class, expected_code, expected_message):
    """Ensure every exception class has the expected default code."""
    exc = exc_class()
    assert exc.code == expected_code


@pytest.mark.parametrize("exc_class, expected_code, expected_message", EXCEPTION_DEFAULTS)
def test_all_exception_classes_have_default_message(
    exc_class, expected_code, expected_message
):
    """Ensure every exception class has the expected default message."""
    exc = exc_class()
    assert exc.message == expected_message


@pytest.mark.parametrize("exc_class, expected_code, expected_message", EXCEPTION_DEFAULTS)
def test_exception_can_override_message(exc_class, expected_code, expected_message):
    """Allow overriding the default message without changing the code."""
    custom_message = "custom message"
    exc = exc_class(message=custom_message)
    assert exc.code == expected_code
    assert exc.message == custom_message


@pytest.mark.parametrize("exc_class, expected_code, expected_message", EXCEPTION_DEFAULTS)
def test_exception_can_provide_data(exc_class, expected_code, expected_message):
    """Allow attaching custom data to exception instances."""
    payload = {"detail": "extra context"}
    exc = exc_class(data=payload)
    assert exc.code == expected_code
    assert exc.data == payload


@pytest.mark.parametrize(
    "exc_class, range_start, range_end",
    [
        (ProtocolError, 1000, 2000),
        (UnsupportedVersionError, 1000, 2000),
        (InvalidMessageError, 1000, 2000),
        (SerializationError, 1000, 2000),
        (CompressionError, 1000, 2000),
        (BadRequestError, 2000, 3000),
        (InvalidParamsError, 2000, 3000),
        (MissingRequiredFieldError, 2000, 3000),
        (InvalidFieldValueError, 2000, 3000),
        (RequestTooLargeError, 2000, 3000),
        (UnauthenticatedError, 3000, 4000),
        (InvalidTokenError, 3000, 4000),
        (TokenExpiredError, 3000, 4000),
        (UnauthorizedError, 3000, 4000),
        (PermissionDeniedError, 3000, 4000),
        (InsufficientScopeError, 3000, 4000),
        (ResourceNotFoundError, 4000, 5000),
        (MethodNotFoundError, 4000, 5000),
        (ServiceNotFoundError, 4000, 5000),
        (AlreadyExistsError, 4000, 5000),
        (ConflictError, 4000, 5000),
        (GoneError, 4000, 5000),
        (InternalError, 5000, 6000),
        (RpcNotImplementedError, 5000, 6000),
        (ServiceUnavailableError, 5000, 6000),
        (RpcTimeoutError, 5000, 6000),
        (CircuitBreakerOpenError, 5000, 6000),
        (RateLimitedError, 5000, 6000),
        (ResourceExhaustedError, 5000, 6000),
        (DependencyError, 6000, 7000),
        (UpstreamTimeoutError, 6000, 7000),
        (UpstreamUnavailableError, 6000, 7000),
    ],
)
def test_exception_codes_match_ranges(exc_class, range_start, range_end):
    """Validate that exception codes fall within the expected range."""
    exc = exc_class()
    assert range_start <= exc.code < range_end


def test_rpc_exception_creation():
    """Create a base RpcException and validate fields."""
    exc = RpcException(code=9000, message="custom", data={"key": "value"})
    assert exc.code == 9000
    assert exc.message == "custom"
    assert exc.data == {"key": "value"}
    assert exc.cause is None
    assert exc.args == ("custom",)


def test_rpc_exception_immutable():
    """Ensure RpcException instances are immutable."""
    exc = RpcException(code=9000, message="immutable")
    with pytest.raises(FrozenInstanceError):
        exc.message = "mutated"


def test_rpc_exception_to_error_dict():
    """Return a compatible error dict shape."""
    exc = RpcException(code=9000, message="oops", data={"info": 1})
    assert exc.to_error_dict() == {"code": 9000, "message": "oops", "data": {"info": 1}}


def test_rpc_exception_with_cause():
    """Preserve explicit exception causes."""
    cause = ValueError("root cause")
    exc = RpcException(code=9000, message="wrapped", cause=cause)
    assert exc.cause is cause
    assert exc.__cause__ is cause
    assert exc.__suppress_context__ is True


def test_rpc_exception_is_exception():
    """RpcException inherits from Exception."""
    exc = RpcException(code=9000, message="boom")
    assert isinstance(exc, Exception)


def test_error_code_enum_values():
    """Verify all ErrorCode enum values."""
    expected = {
        "PROTOCOL_ERROR": 1000,
        "UNSUPPORTED_VERSION": 1001,
        "INVALID_MESSAGE": 1002,
        "SERIALIZATION_ERROR": 1003,
        "COMPRESSION_ERROR": 1004,
        "BAD_REQUEST": 2000,
        "INVALID_PARAMS": 2001,
        "MISSING_REQUIRED_FIELD": 2002,
        "INVALID_FIELD_VALUE": 2003,
        "REQUEST_TOO_LARGE": 2004,
        "UNAUTHENTICATED": 3000,
        "INVALID_TOKEN": 3001,
        "TOKEN_EXPIRED": 3002,
        "UNAUTHORIZED": 3010,
        "PERMISSION_DENIED": 3011,
        "INSUFFICIENT_SCOPE": 3012,
        "RESOURCE_NOT_FOUND": 4000,
        "METHOD_NOT_FOUND": 4001,
        "SERVICE_NOT_FOUND": 4002,
        "ALREADY_EXISTS": 4010,
        "CONFLICT": 4011,
        "GONE": 4020,
        "INTERNAL_ERROR": 5000,
        "NOT_IMPLEMENTED": 5001,
        "SERVICE_UNAVAILABLE": 5002,
        "RPC_TIMEOUT": 5003,
        "CIRCUIT_BREAKER_OPEN": 5010,
        "RATE_LIMITED": 5020,
        "RESOURCE_EXHAUSTED": 5021,
        "DEPENDENCY_ERROR": 6000,
        "UPSTREAM_TIMEOUT": 6001,
        "UPSTREAM_UNAVAILABLE": 6002,
    }
    assert {member.name: member.value for member in ErrorCode} == expected


def test_error_code_names_mapping():
    """Ensure ERROR_CODE_NAMES maps values to enum names."""
    expected = {member.value: member.name for member in ErrorCode}
    assert ERROR_CODE_NAMES == expected


def test_error_code_is_int():
    """Support int-like behavior on ErrorCode."""
    assert isinstance(ErrorCode.PROTOCOL_ERROR, int)
    assert int(ErrorCode.PROTOCOL_ERROR) == 1000
    assert ErrorCode.PROTOCOL_ERROR + 1 == 1001


@pytest.mark.parametrize(
    "code, expected_status",
    [
        (1000, 400),
        (1999, 400),
        (2000, 400),
        (2999, 400),
        (3000, 401),
        (3002, 401),
        (3010, 403),
        (3012, 403),
        (4000, 404),
        (4002, 404),
        (4010, 409),
        (4011, 409),
        (4020, 404),
        (5000, 500),
        (5001, 501),
        (5002, 503),
        (5003, 504),
        (5020, 429),
        (5021, 429),
        (5500, 500),
        (6000, 502),
        (6999, 502),
        (7000, 500),
    ],
)
def test_error_code_to_http_status(code, expected_status):
    """Map RPC error codes to HTTP status codes for all ranges."""
    assert error_code_to_http_status(code) == expected_status


@pytest.mark.parametrize(
    "code, expected_status",
    [
        (2000, "INVALID_ARGUMENT"),
        (2999, "INVALID_ARGUMENT"),
        (3000, "UNAUTHENTICATED"),
        (3002, "UNAUTHENTICATED"),
        (3010, "PERMISSION_DENIED"),
        (3012, "PERMISSION_DENIED"),
        (4000, "NOT_FOUND"),
        (4002, "NOT_FOUND"),
        (4010, "ALREADY_EXISTS"),
        (4011, "ALREADY_EXISTS"),
        (4020, "NOT_FOUND"),
        (5000, "INTERNAL"),
        (5001, "UNIMPLEMENTED"),
        (5002, "UNAVAILABLE"),
        (5003, "DEADLINE_EXCEEDED"),
        (5020, "RESOURCE_EXHAUSTED"),
        (5021, "RESOURCE_EXHAUSTED"),
        (9999, "UNKNOWN"),
    ],
)
def test_error_code_to_grpc_status(code, expected_status):
    """Map RPC error codes to gRPC status names for all ranges."""
    assert error_code_to_grpc_status(code) == expected_status


def test_http_status_fallback():
    """Fallback to 500 for unknown HTTP error codes."""
    assert error_code_to_http_status(9999) == 500


@pytest.mark.parametrize(
    "code, expected_class",
    [
        (ErrorCode.PROTOCOL_ERROR, ProtocolError),
        (ErrorCode.UNSUPPORTED_VERSION, UnsupportedVersionError),
        (ErrorCode.INVALID_MESSAGE, InvalidMessageError),
        (ErrorCode.SERIALIZATION_ERROR, SerializationError),
        (ErrorCode.COMPRESSION_ERROR, CompressionError),
        (ErrorCode.BAD_REQUEST, BadRequestError),
        (ErrorCode.INVALID_PARAMS, InvalidParamsError),
        (ErrorCode.MISSING_REQUIRED_FIELD, MissingRequiredFieldError),
        (ErrorCode.INVALID_FIELD_VALUE, InvalidFieldValueError),
        (ErrorCode.REQUEST_TOO_LARGE, RequestTooLargeError),
        (ErrorCode.UNAUTHENTICATED, UnauthenticatedError),
        (ErrorCode.INVALID_TOKEN, InvalidTokenError),
        (ErrorCode.TOKEN_EXPIRED, TokenExpiredError),
        (ErrorCode.UNAUTHORIZED, UnauthorizedError),
        (ErrorCode.PERMISSION_DENIED, PermissionDeniedError),
        (ErrorCode.INSUFFICIENT_SCOPE, InsufficientScopeError),
        (ErrorCode.RESOURCE_NOT_FOUND, ResourceNotFoundError),
        (ErrorCode.METHOD_NOT_FOUND, MethodNotFoundError),
        (ErrorCode.SERVICE_NOT_FOUND, ServiceNotFoundError),
        (ErrorCode.ALREADY_EXISTS, AlreadyExistsError),
        (ErrorCode.CONFLICT, ConflictError),
        (ErrorCode.GONE, GoneError),
        (ErrorCode.INTERNAL_ERROR, InternalError),
        (ErrorCode.NOT_IMPLEMENTED, RpcNotImplementedError),
        (ErrorCode.SERVICE_UNAVAILABLE, ServiceUnavailableError),
        (ErrorCode.RPC_TIMEOUT, RpcTimeoutError),
        (ErrorCode.CIRCUIT_BREAKER_OPEN, CircuitBreakerOpenError),
        (ErrorCode.RATE_LIMITED, RateLimitedError),
        (ErrorCode.RESOURCE_EXHAUSTED, ResourceExhaustedError),
        (ErrorCode.DEPENDENCY_ERROR, DependencyError),
        (ErrorCode.UPSTREAM_TIMEOUT, UpstreamTimeoutError),
        (ErrorCode.UPSTREAM_UNAVAILABLE, UpstreamUnavailableError),
    ],
)
def test_exception_from_code_known_code(code, expected_class):
    """Return specific exception classes for known error codes."""
    exc = exception_from_code(int(code))
    assert isinstance(exc, expected_class)
    assert exc.code == int(code)


def test_exception_from_code_unknown_code():
    """Unknown codes should return a generic RpcException."""
    exc = exception_from_code(9999)
    assert isinstance(exc, RpcException)
    assert exc.code == 9999
    assert exc.message == "RPC error"


def test_exception_from_code_with_custom_message():
    """Provide custom messages for known codes."""
    exc = exception_from_code(ErrorCode.BAD_REQUEST, message="custom bad request")
    assert isinstance(exc, BadRequestError)
    assert exc.message == "custom bad request"


def test_exception_from_code_with_data():
    """Provide custom data to exception factory."""
    payload = {"info": "details"}
    exc = exception_from_code(ErrorCode.INTERNAL_ERROR, data=payload)
    assert isinstance(exc, InternalError)
    assert exc.data == payload
