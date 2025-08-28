import logging
from typing import AsyncGenerator

import grpc
from grpc.aio import Channel

from aduib_rpc.client.config import ClientConfig
from aduib_rpc.client.errors import ClientHTTPError
from aduib_rpc.client import ClientContext, ClientRequestInterceptor
from aduib_rpc.client.transports.base import ClientTransport
from aduib_rpc.grpc import aduib_rpc_pb2_grpc, aduib_rpc_pb2
from aduib_rpc.types import AduibRpcRequest, AduibRpcResponse
from aduib_rpc.utils import proto_utils

logger = logging.getLogger(__name__)


class GrpcTransport(ClientTransport):
    """A gRPC transport for the Aduib RPC client."""

    def __init__(
        self,
        channel: Channel,
    ):
        """Initializes the GrpcTransport."""
        self.channel = channel
        self.stub = aduib_rpc_pb2_grpc.AduibRpcServiceStub(channel)

    @classmethod
    def create(
        cls,
        url: str,
        config: ClientConfig,
        interceptors: list[ClientRequestInterceptor],
    ) -> 'GrpcTransport':
        """Creates a gRPC transport for the A2A client."""
        if config.grpc_channel_factory is None:
            raise ValueError('grpc_channel_factory is required when using gRPC')
        return cls(
            config.grpc_channel_factory(url),
        )


    async def completion(self, request: AduibRpcRequest, *, context: ClientContext) -> AduibRpcResponse:
        """Sends a message to the agent and returns the response."""
        grpc_metadata = []
        if request.meta:
            for key, value in request.meta.items():
                grpc_metadata.append((key, value))
        data = proto_utils.ToProto.taskData(request.data)
        task = aduib_rpc_pb2.RpcTask(id=request.id, method=request.method, meta=proto_utils.ToProto.metadata(request.meta), data=data)
        response = await self.stub.completion(
            task,
            metadata=grpc_metadata
        )
        rpc_response = proto_utils.FromProto.rpc_response(response)
        if not rpc_response.is_success():
            raise ClientHTTPError(rpc_response.error.code, rpc_response.error.message)
        return rpc_response

    async def completion_stream(self, request: AduibRpcRequest, *, context: ClientContext) -> AsyncGenerator[
        AduibRpcResponse, None]:
        """Sends a streaming message to the agent and yields the responses."""
        grpc_metadata = []
        if request.meta:
            for key, value in request.meta.items():
                grpc_metadata.append((key, value))
        stream=self.stub.stream_completion(
            aduib_rpc_pb2.RpcTask(id=request.id,
                                  method=request.method,
                                  meta=proto_utils.ToProto.metadata(request.meta),
                                  data=proto_utils.ToProto.taskData(request.data)
            ),
            metadata=grpc_metadata
        )
        # try:
        #     async for response in stream:
        #         rpc_response = proto_utils.FromProto.rpc_response(response)
        #         if not rpc_response.is_success():
        #             raise ClientHTTPError(rpc_response.error.code, rpc_response.error.message)
        #         yield rpc_response
        # except Exception as e:
        #     logging.error(f"Error in gRPC stream: {e}")

        while True:
            try:
                response = await stream.read()
                if response == grpc.aio.EOF:
                    break
                rpc_response = proto_utils.FromProto.rpc_response(response)
                if not rpc_response.is_success():
                    raise ClientHTTPError(rpc_response.error.code, rpc_response.error.message)
                yield rpc_response
            except Exception as e:
                logger.error(f"Error in gRPC stream: {e}")
                break