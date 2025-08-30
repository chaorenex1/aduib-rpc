import time
from abc import ABC
from decimal import Decimal
from enum import StrEnum, Enum
from typing import List, cast, TypeVar
from typing import Optional, Sequence, Annotated, Union, Literal, Any

from pydantic import BaseModel, Field, field_validator, RootModel
from pydantic import model_validator

T=TypeVar('T')


class ModelUsage(BaseModel):
    pass


class PriceType(Enum):
    """
    Enum class for price type.
    """

    INPUT = "input"
    OUTPUT = "output"


class PriceInfo(BaseModel):
    """
    Model class for price info.
    """

    unit_price: Decimal
    unit: Decimal
    total_amount: Decimal
    currency: str

class LLMMode(StrEnum):
    """
    Enum class for large language model mode.
    """

    COMPLETION = "completion"
    CHAT = "chat"

    @classmethod
    def value_of(cls, value: str) -> "LLMMode":
        """
        Get value of given mode.

        :param value: mode value
        :return: mode
        """
        for mode in cls:
            if mode.value == value:
                return mode
        raise ValueError(f"invalid mode value {value}")


class LLMUsage(ModelUsage):
    """
    Model class for llm usage.
    """

    prompt_tokens: int = 0
    prompt_unit_price: Decimal= Decimal("0.0")
    prompt_price_unit: Decimal= Decimal("0.0")
    prompt_price: Decimal = Decimal("0.0")
    completion_tokens: int = 0
    completion_unit_price: Decimal = Decimal("0.0")
    completion_price_unit: Decimal = Decimal("0.0")
    completion_price: Decimal = Decimal("0.0")
    total_tokens: int = 0
    total_price: Decimal = Decimal("0.0")
    currency: str = "USD"
    latency: float = 0.0

    @classmethod
    def empty_usage(cls):
        return cls(
            prompt_tokens=0,
            prompt_unit_price=Decimal("0.0"),
            prompt_price_unit=Decimal("0.0"),
            prompt_price=Decimal("0.0"),
            completion_tokens=0,
            completion_unit_price=Decimal("0.0"),
            completion_price_unit=Decimal("0.0"),
            completion_price=Decimal("0.0"),
            total_tokens=0,
            total_price=Decimal("0.0"),
            currency="USD",
            latency=0.0,
        )

    def plus(self, other: "LLMUsage") -> "LLMUsage":
        """
        Add two LLMUsage instances together.

        :param other: Another LLMUsage instance to add
        :return: A new LLMUsage instance with summed values
        """
        if self.total_tokens == 0:
            return other
        else:
            return LLMUsage(
                prompt_tokens=self.prompt_tokens + other.prompt_tokens,
                prompt_unit_price=other.prompt_unit_price,
                prompt_price_unit=other.prompt_price_unit,
                prompt_price=self.prompt_price + other.prompt_price,
                completion_tokens=self.completion_tokens + other.completion_tokens,
                completion_unit_price=other.completion_unit_price,
                completion_price_unit=other.completion_price_unit,
                completion_price=self.completion_price + other.completion_price,
                total_tokens=self.total_tokens + other.total_tokens,
                total_price=self.total_price + other.total_price,
                currency=other.currency,
                latency=self.latency + other.latency,
            )

    def __add__(self, other: "LLMUsage") -> "LLMUsage":
        """
        Overload the + operator to add two LLMUsage instances.

        :param other: Another LLMUsage instance to add
        :return: A new LLMUsage instance with summed values
        """
        return self.plus(other)


class NumTokensResult(PriceInfo):
    """
    Model class for number of tokens result.
    """

    tokens: int

class StreamOptions(BaseModel):
    include_usage: Optional[bool] = True
    continuous_usage_stats: Optional[bool] = False

class JsonSchemaResponseFormat(BaseModel):
    name: str
    description: Optional[str] = None
    # schema is the field in openai but that causes conflicts with pydantic so
    # instead use json_schema with an alias
    json_schema: Optional[dict[str, Any]] = Field(default=None, alias='schema')
    strict: Optional[bool] = None


class StructuralTag(BaseModel):
    begin: str
    # schema is the field, but that causes conflicts with pydantic so
    # instead use structural_tag_schema with an alias
    structural_tag_schema: Optional[dict[str, Any]] = Field(default=None,
                                                            alias="schema")
    end: str


