from typing import Any, Tuple

from aduib_rpc.client.auth.credentials import CredentialsProvider
from aduib_rpc.client.midwares import ClientRequestInterceptor, ClientContext
from aduib_rpc.utils.constant import SecuritySchemes


class AuthInterceptor(ClientRequestInterceptor):
    """Authentication interceptor for client requests."""

    def __init__(self, credentialProvider: CredentialsProvider):
        self.credentialProvider = credentialProvider

    async def intercept_request(self, method: str, request_body: dict[str, Any], http_kwargs: dict[str, Any],
                                context: ClientContext,schema:SecuritySchemes) -> Tuple[dict[str, Any], dict[str, Any]]:
        """Intercepts the request to add authentication headers.
        Args:
            method: The RPC method being called.
            request_body: The body of the request.
            http_kwargs: Additional HTTP keyword arguments.
            context: The client context.
            schema: The security scheme to use for authentication.
        Returns:
            A tuple containing the modified request body and HTTP keyword arguments.
        """
        session_id = context.state["session_id"]
        if schema is None:
            return request_body, http_kwargs
        token = await self.credentialProvider.get_credentials(schema, session_id)
        match schema:
            case SecuritySchemes.APIKey:
                if "headers" not in http_kwargs:
                    http_kwargs["headers"] = {}
                http_kwargs["headers"]["X-API-Key"] = token
            case SecuritySchemes.OAuth2:
                if "headers" not in http_kwargs:
                    http_kwargs["headers"] = {}
                http_kwargs["headers"]["Authorization"] = f"Bearer {token}"
            case _:
                raise ValueError(f"Unsupported security scheme: {schema}")
        return request_body, http_kwargs
