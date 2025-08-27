import logging
from typing import Any

from fastapi import FastAPI

from aduib_rpc.server.protocols.rpc.jsonrpc_app import JsonRpcApp, ServerContextBuilder
from aduib_rpc.server.request_handlers import RequestHandler
from aduib_rpc.types import AduibJSONRpcRequest
from aduib_rpc.utils.constant import DEFAULT_RPC_PATH

logger=logging.getLogger(__name__)

class AduibFastAPI(FastAPI):
    """A FastAPI application that adds Aduib-specific OpenAPI components."""

    _aduib_components_added: bool = False

    def openapi(self) -> dict[str, Any]:
        """Generates the OpenAPI schema for the application."""
        openapi_schema = super().openapi()
        if not self._aduib_components_added:
            # Add Aduib-specific components here
            aduib_request_schema = AduibJSONRpcRequest.model_json_schema(ref_template="#/components/schemas/{model}")
            defs = aduib_request_schema.pop("$defs", {})
            component_schemas = openapi_schema.setdefault("components", {}).setdefault("schemas", {})
            component_schemas.update(defs)
            component_schemas["AduibJSONRpcRequest"] = aduib_request_schema
            self._aduib_components_added = True
        return openapi_schema


class AduibRPCFastAPIApp(JsonRpcApp):
    """A FastAPI application implementing the Aduib RPC protocol server endpoints.

    Handles incoming RPC requests, routes them to the appropriate
    handler methods, and manages response generation.
    """

    def __init__(  # noqa: PLR0913
        self,
        request_handler: RequestHandler,
        context_builder: ServerContextBuilder | None = None,
    ):
        """Initializes the AduibRPCFastAPIApp.

        Args:
            rpc_handler: The request handler to process incoming RPC requests.
            context_builder: Optional builder for creating call contexts.
                If not provided, a default builder is used.
        """
        super().__init__(context_builder, request_handler)

    def add_routes(self, app: AduibFastAPI, rpc_path: str = DEFAULT_RPC_PATH) -> None:
        """Adds the RPC routes to the FastAPI application.

        Args:
            app: The FastAPI application instance.
            rpc_path: The URL path for the RPC endpoint.
        """
        app.post(
            rpc_path,
        openapi_extra={
            "requestBody": {
                "content": {
                    "application/json": {
                        "schema": {"$ref": "#/components/schemas/AduibJSONRpcRequest"}
                    }
                },
                "required": True,
                "description": "Aduib RPC request payload",
            },
        })(self._handle_requests)
        logger.debug(f"Added RPC route at {rpc_path}")

    def build(
        self,
        rpc_path: str = DEFAULT_RPC_PATH,
        **kwargs: Any,
    ) -> FastAPI:
        """Builds and returns the FastAPI application with RPC routes.

        Args:
            rpc_path: The URL path for the RPC endpoint.
            **kwargs: Additional keyword arguments for FastAPI initialization.

        Returns:
            The configured FastAPI application instance.
        """
        app = AduibFastAPI(**kwargs)
        self.add_routes(app, rpc_path)
        return app