class StructuralTagResponseFormat(BaseModel):
    type: Literal["structural_tag"]
    structures: list[StructuralTag]
    triggers: list[str]


class ResponseFormat(BaseModel):
    # type must be "json_schema", "json_object", or "text"
    type: Literal["text", "json_object", "json_schema"]
    json_schema: Optional[JsonSchemaResponseFormat] = None


AnyResponseFormat = Union[ResponseFormat, StructuralTagResponseFormat]

class PromptMessageRole(Enum):
    """
    Enum class for prompt message.
    """

    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"
    TOOL = "tool"

    @classmethod
    def value_of(cls, value: str) -> "PromptMessageRole":
        """
        Get value of given mode.

        :param value: mode value
        :return: mode
        """
        for mode in cls:
            if mode.value == value:
                return mode
        raise ValueError(f"invalid prompt message type value {value}")




class PromptMessageTool(BaseModel):
    """
    Model class for prompt message tool.
    """

    name: str
    description: str
    parameters: dict


class PromptMessageFunction(BaseModel):
    """
    Model class for prompt message function.
    """

    type: str = "function"
    function: PromptMessageTool

class PromptMessageNamedFunction(BaseModel):
    name: str


class PromptMessageToolChoiceParam(BaseModel):
    function: PromptMessageNamedFunction
    type: Literal["function"] = "function"


class PromptMessageContentType(StrEnum):
    """
    Enum class for prompt message content type.
    """

    TEXT = "text"
    IMAGE = "image"
    AUDIO = "audio"
    VIDEO = "video"
    DOCUMENT = "document"


class PromptMessageContent(BaseModel):
    """
    Model class for prompt message content.
    """

    type: PromptMessageContentType


class TextPromptMessageContent(PromptMessageContent):
    """
    Model class for text prompt message content.
    """

    type: PromptMessageContentType = PromptMessageContentType.TEXT
    data: str


class MultiModalPromptMessageContent(PromptMessageContent):
    """
    Model class for multi-modal prompt message content.
    """

    type: PromptMessageContentType
    format: str = Field(default=..., description="the format of multi-modal file")
    base64_data: str = Field(default="", description="the base64 data of multi-modal file")
    url: str = Field(default="", description="the url of multi-modal file")
    mime_type: str = Field(default=..., description="the mime type of multi-modal file")

    @property
    def data(self):
        return self.url or f"data:{self.mime_type};base64,{self.base64_data}"


class VideoPromptMessageContent(MultiModalPromptMessageContent):
    type: PromptMessageContentType = PromptMessageContentType.VIDEO


class AudioPromptMessageContent(MultiModalPromptMessageContent):
    type: PromptMessageContentType = PromptMessageContentType.AUDIO

    @property
    def input_audio(self):
        return {
            "format": self.format,
            "data": self.data,
            "url": self.url,
            "mime_type": self.mime_type
        }


class ImagePromptMessageContent(MultiModalPromptMessageContent):
    """
    Model class for image prompt message content.
    """

    class DETAIL(StrEnum):
        LOW = "low"
        HIGH = "high"

    type: PromptMessageContentType = PromptMessageContentType.IMAGE
    detail: DETAIL = DETAIL.LOW

    @property
    def image_url(self):
        return {
            "format": self.format,
            "data": self.data,
            "url": self.data,
            "mime_type": self.mime_type,
            "detail": self.detail
        }



class DocumentPromptMessageContent(MultiModalPromptMessageContent):
    type: PromptMessageContentType = PromptMessageContentType.DOCUMENT


PromptMessageContentUnionTypes = Annotated[
    Union[
        TextPromptMessageContent,
        ImagePromptMessageContent,
        DocumentPromptMessageContent,
        AudioPromptMessageContent,
        VideoPromptMessageContent,
    ],
    Field(discriminator="type"),
]


