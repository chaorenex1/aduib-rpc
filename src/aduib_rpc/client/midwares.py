from abc import ABC, abstractmethod
from collections.abc import MutableMapping
from typing import Any, Tuple

from pydantic import BaseModel, Field

from aduib_rpc.utils.constant import SecuritySchemes


class ClientContext(BaseModel):
    """Client context to hold mutable state information."""

    state : MutableMapping[str, Any] = Field(default_factory=dict)

    def get_schema(self) -> SecuritySchemes:
        """Retrieve the security scheme from the context state."""
        return SecuritySchemes.to_original(self.state.get('security_schema'))

    def get_session_id(self) -> str:
        """Retrieve the session ID from the context state."""
        return self.state.get('session_id', None)



class ClientRequestInterceptor(ABC):
    """Abstract base class for client request interceptors."""

    @abstractmethod
    async def intercept_request(self,
                                method: str,
                                request_body: dict[str, Any],
                                http_kwargs: dict[str, Any],
                                context: ClientContext,
                                schema:SecuritySchemes
                                ) -> Tuple[dict[str, Any], dict[str, Any]]:
        """Intercepts and potentially modifies the outgoing request.

        Args:
            method: The HTTP method (e.g., 'GET', 'POST').
            request_body: The body of the request as a dictionary.
            http_kwargs: Additional HTTP keyword arguments.
            context: The ClientContext instance for maintaining state.
            schema: The security scheme used for the request.
        Returns:
            A tuple containing the potentially modified request body and HTTP keyword arguments.
        """