from . import json_schema_pb2 as _json_schema_pb2
from google.protobuf import struct_pb2 as _struct_pb2
from google.protobuf.internal import containers as _containers
from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from typing import ClassVar as _ClassVar, Iterable as _Iterable, Mapping as _Mapping, Optional as _Optional, Union as _Union

DESCRIPTOR: _descriptor.FileDescriptor

class Properties(_message.Message):
    __slots__ = ("properties",)
    class PropertiesEntry(_message.Message):
        __slots__ = ("key", "value")
        KEY_FIELD_NUMBER: _ClassVar[int]
        VALUE_FIELD_NUMBER: _ClassVar[int]
        key: str
        value: _json_schema_pb2.JSONSchema
        def __init__(self, key: _Optional[str] = ..., value: _Optional[_Union[_json_schema_pb2.JSONSchema, _Mapping]] = ...) -> None: ...
    PROPERTIES_FIELD_NUMBER: _ClassVar[int]
    properties: _containers.MessageMap[str, _json_schema_pb2.JSONSchema]
    def __init__(self, properties: _Optional[_Mapping[str, _json_schema_pb2.JSONSchema]] = ...) -> None: ...

class PromptMessages(_message.Message):
    __slots__ = ("content", "role")
    CONTENT_FIELD_NUMBER: _ClassVar[int]
    ROLE_FIELD_NUMBER: _ClassVar[int]
    content: _struct_pb2.Struct
    role: str
    def __init__(self, content: _Optional[_Union[_struct_pb2.Struct, _Mapping]] = ..., role: _Optional[str] = ...) -> None: ...