class PromptMessage(ABC, BaseModel):
    """
    Model class for prompt message.
    """

    role: PromptMessageRole
    content: Optional[str | Sequence[PromptMessageContent]] = None
    name: Optional[str] = None

    def is_empty(self) -> bool:
        """
        Check if prompt message is empty.

        :return: True if prompt message is empty, False otherwise
        """
        return not self.content

    @classmethod
    def convert_str_prompt_to_contents(cls,str_contents:list['PromptMessage']) -> list['PromptMessage']:
        """
        Convert string prompt messages to content prompt messages.

        :param str_contents: list of string prompt messages
        :return: list of content prompt messages
        """
        contents = []
        for content in str_contents:
            if isinstance(content.content, str):
                content.content=[TextPromptMessageContent(data=content.content)]
                contents.append(content)
            elif isinstance(content.content, PromptMessageContent):
                contents.append(content)
            else:
                raise ValueError(f"Invalid prompt message content type {type(content)}")
        return contents


class UserPromptMessage(PromptMessage):
    """
    Model class for user prompt message.
    """

    role: PromptMessageRole = PromptMessageRole.USER


class AssistantPromptMessage(PromptMessage):
    """
    Model class for assistant prompt message.
    """

    class ToolCall(BaseModel):
        """
        Model class for assistant prompt message tool call.
        """

        class ToolCallFunction(BaseModel):
            """
            Model class for assistant prompt message tool call function.
            """

            name: str
            arguments: str

        id: str
        type: str
        function: ToolCallFunction

        @field_validator("id", mode="before")
        @classmethod
        def transform_id_to_str(cls, value) -> str:
            if not isinstance(value, str):
                return str(value)
            else:
                return value

    role: PromptMessageRole = PromptMessageRole.ASSISTANT
    tool_calls: list[ToolCall] = []
    audio: Optional[dict[str, Any]] = None

    def is_empty(self) -> bool:
        """
        Check if prompt message is empty.

        :return: True if prompt message is empty, False otherwise
        """
        if not super().is_empty() and not self.tool_calls:
            return False

        return True


class SystemPromptMessage(PromptMessage):
    """
    Model class for system prompt message.
    """

    role: PromptMessageRole = PromptMessageRole.SYSTEM


class ToolPromptMessage(PromptMessage):
    """
    Model class for tool prompt message.
    """

    role: PromptMessageRole = PromptMessageRole.TOOL
    tool_call_id: str

    def is_empty(self) -> bool:
        """
        Check if prompt message is empty.

        :return: True if prompt message is empty, False otherwise
        """
        if not super().is_empty() and not self.tool_call_id:
            return False

        return True

