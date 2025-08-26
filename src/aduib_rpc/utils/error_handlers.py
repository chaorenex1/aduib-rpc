import functools
import logging

from collections.abc import Awaitable, Callable, Coroutine
from typing import TYPE_CHECKING, Any


if TYPE_CHECKING:
    from starlette.responses import JSONResponse, Response
else:
    try:
        from starlette.responses import JSONResponse, Response
    except ImportError:
        JSONResponse = Any
        Response = Any

logger = logging.getLogger(__name__)


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
