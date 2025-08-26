from google.protobuf.internal import containers as _containers
from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from typing import ClassVar as _ClassVar, Iterable as _Iterable, Mapping as _Mapping, Optional as _Optional, Union as _Union

DESCRIPTOR: _descriptor.FileDescriptor

class EmbeddingRequest(_message.Message):
    __slots__ = ("prompt", "model", "encoding_format", "prompts")
    PROMPT_FIELD_NUMBER: _ClassVar[int]
    MODEL_FIELD_NUMBER: _ClassVar[int]
    ENCODING_FORMAT_FIELD_NUMBER: _ClassVar[int]
    PROMPTS_FIELD_NUMBER: _ClassVar[int]
    prompt: str
    model: str
    encoding_format: str
    prompts: _containers.RepeatedScalarFieldContainer[str]
    def __init__(self, prompt: _Optional[str] = ..., model: _Optional[str] = ..., encoding_format: _Optional[str] = ..., prompts: _Optional[_Iterable[str]] = ...) -> None: ...

class EmbeddingBatchResult(_message.Message):
    __slots__ = ("embedding", "index")
    EMBEDDING_FIELD_NUMBER: _ClassVar[int]
    INDEX_FIELD_NUMBER: _ClassVar[int]
    embedding: _containers.RepeatedScalarFieldContainer[float]
    index: int
    def __init__(self, embedding: _Optional[_Iterable[float]] = ..., index: _Optional[int] = ...) -> None: ...

class EmbeddingResponse(_message.Message):
    __slots__ = ("object", "model", "embedding", "embeddings", "index")
    OBJECT_FIELD_NUMBER: _ClassVar[int]
    MODEL_FIELD_NUMBER: _ClassVar[int]
    EMBEDDING_FIELD_NUMBER: _ClassVar[int]
    EMBEDDINGS_FIELD_NUMBER: _ClassVar[int]
    INDEX_FIELD_NUMBER: _ClassVar[int]
    object: str
    model: str
    embedding: _containers.RepeatedScalarFieldContainer[float]
    embeddings: _containers.RepeatedCompositeFieldContainer[EmbeddingBatchResult]
    index: int
    def __init__(self, object: _Optional[str] = ..., model: _Optional[str] = ..., embedding: _Optional[_Iterable[float]] = ..., embeddings: _Optional[_Iterable[_Union[EmbeddingBatchResult, _Mapping]]] = ..., index: _Optional[int] = ...) -> None: ...
