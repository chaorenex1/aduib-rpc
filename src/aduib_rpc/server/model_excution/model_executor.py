import logging
from abc import ABC, abstractmethod
from typing import Any

from aduib_rpc.server.model_excution.context import RequestContext

logger=logging.getLogger(__name__)

class ModelExecutor(ABC):
    """Model Executor interface."""

    @abstractmethod
    async def execute(self, context: RequestContext) -> Any:
        """Executes the model with the given context.
        Args:
            context: The request context containing the message, task ID, etc.
        Returns:
            The `AduibRpcResponse` object containing the response.
        """




MODEL_EXECUTIONS:dict[str, ModelExecutor] = {}


def model_execution(model_id:str):
    """Decorator to register a model executor class."""
    def decorator(cls:Any):
        if model_id in MODEL_EXECUTIONS:
            logger.warning(f"Model executor for model_id '{model_id}' is already registered. Overwriting.")
        else:
            logger.info(f"Registering model executor for model_id '{model_id}'.")
            MODEL_EXECUTIONS[model_id] = cls()
        return cls
    return decorator