class ChatCompletionRequest(BaseModel):
    messages: Optional[list[PromptMessage]] = None
    model: Optional[str] = None
    tools: Optional[list[PromptMessageFunction]] = None
    tool_choice: Optional[Union[
        Literal["none"],
        Literal["auto"],
        Literal["required"],
        PromptMessageToolChoiceParam,
    ]] = "none"
    stream: bool = None
    stream_options: Optional[StreamOptions] = None
    top_p: Optional[float] = None
    top_k: Optional[int] = None
    temperature: Optional[float] = None
    max_tokens: Optional[int] = Field(
        default=None,
        description="The maximum number of tokens that can be present in a prompt.",
        deprecated="max_tokens is deprecated, use max_completion_tokens instead"
    )
    max_completion_tokens: Optional[int] = Field(
        default=None,
        description="The maximum number of tokens that can be generated in the completion."
    )
    n: Optional[int] = 1
    logit_bias: Optional[dict[str, float]] = None
    logprobs: Optional[bool] = False
    top_logprobs: Optional[int] = 0
    stop: Optional[Union[str, Sequence[str]]] = None
    frequency_penalty: Optional[float] = None
    presence_penalty: Optional[float] = None
    response_format: Optional[AnyResponseFormat] = None
    seed: Optional[int] = None
    user: Optional[str] = None
    reasoning_effort: Optional[Literal["low", "medium", "high"]] = None
    include_reasoning: bool = None
    audio: Optional[dict[str,Any]]= None
    modalities: Optional[list[str]]= None


    @field_validator("messages", mode="before")
    @classmethod
    def convert_prompt_messages(cls, v):
        if not isinstance(v, list):
            raise ValueError("prompt_messages must be a list")

        for i in range(len(v)):
            if v[i]["role"] == PromptMessageRole.USER.value:
                v[i] = UserPromptMessage(**v[i])
            elif v[i]["role"] == PromptMessageRole.ASSISTANT.value:
                v[i] = AssistantPromptMessage(**v[i])
            elif v[i]["role"] == PromptMessageRole.SYSTEM.value:
                v[i] = SystemPromptMessage(**v[i])
            elif v[i]["role"] == PromptMessageRole.TOOL.value:
                v[i] = ToolPromptMessage(**v[i])
            else:
                v[i] = PromptMessage(**v[i])

        return v

    @model_validator(mode="before")
    @classmethod
    def validate_stream_options(cls, data):
        if data.get("stream_options") and not data.get("stream"):
            raise ValueError(
                "Stream options can only be defined when `stream=True`.")

        return data

    @model_validator(mode="before")
    @classmethod
    def check_tool_usage(cls, data):

        # if "tool_choice" is not specified but tools are provided,
        # default to "auto" tool_choice
        if "tool_choice" not in data and data.get("tools"):
            data["tool_choice"] = "auto"

        # if "tool_choice" is "none" -- no validation is needed for tools
        if "tool_choice" in data and data["tool_choice"] == "none":
            return data

        # if "tool_choice" is specified -- validation
        if "tool_choice" in data and data["tool_choice"] is not None:

            # ensure that if "tool choice" is specified, tools are present
            if "tools" not in data or data["tools"] is None:
                raise ValueError(
                    "When using `tool_choice`, `tools` must be set.")

            # make sure that tool choice is either a named tool
            # OR that it's set to "auto" or "required"
            if data["tool_choice"] not in [
                "auto", "required"
            ] and not isinstance(data["tool_choice"], dict):
                raise ValueError(
                    f'Invalid value for `tool_choice`: {data["tool_choice"]}! ' \
                    'Only named tools, "none", "auto" or "required" ' \
                    'are supported.'
                )

            # if tool_choice is "required" but the "tools" list is empty,
            # override the data to behave like "none" to align with
            # OpenAI’s behavior.
            if data["tool_choice"] == "required" and isinstance(
                    data["tools"], list) and len(data["tools"]) == 0:
                data["tool_choice"] = "none"
                del data["tools"]
                return data

            # ensure that if "tool_choice" is specified as an object,
            # it matches a valid tool
            correct_usage_message = 'Correct usage: `{"type": "function",' \
                                    ' "function": {"name": "my_function"}}`'
            if isinstance(data["tool_choice"], dict):
                valid_tool = False
                function = data["tool_choice"].get("function")
                if not isinstance(function, dict):
                    raise ValueError(
                        f"Invalid value for `function`: `{function}` in "
                        f"`tool_choice`! {correct_usage_message}")
                if "name" not in function:
                    raise ValueError(f"Expected field `name` in `function` in "
                                     f"`tool_choice`! {correct_usage_message}")
                function_name = function["name"]
                if not isinstance(function_name,
                                  str) or len(function_name) == 0:
                    raise ValueError(
                        f"Invalid `name` in `function`: `{function_name}`"
                        f" in `tool_choice`! {correct_usage_message}")
                for tool in data["tools"]:
                    if tool["function"]["name"] == function_name:
                        valid_tool = True
                        break
                if not valid_tool:
                    raise ValueError(
                        "The tool specified in `tool_choice` does not match any"
                        " of the specified `tools`")
        return data

