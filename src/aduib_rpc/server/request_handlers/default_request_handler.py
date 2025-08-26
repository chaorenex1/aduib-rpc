import logging
import uuid
from collections.abc import AsyncGenerator

from aduib_rpc.server.context import ServerContext
from aduib_rpc.server.model_excution.context import RequestContext
from aduib_rpc.server.model_excution.model_executor import ModelExecutor, MODEL_EXECUTIONS
from aduib_rpc.server.request_handlers import RequestHandler
from aduib_rpc.types import AduibRpcResponse, AduibRpcRequest

logger = logging.getLogger(__name__)


class DefaultRequestHandler(RequestHandler):
    """Default implementation of RequestHandler with no-op methods."""

    def __init__(self,
                 model_executor: ModelExecutor):
        """Initializes the DefaultRequestHandler.
        Args:
            model_executor: The ModelExecutor instance to handle model operations.
        """
        self.model_executor = model_executor

    async def on_message(
            self,
            message: AduibRpcRequest,
            context: ServerContext | None = None
    )-> AduibRpcResponse:
        """Handles the 'message' method.
        Args:
            message: The incoming `CompletionRequest` object.
            context: Context provided by the server.

        Returns:
            The `AduibRpcResponse` object containing the response.
        """
        try:
            context:RequestContext=self._setup_request_context(message,context)
            self.model_executor=self._validate_model_executor(self.model_executor,context)
            response = await self.model_executor.execute(context)
            return AduibRpcResponse(id=context.request_id, result=response)
        except Exception as e:
            logger.error(f"Error processing message: {e}")
            raise

    async def on_stream_message(
            self,
            message: AduibRpcRequest,
            context: ServerContext | None = None
    )-> AsyncGenerator[AduibRpcResponse]:
        """Handles the 'stream_message' method.

        Args:
            message: The incoming `CompletionRequest` object.
            context: Context provided by the server.

        Yields:
            The `AduibRpcResponse` objects containing the streaming responses.
        """
        try:
            context:RequestContext=self._setup_request_context(message,context)
            self.model_executor=self._validate_model_executor(self.model_executor,context)
            async for response in self.model_executor.execute(context):
                yield AduibRpcResponse(id=context.request_id, result=response)
        except Exception as e:
            logger.error(f"Error processing stream message: {e}")
            raise

    def _setup_request_context(self,
                               message: AduibRpcRequest,
            context: ServerContext | None = None) -> RequestContext:
        """Sets up and returns a RequestContext based on the provided ServerContext."""
        context_id:str=str(uuid.uuid4())
        request_id:str=message.id or str(uuid.uuid4())
        request_context = RequestContext(
            context_id=context_id,
            request_id=request_id,
            request=message,
            server_context=context,
        )
        return request_context

    def _validate_model_executor(self, model_executor: ModelExecutor,context:RequestContext) -> ModelExecutor:
        """Validates and returns the ModelExecutor instance."""
        if not model_executor:
            return MODEL_EXECUTIONS.get(context.request.model)
        # MODEL_EXECUTIONS
        if context.request.model not in MODEL_EXECUTIONS:
            raise ValueError(f"Model '{context.request.model}' is not supported.")

        validated:bool=False
        for name,model_executor in MODEL_EXECUTIONS.items():
            if isinstance(model_executor, type(model_executor)) and name == context.request.model:
                validated=True
                break
        if not validated:
            return MODEL_EXECUTIONS.get(context.request.model)
        else:
            return model_executor


