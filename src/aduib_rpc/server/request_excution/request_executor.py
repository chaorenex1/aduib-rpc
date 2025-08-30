import logging
from abc import ABC, abstractmethod
from typing import Any, Optional

from starlette.requests import Request

from aduib_rpc.server.request_excution.context import RequestContext

logger=logging.getLogger(__name__)

class RequestExecutor(ABC):
    """Abstract base class for executing requests."""

    @abstractmethod
    def execute(self, context: RequestContext) -> Any:
        """Executes the request based on the provided context.
        Args:
            context: The `RequestContext` containing request details.
        Returns:
            The result of the request execution.
        """

REQUEST_EXECUTIONS:dict[str, RequestExecutor] = {}

def request_execution(method:str):
    """Decorator to register a request executor class."""
    def decorator(cls:Any):
        if method:
            if method in REQUEST_EXECUTIONS:
                logger.warning(f"Request executor for method '{method}' is already registered. Overwriting.")
            else:
                logger.info(f"Registering request executor for method '{method}'.")
                REQUEST_EXECUTIONS[method] = cls()
        else:
            logger.warning("Method is empty. Cannot register request executor.")
        return cls
    return decorator


def get_request_executor(method:str)-> RequestExecutor | None:
    """Retrieves the request executor for the given model ID or type.
    Args:
        method: request method.
    Returns:
        The registered `RequestExecutor` instance or None if not found.
    """
    if method:
        executor = REQUEST_EXECUTIONS.get(method)
        if executor:
            return executor
    return None

def add_request_executor(method:str, executor:RequestExecutor):
    """Adds a request executor for the given method.
    Args:
        method: request method.
    """
    if method in REQUEST_EXECUTIONS:
        logger.warning(f"Request executor for method '{method}' is already registered. Overwriting.")
    else:
        logger.info(f"Registering request executor for method '{method}'.")
        REQUEST_EXECUTIONS[method] = executor