class CompletionRequest(BaseModel):
    prompt: Optional[Union[list[int], list[list[int]], str, list[str]]] = None
    prompt_embeds: Optional[Union[bytes, list[bytes]]] = None
    model: Optional[str] = None
    stream: bool = None
    stream_options: Optional[StreamOptions] = None
    top_p: Optional[float] = None
    top_k: Optional[int] = None
    temperature: Optional[float] = None
    max_tokens: Optional[int] = Field(
        default=None,
        description="The maximum number of tokens that can be present in a prompt.",
        deprecated="max_tokens is deprecated, use max_completion_tokens instead"
    )
    max_completion_tokens: Optional[int] = Field(
        default=None,
        description="The maximum number of tokens that can be generated in the completion."
    )
    n: Optional[int] = 1
    logit_bias: Optional[dict[str, float]] = None
    logprobs: Optional[bool] = False
    top_logprobs: Optional[int] = 0
    stop: Optional[Union[str, Sequence[str]]] = None
    suffix: Optional[str] = None
    frequency_penalty: Optional[float] = None
    presence_penalty: Optional[float] = None
    response_format: Optional[AnyResponseFormat] = None
    seed: Optional[int] = None
    user: Optional[str] = None

    @model_validator(mode="before")
    @classmethod
    def validate_stream_options(cls, data):
        if data.get("stream_options") and not data.get("stream"):
            raise ValueError(
                "Stream options can only be defined when `stream=True`.")

        return data

    @model_validator(mode="before")
    @classmethod
    def check_tool_usage(cls, data):

        # if "tool_choice" is not specified but tools are provided,
        # default to "auto" tool_choice
        if "tool_choice" not in data and data.get("tools"):
            data["tool_choice"] = "auto"

        # if "tool_choice" is "none" -- no validation is needed for tools
        if "tool_choice" in data and data["tool_choice"] == "none":
            return data

        # if "tool_choice" is specified -- validation
        if "tool_choice" in data and data["tool_choice"] is not None:

            # ensure that if "tool choice" is specified, tools are present
            if "tools" not in data or data["tools"] is None:
                raise ValueError(
                    "When using `tool_choice`, `tools` must be set.")

            # make sure that tool choice is either a named tool
            # OR that it's set to "auto" or "required"
            if data["tool_choice"] not in [
                "auto", "required"
            ] and not isinstance(data["tool_choice"], dict):
                raise ValueError(
                    f'Invalid value for `tool_choice`: {data["tool_choice"]}! ' \
                    'Only named tools, "none", "auto" or "required" ' \
                    'are supported.'
                )

            # if tool_choice is "required" but the "tools" list is empty,
            # override the data to behave like "none" to align with
            # OpenAI’s behavior.
            if data["tool_choice"] == "required" and isinstance(
                    data["tools"], list) and len(data["tools"]) == 0:
                data["tool_choice"] = "none"
                del data["tools"]
                return data

            # ensure that if "tool_choice" is specified as an object,
            # it matches a valid tool
            correct_usage_message = 'Correct usage: `{"type": "function",' \
                                    ' "function": {"name": "my_function"}}`'
            if isinstance(data["tool_choice"], dict):
                valid_tool = False
                function = data["tool_choice"].get("function")
                if not isinstance(function, dict):
                    raise ValueError(
                        f"Invalid value for `function`: `{function}` in "
                        f"`tool_choice`! {correct_usage_message}")
                if "name" not in function:
                    raise ValueError(f"Expected field `name` in `function` in "
                                     f"`tool_choice`! {correct_usage_message}")
                function_name = function["name"]
                if not isinstance(function_name,
                                  str) or len(function_name) == 0:
                    raise ValueError(
                        f"Invalid `name` in `function`: `{function_name}`"
                        f" in `tool_choice`! {correct_usage_message}")
                for tool in data["tools"]:
                    if tool["function"]["name"] == function_name:
                        valid_tool = True
                        break
                if not valid_tool:
                    raise ValueError(
                        "The tool specified in `tool_choice` does not match any"
                        " of the specified `tools`")
        return data

class EmbeddingRequest(BaseModel):
    prompt: str
    model: str
    encoding_format: Optional[str] = "float"

class EmbeddingsResponse(BaseModel):
    embedding: Optional[List[float]] = None
    object: Optional[str] = None
    index: Optional[int] = None


class CreateModelRequest(BaseModel):
    model_name: str
    provider_name: str
    model_type: str
    max_tokens: int
    input_price: float | None = 0.0
    output_price: float | None = 0.0
    model_configs: dict[str, Any]| None = {}
    model_feature: list[str] | None = []

class ChatCompletionResponseChunkDelta(BaseModel):
    """
    Model class for llm result chunk delta.
    """

    index: int
    message: AssistantPromptMessage= None
    text: Optional[str] = None
    usage: Optional[LLMUsage] = None
    finish_reason: Optional[str] = None
    delta: Optional[AssistantPromptMessage] = None


class ChatCompletionResponseChunk(BaseModel):
    """
    Model class for llm result chunk.
    """
    id: Optional[str] = None
    object: Optional[str] = None
    created: Optional[int] = None
    model: str= None
    prompt_messages: Union[list[PromptMessage], str]= None
    system_fingerprint: Optional[str] = None
    choices: list[ChatCompletionResponseChunkDelta]= None
    delta: ChatCompletionResponseChunkDelta= None
    usage: Optional[LLMUsage] = None
    done: bool = False


