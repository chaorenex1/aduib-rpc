from typing import Any

from google.protobuf import struct_pb2
from google.protobuf.json_format import ParseDict, MessageToDict

from aduib_rpc.grpc import aduib_rpc_pb2, chat_completion_response_pb2, embedding_pb2, chat_completion_pb2
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

    @classmethod
    def rpc_response(cls, response: aduib_rpc_pb2.RpcTaskResponse) -> AduibRpcResponse:
        response_dict = MessageToDict(response)
        rpc_response = AduibRpcResponse(**response_dict)
        if response.result.chat_completion_response:
            chat_completion_response_dict = MessageToDict(response.result.chat_completion_response)
            if 'choices' in chat_completion_response_dict and chat_completion_response_dict['choices']:
                if 'delta' in chat_completion_response_dict['choices'][0]:
                    rpc_response.result = ChatCompletionResponseChunk(**chat_completion_response_dict)
                else:
                    rpc_response.result = ChatCompletionResponse(**chat_completion_response_dict)
        elif response.result.embedding_response:
            rpc_response.result = EmbeddingsResponse(**MessageToDict(response.result.embedding_response))
        return rpc_response


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

    @classmethod
    def metadata(cls, metadata: dict[str, Any]) -> struct_pb2.Struct | None:
        if not metadata:
            return None
        return dict_to_struct(metadata)

    @classmethod
    def taskData(cls, data: Any) -> aduib_rpc_pb2.TaskData:
        task_data = aduib_rpc_pb2.TaskData()
        if isinstance(data, CompletionRequest):
            chat_completion_request = chat_completion_pb2.ChatCompletion()
            ParseDict(data.model_dump(exclude_none=True), chat_completion_request)
            task_data.chat_completion.CopyFrom(chat_completion_request)
        elif isinstance(data, ChatCompletionRequest):
            chat_completion_request = chat_completion_pb2.ChatCompletion()
            ParseDict(data.model_dump(exclude_none=True), chat_completion_request)
            task_data.chat_completion.CopyFrom(chat_completion_request)
        elif isinstance(data, EmbeddingRequest):
            embedding_request = embedding_pb2.EmbeddingRequest()
            ParseDict(data.model_dump(exclude_none=True), embedding_request)
            task_data.embedding.CopyFrom(embedding_request)
        return task_data


def dict_to_struct(dictionary: dict[str, Any]) -> struct_pb2.Struct:
    """Converts a Python dict to a Struct proto.

    Unfortunately, using `json_format.ParseDict` does not work because this
    wants the dictionary to be an exact match of the Struct proto with fields
    and keys and values, not the traditional Python dict structure.

    Args:
      dictionary: The Python dict to convert.

    Returns:
      The Struct proto.
    """
    struct = struct_pb2.Struct()
    for key, val in dictionary.items():
        if isinstance(val, dict):
            struct[key] = dict_to_struct(val)
        else:
            struct[key] = val
    return struct
