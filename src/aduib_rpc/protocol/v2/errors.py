"""Error codes and mapping helpers for Aduib RPC protocol v2."""

from __future__ import annotations

import os
import sys
import traceback
from enum import IntEnum
from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    from aduib_rpc.protocol.v2.types import DebugInfo, RpcError

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
    """Return the HTTP status code corresponding to an RPC error code.

    Mapping per spec v2 section 5.3:
    - 1xxx (protocol errors) -> 400
    - 2xxx (client errors) -> 400
    - 3000-3002 (unauthenticated) -> 401
    - 3010-3012 (unauthorized) -> 403
    - 4000-4002 (not found) -> 404
    - 4010-4011 (conflict) -> 409
    - 4020 (gone) -> 410
    - 5000 (internal error) -> 500
    - 5001 (not implemented) -> 501
    - 5002 (service unavailable) -> 503
    - 5003 (timeout) -> 504
    - 5010 (circuit breaker) -> 503
    - 5020-5021 (rate limited/exhausted) -> 429
    - 6000 (dependency error) -> 502
    - 6001 (upstream timeout) -> 504
    - 6002 (upstream unavailable) -> 502
    """

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
        return 410  # HTTP 410 Gone
    if code == 5000:
        return 500
    if code == 5001:
        return 501
    if code == 5002:
        return 503
    if code == 5003:
        return 504
    if code == 5010:
        return 503  # Circuit breaker -> service unavailable
    if 5020 <= code <= 5021:
        return 429
    if 5000 <= code < 6000:
        return 500  # Other 5xxx errors
    if code == 6000:
        return 502  # Bad gateway
    if code == 6001:
        return 504  # Upstream timeout -> gateway timeout
    if code == 6002:
        return 502  # Upstream unavailable -> bad gateway
    if 6000 <= code < 7000:
        return 502  # Other 6xxx errors
    return 500  # Unknown error -> internal server error


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


def exception_from_code(code: int, message: str | None = None, data: Any = None) -> RpcException:
    """Create a concrete RPC exception instance from a standardized code."""

    exc_cls = _EXCEPTION_BY_CODE.get(code)
    if exc_cls is None:
        fallback_message = message or "RPC error"
        return RpcException(code=code, message=fallback_message, data=data)
    if message is None:
        return exc_cls(data=data)
    return exc_cls(message=message, data=data)


# =============================================================================
# Standard Python Exception Mapping
# =============================================================================

_STANDARD_EXCEPTION_MAPPING: dict[type[Exception], int] = {
    # Client errors (2xxx)
    ValueError: ErrorCode.INVALID_PARAMS,
    KeyError: ErrorCode.INVALID_PARAMS,
    TypeError: ErrorCode.INVALID_PARAMS,
    AttributeError: ErrorCode.INVALID_PARAMS,
    IndexError: ErrorCode.INVALID_PARAMS,
    AssertionError: ErrorCode.INVALID_PARAMS,
    StopIteration: ErrorCode.INVALID_PARAMS,
    # Authentication/Authorization (3xxx)
    PermissionError: ErrorCode.PERMISSION_DENIED,
    # Resource errors (4xxx)
    FileNotFoundError: ErrorCode.RESOURCE_NOT_FOUND,
    LookupError: ErrorCode.RESOURCE_NOT_FOUND,
    NotImplementedError: ErrorCode.NOT_IMPLEMENTED,
    # Server errors (5xxx)
    RuntimeError: ErrorCode.INTERNAL_ERROR,
    Exception: ErrorCode.INTERNAL_ERROR,
}


def map_exception_to_error_code(exc: Exception) -> int:
    """Map a standard Python exception to an RPC error code.

    Args:
        exc: The exception to map.

    Returns:
        The corresponding ErrorCode value.

    Examples:
        >>> map_exception_to_error_code(ValueError("bad input"))
        2001
        >>> map_exception_to_error_code(FileNotFoundError("missing"))
        4000
    """
    # If it's already an RpcException, use its code
    if isinstance(exc, RpcException):
        return exc.code

    # Find the most specific matching type in the mapping
    for exc_type, code in _STANDARD_EXCEPTION_MAPPING.items():
        if isinstance(exc, exc_type):
            return code

    return ErrorCode.INTERNAL_ERROR


def exception_to_rpc_error(
    exc: Exception,
    include_debug: bool | None = None,
) -> "RpcError":
    """Convert any exception to an RpcError with optional debug info.

    Args:
        exc: The exception to convert.
        include_debug: Whether to include debug information. If None, uses
            is_debug_enabled() to check environment.

    Returns:
        An RpcError instance populated from the exception.
    """
    # Lazy import to avoid circular dependency
    from aduib_rpc.protocol.v2.types import DebugInfo, RpcError

    code = map_exception_to_error_code(exc)
    name = ERROR_CODE_NAMES.get(code, "UNKNOWN")
    message = str(exc) if str(exc) else f"{type(exc).__name__}"

    debug_info = None
    if include_debug or (include_debug is None and is_debug_enabled()):
        debug_info = DebugInfo(
            stack_trace="".join(traceback.format_exception(type(exc), exc, exc.__traceback__)),
            internal_message=f"{type(exc).__module__}.{type(exc).__name__}",
            timestamp_ms=0,  # Will be set by caller
        )

    return RpcError(code=code, name=name, message=message, debug=debug_info)


# =============================================================================
# Debug Gating
# =============================================================================

_DEBUG_ENABLED: bool | None = None


def is_debug_enabled() -> bool:
    """Check if debug mode is enabled for RPC responses.

    Debug mode is enabled when:
    - ADUIB_RPC_DEBUG environment variable is set to "true"/"1"
    - ADUIB_ENV is set to "dev"/"development"
    - Python is running in debug mode (pydev debugger attached)

    Returns:
        True if debug mode is enabled, False otherwise.
    """
    global _DEBUG_ENABLED

    if _DEBUG_ENABLED is not None:
        return _DEBUG_ENABLED

    # Check environment variables
    debug_env = os.environ.get("ADUIB_RPC_DEBUG", "").lower()
    if debug_env in {"1", "true", "yes", "on"}:
        _DEBUG_ENABLED = True
        return True

    # Check environment type
    env = os.environ.get("ADUIB_ENV", "").lower()
    if env in {"dev", "development", "test"}:
        _DEBUG_ENABLED = True
        return True

    # Check if debugger is attached
    _DEBUG_ENABLED = sys.gettrace() is not None
    return _DEBUG_ENABLED


def set_debug_enabled(enabled: bool) -> None:
    """Override debug mode for testing or runtime control.

    Args:
        enabled: Whether to enable debug mode.
    """
    global _DEBUG_ENABLED
    _DEBUG_ENABLED = enabled


def reset_debug_cache() -> None:
    """Reset the cached debug mode setting.

    Useful for testing or when environment variables change.
    """
    global _DEBUG_ENABLED
    _DEBUG_ENABLED = None