class ChatCompletionResponse(BaseModel):
    """
    Model class for llm result.
    """

    id: Optional[str] = None
    model: str
    prompt_messages: Union[list[PromptMessage], str] = None
    message: AssistantPromptMessage = None
    usage: LLMUsage
    system_fingerprint: Optional[str] = None
    done: bool = False
    choices: list[ChatCompletionResponseChunkDelta] = None


class CreateProviderRequest(BaseModel):
    provider_name: str
    supported_model_types: list[str]
    provider_type: str
    provider_config: dict[str, Any]


class ModelPermission(BaseModel):
    id: str = Field(default_factory=lambda: f"modelperm-{int(time.time())}")
    object: str = "model_permission"
    created: int = Field(default_factory=lambda: int(time.time()))
    allow_create_engine: bool = False
    allow_sampling: bool = True
    allow_logprobs: bool = True
    allow_search_indices: bool = False
    allow_view: bool = True
    allow_fine_tuning: bool = False
    organization: str = "*"
    group: Optional[str] = None
    is_blocking: bool = False


class ModelCard(BaseModel):
    id: str
    object: str = "model"
    created: int = Field(default_factory=lambda: int(time.time()))
    owned_by: str = "vllm"
    root: Optional[str] = None
    parent: Optional[str] = None
    max_model_len: Optional[int] = None
    permission: list[ModelPermission] = Field(default_factory=list)


class ModelList(BaseModel):
    object: str = "list"
    data: list[ModelCard] = Field(default_factory=list)

class AduibRPCError(BaseModel):
    """
    Represents a JSON-RPC 2.0 Error object, included in an error response.
    """

    code: int
    """
    A number that indicates the error type that occurred.
    """
    data: Any | None = None
    """
    A primitive or structured value containing additional information about the error.
    This may be omitted.
    """
    message: str
    """
    A string providing a short description of the error.
    """

class AduibRpcRequest(BaseModel):
    aduib_rpc: Literal['1.0'] = '1.0'
    method: str
    data: Union[ChatCompletionRequest, CompletionRequest, EmbeddingRequest, dict[str, Any],Any, None] = None
    meta: Optional[dict[str, Any]] = None
    id: Union[str, int, None] = None

    def add_meta(self, key: str, value: Any) -> None:
        if self.meta is None:
            self.meta = {}
        self.meta[key] = value
    def cast(self, typ: type) -> Any:
        if self.data is None:
            return None
        if isinstance(self.data, typ):
            return self.data
        return typ(**self.data)


class AduibRpcResponse(BaseModel):
    aduib_rpc: Literal['1.0'] = '1.0'
    result: Union[ChatCompletionResponse, ChatCompletionResponseChunk, EmbeddingsResponse, dict[str, Any],Any, None] = None
    error: Optional[AduibRPCError] = None
    id: Union[str, int, None] = None
    status: str = 'success' # 'success' or 'error'

    def is_success(self) -> bool:
        return self.status == 'success' and self.error is None

    def cast(self, typ: type) -> Any:
        if self.result is None:
            return None
        if isinstance(self.result, typ):
            return self.result
        return typ(**self.result)

"""
jsonrpc types
"""

class JSONRPCError(BaseModel):
    """
    Represents a JSON-RPC 2.0 Error object, included in an error response.
    """

    code: int
    """
    A number that indicates the error type that occurred.
    """
    data: Any | None = None
    """
    A primitive or structured value containing additional information about the error.
    This may be omitted.
    """
    message: str
    """
    A string providing a short description of the error.
    """

class JSONRPCErrorResponse(BaseModel):
    """
    Represents a JSON-RPC 2.0 Error Response object.
    """

    error: (
        JSONRPCError
    )
    """
    An object describing the error that occurred.
    """
    id: str | int | None = None
    """
    The identifier established by the client.
    """
    jsonrpc: Literal['2.0'] = '2.0'
    """
    The version of the JSON-RPC protocol. MUST be exactly "2.0".
    """

