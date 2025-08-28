from google.protobuf import struct_pb2 as _struct_pb2
from . import chat_completion_pb2 as _chat_completion_pb2
from google.protobuf.internal import containers as _containers
from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from typing import ClassVar as _ClassVar, Iterable as _Iterable, Mapping as _Mapping, Optional as _Optional, Union as _Union

DESCRIPTOR: _descriptor.FileDescriptor

class Usage(_message.Message):
    __slots__ = ("prompt_tokens", "completion_tokens", "total_tokens", "currency", "latency")
    PROMPT_TOKENS_FIELD_NUMBER: _ClassVar[int]
    COMPLETION_TOKENS_FIELD_NUMBER: _ClassVar[int]
    TOTAL_TOKENS_FIELD_NUMBER: _ClassVar[int]
    CURRENCY_FIELD_NUMBER: _ClassVar[int]
    LATENCY_FIELD_NUMBER: _ClassVar[int]
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    currency: str
    latency: float
    def __init__(self, prompt_tokens: _Optional[int] = ..., completion_tokens: _Optional[int] = ..., total_tokens: _Optional[int] = ..., currency: _Optional[str] = ..., latency: _Optional[float] = ...) -> None: ...

class ToolCall(_message.Message):
    __slots__ = ("id", "type", "function")
    class FunctionCall(_message.Message):
        __slots__ = ("name", "arguments")
        NAME_FIELD_NUMBER: _ClassVar[int]
        ARGUMENTS_FIELD_NUMBER: _ClassVar[int]
        name: str
        arguments: str
        def __init__(self, name: _Optional[str] = ..., arguments: _Optional[str] = ...) -> None: ...
    ID_FIELD_NUMBER: _ClassVar[int]
    TYPE_FIELD_NUMBER: _ClassVar[int]
    FUNCTION_FIELD_NUMBER: _ClassVar[int]
    id: str
    type: str
    function: ToolCall.FunctionCall
    def __init__(self, id: _Optional[str] = ..., type: _Optional[str] = ..., function: _Optional[_Union[ToolCall.FunctionCall, _Mapping]] = ...) -> None: ...

class MessageContent(_message.Message):
    __slots__ = ("content", "role", "name", "tool_calls", "audio", "annotations")
    CONTENT_FIELD_NUMBER: _ClassVar[int]
    ROLE_FIELD_NUMBER: _ClassVar[int]
    NAME_FIELD_NUMBER: _ClassVar[int]
    TOOL_CALLS_FIELD_NUMBER: _ClassVar[int]
    AUDIO_FIELD_NUMBER: _ClassVar[int]
    ANNOTATIONS_FIELD_NUMBER: _ClassVar[int]
    content: str
    role: str
    name: str
    tool_calls: _containers.RepeatedCompositeFieldContainer[ToolCall]
    audio: _struct_pb2.Struct
    annotations: _struct_pb2.Struct
    def __init__(self, content: _Optional[str] = ..., role: _Optional[str] = ..., name: _Optional[str] = ..., tool_calls: _Optional[_Iterable[_Union[ToolCall, _Mapping]]] = ..., audio: _Optional[_Union[_struct_pb2.Struct, _Mapping]] = ..., annotations: _Optional[_Union[_struct_pb2.Struct, _Mapping]] = ...) -> None: ...

class MessageContentChunk(_message.Message):
    __slots__ = ("index", "message", "text", "usage", "finish_reason", "delta")
    INDEX_FIELD_NUMBER: _ClassVar[int]
    MESSAGE_FIELD_NUMBER: _ClassVar[int]
    TEXT_FIELD_NUMBER: _ClassVar[int]
    USAGE_FIELD_NUMBER: _ClassVar[int]
    FINISH_REASON_FIELD_NUMBER: _ClassVar[int]
    DELTA_FIELD_NUMBER: _ClassVar[int]
    index: int
    message: MessageContent
    text: str
    usage: Usage
    finish_reason: str
    delta: MessageContent
    def __init__(self, index: _Optional[int] = ..., message: _Optional[_Union[MessageContent, _Mapping]] = ..., text: _Optional[str] = ..., usage: _Optional[_Union[Usage, _Mapping]] = ..., finish_reason: _Optional[str] = ..., delta: _Optional[_Union[MessageContent, _Mapping]] = ...) -> None: ...

class ChatCompletionResponse(_message.Message):
    __slots__ = ("id", "object", "created", "model", "choices", "usage", "done", "system_fingerprint", "prompt_messages", "message")
    ID_FIELD_NUMBER: _ClassVar[int]
    OBJECT_FIELD_NUMBER: _ClassVar[int]
    CREATED_FIELD_NUMBER: _ClassVar[int]
    MODEL_FIELD_NUMBER: _ClassVar[int]
    CHOICES_FIELD_NUMBER: _ClassVar[int]
    USAGE_FIELD_NUMBER: _ClassVar[int]
    DONE_FIELD_NUMBER: _ClassVar[int]
    SYSTEM_FINGERPRINT_FIELD_NUMBER: _ClassVar[int]
    PROMPT_MESSAGES_FIELD_NUMBER: _ClassVar[int]
    MESSAGE_FIELD_NUMBER: _ClassVar[int]
    id: str
    object: str
    created: int
    model: str
    choices: _containers.RepeatedCompositeFieldContainer[MessageContentChunk]
    usage: Usage
    done: bool
    system_fingerprint: str
    prompt_messages: _chat_completion_pb2.ChatCompletion
    message: MessageContent
    def __init__(self, id: _Optional[str] = ..., object: _Optional[str] = ..., created: _Optional[int] = ..., model: _Optional[str] = ..., choices: _Optional[_Iterable[_Union[MessageContentChunk, _Mapping]]] = ..., usage: _Optional[_Union[Usage, _Mapping]] = ..., done: bool = ..., system_fingerprint: _Optional[str] = ..., prompt_messages: _Optional[_Union[_chat_completion_pb2.ChatCompletion, _Mapping]] = ..., message: _Optional[_Union[MessageContent, _Mapping]] = ...) -> None: ...
