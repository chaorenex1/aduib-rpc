from typing import Any

from google.protobuf.json_format import ParseDict, MessageToDict
from google.protobuf.proto import parse
from pydantic import BaseModel

from aduib_rpc.grpc.chat_completion_pb2 import ChatCompletion
from aduib_rpc.grpc.chat_completion_response_pb2 import ChatCompletionResponse
from aduib_rpc.types import ChatCompletionRequest, CompletionRequest


class FromProto:
    """Utility class for converting protobuf messages to native Python types."""
    @classmethod
    def chat_completion_request(cls, request:ChatCompletion) -> ChatCompletionRequest:
        request_dict = MessageToDict(request)
        return ChatCompletionRequest(**request_dict)

    @classmethod
    def completion_request(cls, request: ChatCompletion) -> CompletionRequest:
        request_dict = MessageToDict(request)
        return CompletionRequest(**request_dict)


class ToProto:
    """Utility class for converting native Python types to protobuf messages."""
    @classmethod
    def chat_completion(cls, request: ChatCompletionRequest) -> ChatCompletion:
        return ParseDict(request.model_dump(exclude_none=True), ChatCompletion())

    @classmethod
    def completion(cls, request: CompletionRequest) -> ChatCompletion:
        return ParseDict(request.model_dump(exclude_none=True), ChatCompletion())

    @classmethod
    def chat_completion_response(cls, response:BaseModel)-> ChatCompletionResponse:
        return ParseDict(response.model_dump(exclude_none=True), ChatCompletionResponse())
