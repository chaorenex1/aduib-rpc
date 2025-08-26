from google.protobuf.json_format import ParseDict, MessageToDict

from aduib_rpc.grpc import aduib_rpc_pb2, chat_completion_response_pb2, embedding_pb2
from aduib_rpc.grpc.chat_completion_response_pb2 import ChatCompletionResponse
from aduib_rpc.types import ChatCompletionRequest, CompletionRequest, AduibRpcRequest, EmbeddingRequest, \
    AduibRpcResponse, ChatCompletionResponseChunk, EmbeddingsResponse


class FromProto:
    """Utility class for converting protobuf messages to native Python types."""
    @classmethod
    def rpc_request(cls, request:aduib_rpc_pb2.RpcTask) -> AduibRpcRequest:
        request_dict = MessageToDict(request)
        rpc_request = AduibRpcRequest(**request_dict)
        if request.data.chat_completion:
            chat_completion_dict = MessageToDict(request.data.chat_completion)
            chat_completion_request = ChatCompletionRequest(**chat_completion_dict)
            if not chat_completion_request.messages:
                rpc_request.data = CompletionRequest(**chat_completion_dict)
            else:
                rpc_request.data=chat_completion_request
        elif request.data.embedding:
            rpc_request.data=EmbeddingRequest(**MessageToDict(request.data.embedding))
        return rpc_request


class ToProto:
    """Utility class for converting native Python types to protobuf messages."""
    @classmethod
    def rpc_response(cls, response: AduibRpcResponse) -> aduib_rpc_pb2.RpcTaskResponse:
        response_dict = response.model_dump(exclude_none=True)
        rpc_response = aduib_rpc_pb2.RpcTaskResponse()
        ParseDict(response_dict, rpc_response)
        if isinstance(response.result, ChatCompletionResponse):
            chat_completion_response = chat_completion_response_pb2.ChatCompletionResponse()
            ParseDict(response.result.model_dump(exclude_none=True), chat_completion_response)
            rpc_response.result.chat_completion_response.CopyFrom(chat_completion_response)
        if isinstance(response.result, ChatCompletionResponseChunk):
            chat_completion_response = chat_completion_response_pb2.ChatCompletionResponse()
            ParseDict(response.result.model_dump(exclude_none=True), chat_completion_response)
            rpc_response.result.chat_completion_response.CopyFrom(chat_completion_response)
        elif isinstance(response.result, EmbeddingsResponse):
            embedding_response = embedding_pb2.EmbeddingResponse()
            ParseDict(response.result.model_dump(exclude_none=True), embedding_response)
            rpc_response.result.embedding_response.CopyFrom(embedding_response)
        return rpc_response
