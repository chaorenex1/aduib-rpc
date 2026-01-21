"""Error codes and mapping helpers for Aduib RPC protocol v2."""

from __future__ import annotations

from enum import IntEnum
from typing import Any

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


class ErrorCode(IntEnum):
    """Standard Aduib RPC error codes."""

    # 协议错误
    PROTOCOL_ERROR = 1000
    UNSUPPORTED_VERSION = 1001
    INVALID_MESSAGE = 1002
    SERIALIZATION_ERROR = 1003
    COMPRESSION_ERROR = 1004

    # 客户端错误
    BAD_REQUEST = 2000
    INVALID_PARAMS = 2001
    MISSING_REQUIRED_FIELD = 2002
    INVALID_FIELD_VALUE = 2003
    REQUEST_TOO_LARGE = 2004

    # 认证错误
    UNAUTHENTICATED = 3000
    INVALID_TOKEN = 3001
    TOKEN_EXPIRED = 3002
    UNAUTHORIZED = 3010
    PERMISSION_DENIED = 3011
    INSUFFICIENT_SCOPE = 3012

    # 资源错误
    RESOURCE_NOT_FOUND = 4000
    METHOD_NOT_FOUND = 4001
    SERVICE_NOT_FOUND = 4002
    ALREADY_EXISTS = 4010
    CONFLICT = 4011
    GONE = 4020

    # 服务端错误
    INTERNAL_ERROR = 5000
    NOT_IMPLEMENTED = 5001
    SERVICE_UNAVAILABLE = 5002
    RPC_TIMEOUT = 5003
    CIRCUIT_BREAKER_OPEN = 5010
    RATE_LIMITED = 5020
    RESOURCE_EXHAUSTED = 5021

    # 依赖错误
    DEPENDENCY_ERROR = 6000
    UPSTREAM_TIMEOUT = 6001
    UPSTREAM_UNAVAILABLE = 6002


ERROR_CODE_NAMES: dict[int, str] = {member.value: member.name for member in ErrorCode}


_EXCEPTION_BY_CODE: dict[int, type[RpcException]] = {
    ErrorCode.PROTOCOL_ERROR: ProtocolError,
    ErrorCode.UNSUPPORTED_VERSION: UnsupportedVersionError,
    ErrorCode.INVALID_MESSAGE: InvalidMessageError,
    ErrorCode.SERIALIZATION_ERROR: SerializationError,
    ErrorCode.COMPRESSION_ERROR: CompressionError,
    ErrorCode.BAD_REQUEST: BadRequestError,
    ErrorCode.INVALID_PARAMS: InvalidParamsError,
    ErrorCode.MISSING_REQUIRED_FIELD: MissingRequiredFieldError,
    ErrorCode.INVALID_FIELD_VALUE: InvalidFieldValueError,
    ErrorCode.REQUEST_TOO_LARGE: RequestTooLargeError,
    ErrorCode.UNAUTHENTICATED: UnauthenticatedError,
    ErrorCode.INVALID_TOKEN: InvalidTokenError,
    ErrorCode.TOKEN_EXPIRED: TokenExpiredError,
    ErrorCode.UNAUTHORIZED: UnauthorizedError,
    ErrorCode.PERMISSION_DENIED: PermissionDeniedError,
    ErrorCode.INSUFFICIENT_SCOPE: InsufficientScopeError,
    ErrorCode.RESOURCE_NOT_FOUND: ResourceNotFoundError,
    ErrorCode.METHOD_NOT_FOUND: MethodNotFoundError,
    ErrorCode.SERVICE_NOT_FOUND: ServiceNotFoundError,
    ErrorCode.ALREADY_EXISTS: AlreadyExistsError,
    ErrorCode.CONFLICT: ConflictError,
    ErrorCode.GONE: GoneError,
    ErrorCode.INTERNAL_ERROR: InternalError,
    ErrorCode.NOT_IMPLEMENTED: RpcNotImplementedError,
    ErrorCode.SERVICE_UNAVAILABLE: ServiceUnavailableError,
    ErrorCode.RPC_TIMEOUT: RpcTimeoutError,
    ErrorCode.CIRCUIT_BREAKER_OPEN: CircuitBreakerOpenError,
    ErrorCode.RATE_LIMITED: RateLimitedError,
    ErrorCode.RESOURCE_EXHAUSTED: ResourceExhaustedError,
    ErrorCode.DEPENDENCY_ERROR: DependencyError,
    ErrorCode.UPSTREAM_TIMEOUT: UpstreamTimeoutError,
    ErrorCode.UPSTREAM_UNAVAILABLE: UpstreamUnavailableError,
}


def error_code_to_http_status(code: int) -> int:
    """Return the HTTP status code corresponding to an RPC error code."""

    if 1000 <= code < 2000:
        return 400
    if 2000 <= code < 3000:
        return 400
    if 3000 <= code <= 3002:
        return 401
    if 3010 <= code <= 3012:
        return 403
    if 4000 <= code <= 4002:
        return 404
    if 4010 <= code <= 4011:
        return 409
    if code == 4020:
        return 404
    if code == 5000:
        return 500
    if code == 5001:
        return 501
    if code == 5002:
        return 503
    if code == 5003:
        return 504
    if 5020 <= code <= 5021:
        return 429
    if 5000 <= code < 6000:
        return 500
    if 6000 <= code < 7000:
        return 502
    return 500


def error_code_to_grpc_status(code: int) -> str:
    """Return the gRPC status code name for an RPC error code."""

    if 2000 <= code < 3000:
        return "INVALID_ARGUMENT"
    if 3000 <= code <= 3002:
        return "UNAUTHENTICATED"
    if 3010 <= code <= 3012:
        return "PERMISSION_DENIED"
    if 4000 <= code <= 4002:
        return "NOT_FOUND"
    if 4010 <= code <= 4011:
        return "ALREADY_EXISTS"
    if code == 4020:
        return "NOT_FOUND"
    if code == 5000:
        return "INTERNAL"
    if code == 5001:
        return "UNIMPLEMENTED"
    if code == 5002:
        return "UNAVAILABLE"
    if code == 5003:
        return "DEADLINE_EXCEEDED"
    if 5020 <= code <= 5021:
        return "RESOURCE_EXHAUSTED"
    return "UNKNOWN"


def exception_from_code(
    code: int, message: str | None = None, data: Any = None
) -> RpcException:
    """Create a concrete RPC exception instance from a standardized code."""

    exc_cls = _EXCEPTION_BY_CODE.get(code)
    if exc_cls is None:
        fallback_message = message or "RPC error"
        return RpcException(code=code, message=fallback_message, data=data)
    if message is None:
        return exc_cls(data=data)
    return exc_cls(message=message, data=data)
