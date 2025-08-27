from aduib_rpc.types import JSONRPCErrorResponse


class ClientError(Exception):
    """Base class for all client-related errors."""
    pass

class ClientHTTPError(ClientError):
    """Raised for HTTP-related errors in the client."""
    def __init__(self, status_code: int, message: str):
        self.status_code = status_code
        self.message = message
        super().__init__(f"HTTP {status_code}: {message}")

class ClientJSONRPCError(ClientError):
    """Raised for JSON-RPC specific errors in the client."""
    def __init__(self, error: JSONRPCErrorResponse):
        self.error = error
        super().__init__(f"JSON-RPC Error {error.error.code}: {error.error.message}")


class ClientJSONError(ClientError):
    """Raised for JSON decoding or validation errors in the client."""
    def __init__(self, message: str):
        self.message = message
        super().__init__(f"JSON Error: {message}")
