import logging
from typing import Any

from starlette.applications import Starlette
from starlette.routing import Route

from aduib_rpc.server.app.rpc.jsonrpc_app import JsonRpcApp, ServerContentBuilder
from aduib_rpc.server.request_handlers import RequestHandler

logger=logging.getLogger(__name__)

class AduibRpcStarletteApp(JsonRpcApp):
    """A Starlette application implementing the ADuIB-RPC protocol server endpoints.

    Handles incoming RPC requests, routes them to the appropriate
    handler methods, and manages response generation including Server-Sent Events
    (SSE).
    """

    def __init__(  # noqa: PLR0913
        self,
            request_handler: RequestHandler,
            context_builder: ServerContentBuilder | None = None,
    ):
        """Initializes the AduibRpcStarletteApp.

        Args:
            rpc_handler: The request handler for processing incoming RPC requests.
            context_builder: Optional builder for creating call contexts.
        """
        super().__init__(
            context_builder=context_builder,
            request_handler=request_handler,
        )

    def add_routes(self,
                   app: Starlette,
                   rpc_path: str = "/") -> None:
        """Adds the RPC routes to the Starlette application.
        Args:
            app: The Starlette application instance.
            rpc_path: The path to mount the RPC endpoint.
        """
        app.routes.extend([
            Route(rpc_path, self._handle_requests, methods=["POST"], name="aduib_rpc_handler")
        ])
        logger.debug(f"Added RPC route at path: {rpc_path}")

    def build(self,
              rpc_path: str="/",
              **kwargs: Any)-> Starlette:
        """Builds and returns the Starlette application with the configured routes.

        Returns:
            The configured Starlette application instance.
        """
        app = Starlette(**kwargs)
        self.add_routes(app,rpc_path)
        return app
