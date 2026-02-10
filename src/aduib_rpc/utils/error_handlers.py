import functools
import logging

from collections.abc import Awaitable, Callable, Coroutine
from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING, Any

from aduib_rpc.protocol.v2.errors import ERROR_CODE_NAMES, exception_to_rpc_error
from aduib_rpc.protocol.v2.types import RpcError


if TYPE_CHECKING:
    from starlette.responses import JSONResponse, Response
else:
    try:
        from starlette.responses import JSONResponse, Response
    except ImportError:
        JSONResponse = Any
        Response = Any

logger = logging.getLogger(__name__)


class ErrorSeverity(Enum):
    INFO = "info"  # Normal flow (e.g., validation failure)
    WARNING = "warning"  # Recoverable error (e.g., retry succeeded)
    ERROR = "error"  # Business error
    CRITICAL = "critical"  # System error


@dataclass
class ErrorContext:
    exception: BaseException
    request_id: str
    method: str
    severity: ErrorSeverity
    should_notify: bool = True
    should_log: bool = True


def rest_error_handler(
    func: Callable[..., Awaitable[Response]],
) -> Callable[..., Awaitable[Response]]:
    """Decorator to catch ServerError and map it to an appropriate JSONResponse."""

    @functools.wraps(func)
    async def wrapper(*args: Any, **kwargs: Any) -> Response:
        try:
            return await func(*args, **kwargs)
        except Exception:
            logger.exception('Unknown error occurred')
            return JSONResponse(
                content={'message': 'unknown exception'}, status_code=500
            )

    return wrapper


def rest_stream_error_handler(
    func: Callable[..., Coroutine[Any, Any, Any]],
) -> Callable[..., Coroutine[Any, Any, Any]]:
    """Decorator to catch ServerError for a streaming method,log it and then rethrow it to be handled by framework."""

    @functools.wraps(func)
    async def wrapper(*args: Any, **kwargs: Any) -> Any:
        try:
            return await func(*args, **kwargs)
        except Exception as e:
            # Since the stream has started, we can't return a JSONResponse.
            # Instead, we runt the error handling logic (provides logging)
            # and reraise the error and let server framework manage
            raise e

    return wrapper


def exception_to_error(exc: BaseException, *, code: int | None = None) -> RpcError:
    """Convert an arbitrary exception to a v2 RpcError."""

    if code is not None:
        name = ERROR_CODE_NAMES.get(code, "UNKNOWN")
        return RpcError(
            code=int(code),
            name=name,
            message=str(exc) or exc.__class__.__name__,
        )

    return exception_to_rpc_error(exc)


async def handle_error_unified(
    ctx: ErrorContext,
    interceptors: list | None = None,
    server_context: Any = None,
) -> RpcError:
    """Unified error handling pipeline."""

    # NOTE: keep this compatible with the existing exception_to_error helper.
    rpc_error = exception_to_error(ctx.exception)

    # TODO: apply interceptors/server_context if/when a shared interceptor contract exists.
    _ = interceptors, server_context

    if ctx.should_log:
        log_fn = {
            ErrorSeverity.INFO: logger.info,
            ErrorSeverity.WARNING: logger.warning,
            ErrorSeverity.ERROR: logger.error,
            ErrorSeverity.CRITICAL: logger.critical,
        }[ctx.severity]
        log_fn(
            "Error in %s: %s",
            ctx.method,
            rpc_error.message,
            extra={
                "request_id": ctx.request_id,
                "error_code": rpc_error.code,
            },
            exc_info=ctx.severity in {ErrorSeverity.ERROR, ErrorSeverity.CRITICAL},
        )

    return rpc_error
