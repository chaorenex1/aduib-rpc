from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class RpcException(Exception):
    """Base class for Aduib RPC exceptions with a canonical error shape."""

    code: int
    message: str
    data: Any | None = None
    cause: Exception | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "args", (self.message,))
        if self.cause is not None:
            object.__setattr__(self, "__cause__", self.cause)
            object.__setattr__(self, "__suppress_context__", True)

    def to_error_dict(self) -> dict[str, Any]:
        """Return a dict compatible with AduibRpcError."""
        return {"code": self.code, "message": self.message, "data": self.data}


@dataclass(frozen=True)
class ProtocolError(RpcException):
    """Raised when the RPC protocol contract is violated."""

    code: int = 1000
    message: str = "Protocol error"


@dataclass(frozen=True)
class UnsupportedVersionError(RpcException):
    """Raised when the client uses an unsupported protocol version."""

    code: int = 1001
    message: str = "Unsupported protocol version"


@dataclass(frozen=True)
class InvalidMessageError(RpcException):
    """Raised when the inbound RPC message is malformed."""

    code: int = 1002
    message: str = "Invalid message"


@dataclass(frozen=True)
class SerializationError(RpcException):
    """Raised when serialization or deserialization fails."""

    code: int = 1003
    message: str = "Serialization error"


@dataclass(frozen=True)
class CompressionError(RpcException):
    """Raised when compression or decompression fails."""

    code: int = 1004
    message: str = "Compression error"


@dataclass(frozen=True)
class BadRequestError(RpcException):
    """Raised when the request payload is invalid or incomplete."""

    code: int = 2000
    message: str = "Bad request"


@dataclass(frozen=True)
class InvalidParamsError(RpcException):
    """Raised when the provided parameters are invalid."""

    code: int = 2001
    message: str = "Invalid params"


@dataclass(frozen=True)
class MissingRequiredFieldError(RpcException):
    """Raised when a required request field is missing."""

    code: int = 2002
    message: str = "Missing required field"


@dataclass(frozen=True)
class InvalidFieldValueError(RpcException):
    """Raised when a field value fails validation."""

    code: int = 2003
    message: str = "Invalid field value"


@dataclass(frozen=True)
class RequestTooLargeError(RpcException):
    """Raised when the request exceeds the allowed payload size."""

    code: int = 2004
    message: str = "Request too large"


@dataclass(frozen=True)
class UnauthenticatedError(RpcException):
    """Raised when authentication credentials are missing."""

    code: int = 3000
    message: str = "Unauthenticated"


@dataclass(frozen=True)
class InvalidTokenError(RpcException):
    """Raised when the authentication token is invalid."""

    code: int = 3001
    message: str = "Invalid token"


@dataclass(frozen=True)
class TokenExpiredError(RpcException):
    """Raised when the authentication token has expired."""

    code: int = 3002
    message: str = "Token expired"


@dataclass(frozen=True)
class UnauthorizedError(RpcException):
    """Raised when the caller is not authorized for the operation."""

    code: int = 3010
    message: str = "Unauthorized"


@dataclass(frozen=True)
class PermissionDeniedError(RpcException):
    """Raised when the caller lacks permission to access the resource."""

    code: int = 3011
    message: str = "Permission denied"


@dataclass(frozen=True)
class InsufficientScopeError(RpcException):
    """Raised when the caller token lacks required scope."""

    code: int = 3012
    message: str = "Insufficient scope"


@dataclass(frozen=True)
class ResourceNotFoundError(RpcException):
    """Raised when the requested resource cannot be found."""

    code: int = 4000
    message: str = "Resource not found"


@dataclass(frozen=True)
class MethodNotFoundError(RpcException):
    """Raised when the RPC method name is not registered."""

    code: int = 4001
    message: str = "Method not found"


@dataclass(frozen=True)
class ServiceNotFoundError(RpcException):
    """Raised when the target service is not available."""

    code: int = 4002
    message: str = "Service not found"


@dataclass(frozen=True)
class AlreadyExistsError(RpcException):
    """Raised when attempting to create a resource that already exists."""

    code: int = 4010
    message: str = "Already exists"


@dataclass(frozen=True)
class ConflictError(RpcException):
    """Raised when the request conflicts with current state."""

    code: int = 4011
    message: str = "Conflict"


@dataclass(frozen=True)
class GoneError(RpcException):
    """Raised when a resource is no longer available."""

    code: int = 4020
    message: str = "Gone"


@dataclass(frozen=True)
class InternalError(RpcException):
    """Raised for unexpected server-side failures."""

    code: int = 5000
    message: str = "Internal error"


@dataclass(frozen=True)
class RpcNotImplementedError(RpcException):
    """Raised when an RPC method is not implemented."""

    code: int = 5001
    message: str = "Not implemented"


@dataclass(frozen=True)
class ServiceUnavailableError(RpcException):
    """Raised when the service is unavailable or overloaded."""

    code: int = 5002
    message: str = "Service unavailable"


@dataclass(frozen=True)
class RpcTimeoutError(RpcException):
    """Raised when an RPC call exceeds its timeout."""

    code: int = 5003
    message: str = "RPC timeout"


@dataclass(frozen=True)
class CircuitBreakerOpenError(RpcException):
    """Raised when a circuit breaker prevents the call."""

    code: int = 5010
    message: str = "Circuit breaker open"


@dataclass(frozen=True)
class RateLimitedError(RpcException):
    """Raised when rate limiting is enforced."""

    code: int = 5020
    message: str = "Rate limited"


@dataclass(frozen=True)
class ResourceExhaustedError(RpcException):
    """Raised when a server resource is exhausted."""

    code: int = 5021
    message: str = "Resource exhausted"


@dataclass(frozen=True)
class DependencyError(RpcException):
    """Raised when an external dependency fails."""

    code: int = 6000
    message: str = "Dependency error"


@dataclass(frozen=True)
class UpstreamTimeoutError(RpcException):
    """Raised when an upstream dependency times out."""

    code: int = 6001
    message: str = "Upstream timeout"


@dataclass(frozen=True)
class UpstreamUnavailableError(RpcException):
    """Raised when an upstream dependency is unavailable."""

    code: int = 6002
    message: str = "Upstream unavailable"
