import json
import pickle
from typing import Any

from google.protobuf import struct_pb2
from google.protobuf.json_format import ParseDict, MessageToDict

from aduib_rpc.grpc import aduib_rpc_pb2
from aduib_rpc.types import ChatCompletionRequest, CompletionRequest, AduibRpcRequest, EmbeddingRequest, \
    AduibRpcResponse, ChatCompletionResponseChunk, EmbeddingsResponse, PromptMessage, AduibRPCError, \
    ChatCompletionResponse
from aduib_rpc.utils.encoders import jsonable_encoder


class FromProto:
    """Utility class for converting protobuf messages to native Python types."""
    @classmethod
    def rpc_request(cls, request:aduib_rpc_pb2.RpcTask) -> AduibRpcRequest:
        request_dict = MessageToDict(request)
        rpc_request = AduibRpcRequest(id=request.id, method=request.method)
        rpc_request.meta=json.loads(request_dict['meta']) if request.meta else {}
        if request.data.chat_completion:
            chat_completion_request:ChatCompletionRequest = pickle.loads(request.data.chat_completion)
            if not chat_completion_request.messages:
                rpc_request.data = CompletionRequest(**chat_completion_request.model_dump(exclude_none=True))
            else:
                rpc_request.data=chat_completion_request
        elif request.data.embedding:
            rpc_request.data=pickle.loads(request.data.embedding).model_dump(exclude_none=True)
        return rpc_request

    @classmethod
    def rpc_response(cls, response: aduib_rpc_pb2.RpcTaskResponse) -> AduibRpcResponse:
        rpc_response = AduibRpcResponse(id=response.id,status=response.status)
        if not rpc_response.is_success():
            rpc_response.error = AduibRPCError(**MessageToDict(response.error))
        else:
            # Determine if the response is a ChatCompletionResponse or ChatCompletionResponseChunk
            if response.result.chat_completion_response:
                rpc_response.result = pickle.loads(response.result.chat_completion_response)
            elif response.result.embedding_response:
                rpc_response.result = pickle.loads(response.result.chat_completion_response)
        return rpc_response


class ToProto:
    """Utility class for converting native Python types to protobuf messages."""
    @classmethod
    def rpc_response(cls, response: AduibRpcResponse) -> aduib_rpc_pb2.RpcTaskResponse:
        rpc_response = aduib_rpc_pb2.RpcTaskResponse(id=response.id, status=response.status)
        if rpc_response.status== 'error':
            rpc_error = aduib_rpc_pb2.RpcError()
            ParseDict(jsonable_encoder(response.error), rpc_error)
            rpc_response.error = rpc_error
        else:
            if isinstance(response.result, ChatCompletionResponse):
                rpc_response.result.chat_completion_response=pickle.dumps(response.result)
            if isinstance(response.result, ChatCompletionResponseChunk):
                rpc_response.result.chat_completion_response=pickle.dumps(response.result)
            elif isinstance(response.result, EmbeddingsResponse):
                rpc_response.result.embedding_response=pickle.dumps(response.result)
        return rpc_response

    @classmethod
    def metadata(cls, metadata: dict[str, Any]):
        if not metadata:
            return None
        return json.dumps(obj=metadata)

    @classmethod
    def taskData(cls, data: Any) -> aduib_rpc_pb2.TaskData:
        task_data = aduib_rpc_pb2.TaskData()
        if isinstance(data, CompletionRequest):
            task_data.chat_completion=pickle.dumps(data)
        elif isinstance(data, ChatCompletionRequest):
            task_data.chat_completion=pickle.dumps(data)
        elif isinstance(data, EmbeddingRequest):
            task_data.embedding=pickle.dumps(data)
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
    for key, value in dictionary.items():
        if isinstance(value, dict):
            struct.fields[key].CopyFrom(dict_to_struct(value))
        else:
            struct.fields[key] = value
    return struct
