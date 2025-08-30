import uuid
from distutils.util import strtobool

from aduib_rpc.server.context import ServerContext
from aduib_rpc.types import AduibRpcRequest


class RequestContext:
    def __init__(self,
        request: AduibRpcRequest | None = None,
        server_context: ServerContext | None = None,
        request_id: str | None = None,
        context_id: str | None = None,
        model_name: str | None = None,
        method: str | None = None,
        stream: bool = False,
        metadata: dict | None = None,
        ):
        """Initializes the RequestContext.
        Args:
            request: The incoming `AduibRpcRequest` object.
            server_context: Context provided by the server.
            request_id: The ID of the request.
            context_id: The ID of the context.
        """
        self.request = request
        self.server_context = server_context
        self.request_id = request_id
        self.context_id = context_id
        self.model_name = model_name
        self.method = method
        self.stream = stream
        if metadata is None:
            self.metadata = request.meta
        if not self.context_id:
            self.context_id = str(uuid.uuid4())

        data_dict = request.data.model_dump(exclude_none=True)
        if not self.model_name:
            self.model_name = request.meta["model"] if request and request.meta and "model" in request.meta else None

            if not self.model_name:
                with data_dict as data:
                    self.model_name = data["model"] if "model" in data else None
        if not self.method:
            self.method = request.method

        if not self.stream:
            self.stream = request.meta["stream"]=='true' if request and request.meta and "stream" in request.meta else False



    def to_dict(self) -> dict:
        """Converts the RequestContext to a dictionary.
        Returns:
            A dictionary representation of the RequestContext.
        """
        return {
            "request": self.request.model_dump(exclude_none=True) if self.request else None,
            "server_context": self.server_context.model_dump(exclude_none=True) if self.server_context else None,
            "request_id": self.request_id,
            "context_id": self.context_id,
        }

    def get_input_data(self) -> AduibRpcRequest | None:
        """Returns the request object.
        Returns:
            The `AduibRpcRequest` object.
        """
        return self.request.data

    def get_server_context(self) -> ServerContext | None:
        """Returns the server context object.
        Returns:
            The `ServerContext` object.
        """
        return self.server_context

    def get_request_id(self) -> str | None:
        """Returns the request ID.
        Returns:
            The request ID.
        """
        return self.request_id

    def get_context_id(self) -> str:
        """Returns the context ID.
        Returns:
            The context ID.
        """
        return self.context_id

    def get_model_name(self) -> str:
        """Returns the model name.
        Returns:
            The model name.
        """
        return self.model_name

    def is_stream(self) -> bool:
        """Returns whether the request is a stream request.
        Returns:
            True if the request is a stream request, False otherwise.
        """
        return self.stream

    def get_method(self) -> str:
        """Returns the method name.
        Returns:
            The method name.
        """
        return self.method

    def get_metadata(self) -> dict | None:
        """Returns the metadata.
        Returns:
            The metadata.
        """
        return self.metadata