class JSONRPCRequest(BaseModel):
    """
    Represents a JSON-RPC 2.0 Request object.
    """

    id: str | int | None = None
    """
    A unique identifier established by the client. It must be a String, a Number, or null.
    The server must reply with the same value in the response. This property is omitted for notifications.
    """
    jsonrpc: Literal['2.0'] = '2.0'
    """
    The version of the JSON-RPC protocol. MUST be exactly "2.0".
    """
    method: str
    """
    A string containing the name of the method to be invoked.
    """
    params: dict[str, Any] | None = None
    """
    A structured value holding the parameter values to be used during the method invocation.
    """


class JSONRPCSuccessResponse(BaseModel):
    """
    Represents a successful JSON-RPC 2.0 Response object.
    """

    id: str | int | None = None
    """
    The identifier established by the client.
    """
    jsonrpc: Literal['2.0'] = '2.0'
    """
    The version of the JSON-RPC protocol. MUST be exactly "2.0".
    """
    result: Any
    """
    The value of this member is determined by the method invoked on the Server.
    """

class JsonRpcMessageRequest(BaseModel):
    """
    Represents a JSON-RPC request for the `message/send` method.
    """

    id: str | int
    """
    The identifier for this request.
    """
    jsonrpc: Literal['2.0'] = '2.0'
    """
    The version of the JSON-RPC protocol. MUST be exactly "2.0".
    """
    method: Literal['message/completion'] = 'message/completion'
    """
    The method name. Must be 'message/completion'.
    """
    params: AduibRpcRequest
    """
    The parameters for sending a message.
    """

class JsonRpcStreamingMessageRequest(BaseModel):
    """
    Represents a JSON-RPC request for the `message/stream` method.
    """

    id: str | int
    """
    The identifier for this request.
    """
    jsonrpc: Literal['2.0'] = '2.0'
    """
    The version of the JSON-RPC protocol. MUST be exactly "2.0".
    """
    method: Literal['message/completion/stream'] = 'message/completion/stream'
    """
    The method name. Must be 'message/completion/stream'.
    """
    params: AduibRpcRequest
    """
    The parameters for sending a message.
    """

class JsonRpcMessageSuccessResponse(BaseModel):
    """
    Represents a successful JSON-RPC response for the `message/send` method.
    """

    id: str | int | None = None
    """
    The identifier established by the client.
    """
    jsonrpc: Literal['2.0'] = '2.0'
    """
    The version of the JSON-RPC protocol. MUST be exactly "2.0".
    """
    result: AduibRpcResponse
    """
    The result, which can be a direct reply Message or the initial Task object.
    """


class JsonRpcStreamingMessageSuccessResponse(BaseModel):
    """
    Represents a successful JSON-RPC response for the `message/stream` method.
    The server may send multiple response objects for a single request.
    """

    id: str | int | None = None
    """
    The identifier established by the client.
    """
    jsonrpc: Literal['2.0'] = '2.0'
    """
    The version of the JSON-RPC protocol. MUST be exactly "2.0".
    """
    result: AduibRpcResponse
    """
    The result, which can be a Message, Task, or a streaming update event.
    """
class AduibJSONRPCResponse(
    RootModel[
        JSONRPCErrorResponse
        | JsonRpcMessageSuccessResponse
        | JsonRpcStreamingMessageSuccessResponse
    ]):
    root: (
        JSONRPCErrorResponse
        | JsonRpcMessageSuccessResponse
        | JsonRpcStreamingMessageSuccessResponse
    )
    """
    Represents a JSON-RPC response envelope.
    """

class AduibJSONRpcRequest(
    RootModel[JsonRpcMessageRequest
              |JsonRpcStreamingMessageRequest
              ]):
    root: (JsonRpcMessageRequest
           | JsonRpcStreamingMessageRequest)
    """
    Represents a JSON-RPC request envelope.
    """


class JsonRpcMessageResponse(
    RootModel[JSONRPCErrorResponse | JsonRpcMessageSuccessResponse]
):
    root: JSONRPCErrorResponse | JsonRpcMessageSuccessResponse
    """
    Represents a JSON-RPC response for the `message/send` method.
    """


class JsonRpcStreamingMessageResponse(
    RootModel[JSONRPCErrorResponse | JsonRpcStreamingMessageSuccessResponse]
):
    root: JSONRPCErrorResponse | JsonRpcStreamingMessageSuccessResponse
    """
    Represents a JSON-RPC response for the `message/stream` method.
    """