class ChatCompletion(_message.Message):
    __slots__ = ("enable_thinking", "frequency_penalty", "include_reasoning", "max_completion_tokens", "max_tokens", "messages", "model", "n", "presence_penalty", "prompt", "reasoning_effort", "response_format", "stop", "stream", "stream_options", "temperature", "tool_choice", "tools", "top_k", "top_p", "user", "audio", "modalities", "prompt_embeds")
    class Response_format(_message.Message):
        __slots__ = ("json_schema", "type", "properties")
        class Json_schema(_message.Message):
            __slots__ = ("description", "name", "schema")
            class Schema(_message.Message):
                __slots__ = ("properties", "required", "type")
                PROPERTIES_FIELD_NUMBER: _ClassVar[int]
                REQUIRED_FIELD_NUMBER: _ClassVar[int]
                TYPE_FIELD_NUMBER: _ClassVar[int]
                properties: Properties
                required: _containers.RepeatedScalarFieldContainer[str]
                type: str
                def __init__(self, properties: _Optional[_Union[Properties, _Mapping]] = ..., required: _Optional[_Iterable[str]] = ..., type: _Optional[str] = ...) -> None: ...
            DESCRIPTION_FIELD_NUMBER: _ClassVar[int]
            NAME_FIELD_NUMBER: _ClassVar[int]
            SCHEMA_FIELD_NUMBER: _ClassVar[int]
            description: str
            name: str
            schema: ChatCompletion.Response_format.Json_schema.Schema
            def __init__(self, description: _Optional[str] = ..., name: _Optional[str] = ..., schema: _Optional[_Union[ChatCompletion.Response_format.Json_schema.Schema, _Mapping]] = ...) -> None: ...
        class PropertiesEntry(_message.Message):
            __slots__ = ("key", "value")
            KEY_FIELD_NUMBER: _ClassVar[int]
            VALUE_FIELD_NUMBER: _ClassVar[int]
            key: str
            value: _json_schema_pb2.JSONSchema
            def __init__(self, key: _Optional[str] = ..., value: _Optional[_Union[_json_schema_pb2.JSONSchema, _Mapping]] = ...) -> None: ...
        JSON_SCHEMA_FIELD_NUMBER: _ClassVar[int]
        TYPE_FIELD_NUMBER: _ClassVar[int]
        PROPERTIES_FIELD_NUMBER: _ClassVar[int]
        json_schema: ChatCompletion.Response_format.Json_schema
        type: str
        properties: _containers.MessageMap[str, _json_schema_pb2.JSONSchema]
        def __init__(self, json_schema: _Optional[_Union[ChatCompletion.Response_format.Json_schema, _Mapping]] = ..., type: _Optional[str] = ..., properties: _Optional[_Mapping[str, _json_schema_pb2.JSONSchema]] = ...) -> None: ...
    class Tools(_message.Message):
        __slots__ = ("function", "type")
        class Function(_message.Message):
            __slots__ = ("description", "name", "parameters")
            class Parameters(_message.Message):
                __slots__ = ("properties", "required", "type")
                PROPERTIES_FIELD_NUMBER: _ClassVar[int]
                REQUIRED_FIELD_NUMBER: _ClassVar[int]
                TYPE_FIELD_NUMBER: _ClassVar[int]
                properties: Properties
                required: _containers.RepeatedScalarFieldContainer[str]
                type: str
                def __init__(self, properties: _Optional[_Union[Properties, _Mapping]] = ..., required: _Optional[_Iterable[str]] = ..., type: _Optional[str] = ...) -> None: ...
            DESCRIPTION_FIELD_NUMBER: _ClassVar[int]
            NAME_FIELD_NUMBER: _ClassVar[int]
            PARAMETERS_FIELD_NUMBER: _ClassVar[int]
            description: str
            name: str
            parameters: ChatCompletion.Tools.Function.Parameters
            def __init__(self, description: _Optional[str] = ..., name: _Optional[str] = ..., parameters: _Optional[_Union[ChatCompletion.Tools.Function.Parameters, _Mapping]] = ...) -> None: ...
        FUNCTION_FIELD_NUMBER: _ClassVar[int]
        TYPE_FIELD_NUMBER: _ClassVar[int]
        function: ChatCompletion.Tools.Function
        type: str
        def __init__(self, function: _Optional[_Union[ChatCompletion.Tools.Function, _Mapping]] = ..., type: _Optional[str] = ...) -> None: ...
    class StreamOptionsEntry(_message.Message):
        __slots__ = ("key", "value")
        KEY_FIELD_NUMBER: _ClassVar[int]
        VALUE_FIELD_NUMBER: _ClassVar[int]
        key: str
        value: str
        def __init__(self, key: _Optional[str] = ..., value: _Optional[str] = ...) -> None: ...
    ENABLE_THINKING_FIELD_NUMBER: _ClassVar[int]
    FREQUENCY_PENALTY_FIELD_NUMBER: _ClassVar[int]
    INCLUDE_REASONING_FIELD_NUMBER: _ClassVar[int]
    MAX_COMPLETION_TOKENS_FIELD_NUMBER: _ClassVar[int]
    MAX_TOKENS_FIELD_NUMBER: _ClassVar[int]
    MESSAGES_FIELD_NUMBER: _ClassVar[int]
    MODEL_FIELD_NUMBER: _ClassVar[int]
    N_FIELD_NUMBER: _ClassVar[int]
    PRESENCE_PENALTY_FIELD_NUMBER: _ClassVar[int]
    PROMPT_FIELD_NUMBER: _ClassVar[int]
    REASONING_EFFORT_FIELD_NUMBER: _ClassVar[int]
    RESPONSE_FORMAT_FIELD_NUMBER: _ClassVar[int]
    STOP_FIELD_NUMBER: _ClassVar[int]
    STREAM_FIELD_NUMBER: _ClassVar[int]
    STREAM_OPTIONS_FIELD_NUMBER: _ClassVar[int]
    TEMPERATURE_FIELD_NUMBER: _ClassVar[int]
    TOOL_CHOICE_FIELD_NUMBER: _ClassVar[int]
    TOOLS_FIELD_NUMBER: _ClassVar[int]
    TOP_K_FIELD_NUMBER: _ClassVar[int]
    TOP_P_FIELD_NUMBER: _ClassVar[int]
    USER_FIELD_NUMBER: _ClassVar[int]
    AUDIO_FIELD_NUMBER: _ClassVar[int]
    MODALITIES_FIELD_NUMBER: _ClassVar[int]
    PROMPT_EMBEDS_FIELD_NUMBER: _ClassVar[int]
    enable_thinking: str
    frequency_penalty: int
    include_reasoning: str
    max_completion_tokens: int
    max_tokens: int
    messages: _containers.RepeatedCompositeFieldContainer[PromptMessages]
    model: str
    n: int
    presence_penalty: int
    prompt: str
    reasoning_effort: str
    response_format: ChatCompletion.Response_format
    stop: str
    stream: str
    stream_options: _containers.ScalarMap[str, str]
    temperature: float
    tool_choice: str
    tools: _containers.RepeatedCompositeFieldContainer[ChatCompletion.Tools]
    top_k: int
    top_p: int
    user: str
    audio: _struct_pb2.Struct
    modalities: _struct_pb2.Struct
    prompt_embeds: _struct_pb2.Struct
    def __init__(self, enable_thinking: _Optional[str] = ..., frequency_penalty: _Optional[int] = ..., include_reasoning: _Optional[str] = ..., max_completion_tokens: _Optional[int] = ..., max_tokens: _Optional[int] = ..., messages: _Optional[_Iterable[_Union[PromptMessages, _Mapping]]] = ..., model: _Optional[str] = ..., n: _Optional[int] = ..., presence_penalty: _Optional[int] = ..., prompt: _Optional[str] = ..., reasoning_effort: _Optional[str] = ..., response_format: _Optional[_Union[ChatCompletion.Response_format, _Mapping]] = ..., stop: _Optional[str] = ..., stream: _Optional[str] = ..., stream_options: _Optional[_Mapping[str, str]] = ..., temperature: _Optional[float] = ..., tool_choice: _Optional[str] = ..., tools: _Optional[_Iterable[_Union[ChatCompletion.Tools, _Mapping]]] = ..., top_k: _Optional[int] = ..., top_p: _Optional[int] = ..., user: _Optional[str] = ..., audio: _Optional[_Union[_struct_pb2.Struct, _Mapping]] = ..., modalities: _Optional[_Union[_struct_pb2.Struct, _Mapping]] = ..., prompt_embeds: _Optional[_Union[_struct_pb2.Struct, _Mapping]] = ...) -> None: ...
