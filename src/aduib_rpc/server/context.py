import collections
from abc import ABC, abstractmethod
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from aduib_rpc.types import AduibRpcRequest, AduibRPCError

State=collections.abc.MutableMapping[str, Any]

class ServerContext(BaseModel):
    """Context for the server, including configuration and state information."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    state: State = Field(default_factory=dict)

    metadata: dict[str,Any] = Field(default_factory=dict)


class ServerInterceptor(ABC):
    """Abstract base class for server interceptors."""

    @abstractmethod
    async def intercept(
        self,
        request_body: AduibRpcRequest,
        context: ServerContext,
    ) -> AduibRPCError | None:
        """Intercepts and potentially modifies the incoming request.

        Args:
            request_body: The parsed request body.
            context: The ServerContext instance for maintaining state.

        Returns:
            An error object to short-circuit the request, or None to continue.
        """
