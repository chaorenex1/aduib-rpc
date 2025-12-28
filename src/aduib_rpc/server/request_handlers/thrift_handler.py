import json
import logging
from abc import ABC, abstractmethod

from aduib_rpc.server.context import ServerContext
from aduib_rpc.server.request_handlers import RequestHandler
from aduib_rpc.thrift.ttypes import RpcTask, RpcTaskResponse, RpcError
from aduib_rpc.utils import thrift_utils
from aduib_rpc.utils.async_utils import AsyncUtils
from aduib_rpc.utils.error_handlers import exception_to_error


logger=logging.getLogger(__name__)


class ServerContentBuilder(ABC):
    """Abstract base class for building server content."""

    @abstractmethod
    def build_context(self, task:RpcTask) -> ServerContext:
        """Builds and returns server content based on the provided data."""

class DefaultServerContentBuilder(ServerContentBuilder):
    """Default implementation of ServerContextBuilder."""

    def build_context(self, task:RpcTask) -> ServerContext:
        """Builds and returns a default ServerContext."""
        state= {'headers': json.loads(task.meta) if task.meta else {}}
        return ServerContext(state=state,metadata=
                                json.loads(task.meta) or {})

class ThriftHandler:
    """
    Handler for Thrift RPC requests.
    """

    def __init__(
            self,
            request_handler: RequestHandler,
            context_builder: ServerContentBuilder | None = None,
    ):
        """Initializes the ThriftHandler.

        Args:
          request_handler: The underlying `RequestHandler` instance to delegate requests to.
            context_builder: The ServerContextBuilder instance to build server context.
        """
        self.request_handler = request_handler
        self.context_builder = context_builder or DefaultServerContentBuilder()

    def completion(self, request: RpcTask) -> RpcTaskResponse:
        # Handle Thrift request
        try:
            server_context = self.context_builder.build_context(request)
            request_obj = thrift_utils.FromProto.rpc_request(request)
            response = AsyncUtils.run_async(self.request_handler.on_message(
                request_obj, server_context
            ))
            return thrift_utils.ToProto.rpc_response(response)
        except Exception as e:
            logger.exception("Error processing Thrift request")
            aduib_error = exception_to_error(e)
            return RpcTaskResponse(
                id=request.id,
                result=b'',
                status='error',
                error=RpcError(code=str(aduib_error.code), message=aduib_error.message, data=json.dumps(aduib_error.data or {})),
            )
