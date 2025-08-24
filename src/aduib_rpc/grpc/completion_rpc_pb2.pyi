import chat_completion_pb2 as _chat_completion_pb2
import chat_completion_response_pb2 as _chat_completion_response_pb2
from google.protobuf.internal import containers as _containers
from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from typing import ClassVar as _ClassVar, Iterable as _Iterable, Mapping as _Mapping, Optional as _Optional, Union as _Union

DESCRIPTOR: _descriptor.FileDescriptor

class Meta(_message.Message):
    __slots__ = ("key", "value")
    KEY_FIELD_NUMBER: _ClassVar[int]
    VALUE_FIELD_NUMBER: _ClassVar[int]
    key: str
    value: str
    def __init__(self, key: _Optional[str] = ..., value: _Optional[str] = ...) -> None: ...

class CompletionTask(_message.Message):
    __slots__ = ("request_id", "type", "meta", "payload", "created_at")
    REQUEST_ID_FIELD_NUMBER: _ClassVar[int]
    TYPE_FIELD_NUMBER: _ClassVar[int]
    META_FIELD_NUMBER: _ClassVar[int]
    PAYLOAD_FIELD_NUMBER: _ClassVar[int]
    CREATED_AT_FIELD_NUMBER: _ClassVar[int]
    request_id: str
    type: str
    meta: _containers.RepeatedCompositeFieldContainer[Meta]
    payload: _chat_completion_pb2.ChatCompletion
    created_at: int
    def __init__(self, request_id: _Optional[str] = ..., type: _Optional[str] = ..., meta: _Optional[_Iterable[_Union[Meta, _Mapping]]] = ..., payload: _Optional[_Union[_chat_completion_pb2.ChatCompletion, _Mapping]] = ..., created_at: _Optional[int] = ...) -> None: ...

class CompletionTaskResult(_message.Message):
    __slots__ = ("request_id", "ok", "status_code", "result", "error", "finished_at")
    REQUEST_ID_FIELD_NUMBER: _ClassVar[int]
    OK_FIELD_NUMBER: _ClassVar[int]
    STATUS_CODE_FIELD_NUMBER: _ClassVar[int]
    RESULT_FIELD_NUMBER: _ClassVar[int]
    ERROR_FIELD_NUMBER: _ClassVar[int]
    FINISHED_AT_FIELD_NUMBER: _ClassVar[int]
    request_id: str
    ok: bool
    status_code: int
    result: _chat_completion_response_pb2.ChatCompletionResponse
    error: str
    finished_at: int
    def __init__(self, request_id: _Optional[str] = ..., ok: bool = ..., status_code: _Optional[int] = ..., result: _Optional[_Union[_chat_completion_response_pb2.ChatCompletionResponse, _Mapping]] = ..., error: _Optional[str] = ..., finished_at: _Optional[int] = ...) -> None: ...

class StreamMessage(_message.Message):
    __slots__ = ("task", "result")
    TASK_FIELD_NUMBER: _ClassVar[int]
    RESULT_FIELD_NUMBER: _ClassVar[int]
    task: CompletionTask
    result: CompletionTaskResult
    def __init__(self, task: _Optional[_Union[CompletionTask, _Mapping]] = ..., result: _Optional[_Union[CompletionTaskResult, _Mapping]] = ...) -> None: ...
