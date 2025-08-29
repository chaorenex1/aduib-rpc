from abc import ABC, abstractmethod
from typing import Any

from aduib_rpc.client.midwares import ClientContext


class CredentialsProvider(ABC):
    """Abstract base class for providing credentials."""

    @abstractmethod
    async def get_credentials(self,scheme: str,context: ClientContext) -> str | None:
        """Fetches credentials based on the provided scheme and context.

        Args:
            scheme: The authentication scheme (e.g., "Bearer", "Basic").
            context: The client context containing request-specific information.
        Returns:
            The credentials as a string, or None if not available.
        """


class InMemoryCredentialsProvider(CredentialsProvider):
    """In-memory implementation of CredentialsProvider."""

    def __init__(self):
        """Initializes the InMemoryCredentialsProvider with optional credentials."""
        self._store: dict[str, Any] = {}

    async def get_credentials(self,scheme: str,session_id: str) -> str | None:
        """Returns the stored credentials.

        Args:
            scheme: The authentication scheme (e.g., "Bearer", "Basic").
            session_id: The session ID to retrieve credentials for. If None, uses a default key.
        Returns:
            The stored credentials as a string, or None if not set.
        """
        return self._store.get(session_id).get(scheme)


    def set_credentials(self,scheme: str,credentials: str,session_id: str | None = None) -> None:
        """Sets the credentials for a specific scheme and session ID.

        Args:
            scheme: The authentication scheme (e.g., "Bearer", "Basic").
            credentials: The credentials to store.
            session_id: The session ID to associate with the credentials. If None, uses a default key.
        """
        if session_id not in self._store:
            self._store[session_id] = {}
        self._store[session_id][scheme] = credentials