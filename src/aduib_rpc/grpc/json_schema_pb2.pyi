from google.protobuf.internal import containers as _containers
from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from typing import ClassVar as _ClassVar, Iterable as _Iterable, Mapping as _Mapping, Optional as _Optional, Union as _Union

DESCRIPTOR: _descriptor.FileDescriptor

class JSONSchema(_message.Message):
    __slots__ = ("type", "description", "default_value", "enum", "properties", "items", "min_length", "max_length", "minimum", "maximum", "required", "additional_properties", "one_of", "any_of", "all_of", "pattern", "extensions")
    class PropertiesEntry(_message.Message):
        __slots__ = ("key", "value")
        KEY_FIELD_NUMBER: _ClassVar[int]
        VALUE_FIELD_NUMBER: _ClassVar[int]
        key: str
        value: JSONSchema
        def __init__(self, key: _Optional[str] = ..., value: _Optional[_Union[JSONSchema, _Mapping]] = ...) -> None: ...
    class ExtensionsEntry(_message.Message):
        __slots__ = ("key", "value")
        KEY_FIELD_NUMBER: _ClassVar[int]
        VALUE_FIELD_NUMBER: _ClassVar[int]
        key: str
        value: str
        def __init__(self, key: _Optional[str] = ..., value: _Optional[str] = ...) -> None: ...
    TYPE_FIELD_NUMBER: _ClassVar[int]
    DESCRIPTION_FIELD_NUMBER: _ClassVar[int]
    DEFAULT_VALUE_FIELD_NUMBER: _ClassVar[int]
    ENUM_FIELD_NUMBER: _ClassVar[int]
    PROPERTIES_FIELD_NUMBER: _ClassVar[int]
    ITEMS_FIELD_NUMBER: _ClassVar[int]
    MIN_LENGTH_FIELD_NUMBER: _ClassVar[int]
    MAX_LENGTH_FIELD_NUMBER: _ClassVar[int]
    MINIMUM_FIELD_NUMBER: _ClassVar[int]
    MAXIMUM_FIELD_NUMBER: _ClassVar[int]
    REQUIRED_FIELD_NUMBER: _ClassVar[int]
    ADDITIONAL_PROPERTIES_FIELD_NUMBER: _ClassVar[int]
    ONE_OF_FIELD_NUMBER: _ClassVar[int]
    ANY_OF_FIELD_NUMBER: _ClassVar[int]
    ALL_OF_FIELD_NUMBER: _ClassVar[int]
    PATTERN_FIELD_NUMBER: _ClassVar[int]
    EXTENSIONS_FIELD_NUMBER: _ClassVar[int]
    type: str
    description: str
    default_value: str
    enum: _containers.RepeatedScalarFieldContainer[str]
    properties: _containers.MessageMap[str, JSONSchema]
    items: JSONSchema
    min_length: int
    max_length: int
    minimum: float
    maximum: float
    required: _containers.RepeatedScalarFieldContainer[str]
    additional_properties: bool
    one_of: _containers.RepeatedCompositeFieldContainer[JSONSchema]
    any_of: _containers.RepeatedCompositeFieldContainer[JSONSchema]
    all_of: _containers.RepeatedCompositeFieldContainer[JSONSchema]
    pattern: str
    extensions: _containers.ScalarMap[str, str]
    def __init__(self, type: _Optional[str] = ..., description: _Optional[str] = ..., default_value: _Optional[str] = ..., enum: _Optional[_Iterable[str]] = ..., properties: _Optional[_Mapping[str, JSONSchema]] = ..., items: _Optional[_Union[JSONSchema, _Mapping]] = ..., min_length: _Optional[int] = ..., max_length: _Optional[int] = ..., minimum: _Optional[float] = ..., maximum: _Optional[float] = ..., required: _Optional[_Iterable[str]] = ..., additional_properties: bool = ..., one_of: _Optional[_Iterable[_Union[JSONSchema, _Mapping]]] = ..., any_of: _Optional[_Iterable[_Union[JSONSchema, _Mapping]]] = ..., all_of: _Optional[_Iterable[_Union[JSONSchema, _Mapping]]] = ..., pattern: _Optional[str] = ..., extensions: _Optional[_Mapping[str, str]] = ...) -> None: ...
