import logging
from abc import ABC, abstractmethod
from typing import Any, Optional

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




MODEL_EXECUTIONS:dict[str, ModelExecutor|list[ModelExecutor]] = {}


def model_execution(model_id:str,model_type:Optional[str]=None):
    """Decorator to register a model executor class."""
    def decorator(cls:Any):
        if model_id and model_type:
            id=model_id+"_"+model_type
            if id not in MODEL_EXECUTIONS:
                MODEL_EXECUTIONS[id] = cls()
        if model_type and not model_id:
            if MODEL_EXECUTIONS.get(model_type) is None:
                MODEL_EXECUTIONS[model_type] = cls()
        if model_id:
            if model_id in MODEL_EXECUTIONS:
                logger.warning(f"Model executor for model_id '{model_id}' is already registered. Overwriting.")
            else:
                logger.info(f"Registering model executor for model_id '{model_id}'.")
                MODEL_EXECUTIONS[model_id] = cls()
        else:
            logger.warning("Model executor must have at least a model_id or model_type.")
        return cls
    return decorator


def get_model_executor(model_id:str,model_type:Optional[str]=None)->ModelExecutor|None:
    """Retrieves the model executor for the given model ID or type.
    Args:
        model_id: The model ID.
        model_type: The model type.
    Returns:
        The registered `ModelExecutor` instance or None if not found.
    """
    if model_id and model_type:
        id=model_id+"_"+model_type
        executor = MODEL_EXECUTIONS.get(id)
        if executor:
            return executor
    if model_id:
        executor = MODEL_EXECUTIONS.get(model_id)
        if executor:
            return executor
    if model_type:
        executor = MODEL_EXECUTIONS.get(model_type)
        if executor:
            return executor
    return None