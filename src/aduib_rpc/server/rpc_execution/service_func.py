from __future__ import annotations as _annotations

import functools
import inspect
import json
import logging
from collections.abc import Awaitable, Callable, Sequence
from typing import (
    Annotated,
    Any,
    ForwardRef,
)

from pydantic import BaseModel, ConfigDict, Field, WithJsonSchema, create_model
from pydantic._internal._typing_extra import eval_type_backport
from pydantic.fields import FieldInfo
from pydantic_core import PydanticUndefined

from aduib_rpc.discover import MethodDescriptor

logger = logging.getLogger(__name__)


class ArgModelBase(BaseModel):
    """A model representing the arguments to a function."""

    def model_dump_one_level(self) -> dict[str, Any]:
        """Return a dict of the model's fields, one level deep.

        That is, sub-models etc are not dumped - they are kept as pydantic models.
        """
        kwargs: dict[str, Any] = {}
        for field_name in self.__class__.model_fields.keys():
            kwargs[field_name] = getattr(self, field_name)
        return kwargs

    model_config = ConfigDict(
        arbitrary_types_allowed=True,
    )


class OutModelBase(BaseModel):
    """A model representing the output of a function."""

    def model_dump_one_level(self) -> dict[str, Any]:
        """Return a dict of the model's fields, one level deep.

        That is, sub-models etc are not dumped - they are kept as pydantic models.
        """
        kwargs: dict[str, Any] = {}
        for field_name in self.__class__.model_fields.keys():
            kwargs[field_name] = getattr(self, field_name)
        return kwargs

    model_config = ConfigDict(
        arbitrary_types_allowed=True,
    )


class ServiceFuncMetadata(BaseModel):
    arg_model: Annotated[type[ArgModelBase], WithJsonSchema(None)]
    out_model: Annotated[type[OutModelBase], WithJsonSchema(None)]

    # We can add things in the future like
    #  - Maybe some args are excluded from attempting to parse from JSON
    #  - Maybe some args are special (like context) for dependency injection

    async def call_fn_with_arg_validation(
        self,
        fn: Callable[..., Any] | Awaitable[Any],
        fn_is_async: bool,
        arguments_to_validate: dict[str, Any],
        arguments_to_pass_directly: dict[str, Any] | None,
    ) -> Any:
        """Call the given function with arguments validated and injected.

        Arguments are first attempted to be parsed from JSON, then validated against
        the argument model, before being passed to the function.
        """
        arguments_pre_parsed = self.pre_parse_json(arguments_to_validate)
        arguments_parsed_model = self.arg_model.model_validate(arguments_pre_parsed)
        arguments_parsed_dict = arguments_parsed_model.model_dump_one_level()

        arguments_parsed_dict |= arguments_to_pass_directly or {}

        if fn_is_async:
            if isinstance(fn, Awaitable):
                return await fn

            # For async callables:
            # - coroutine functions return awaitables
            # - async-generator functions return an async generator object (NOT awaitable)
            res = fn(**arguments_parsed_dict)
            if inspect.isawaitable(res):
                return await res
            return res

        if isinstance(fn, Callable):
            return fn(**arguments_parsed_dict)
        raise TypeError("fn must be either Callable or Awaitable")

    def pre_parse_json(self, data: dict[str, Any]) -> dict[str, Any]:
        """Pre-parse data from JSON.

        Return a dict with same keys as input but with values parsed from JSON
        if appropriate.

        This is to handle cases like `["a", "b", "c"]` being passed in as JSON inside
        a string rather than an actual list. Claude desktop is prone to this - in fact
        it seems incapable of NOT doing this. For sub-models, it tends to pass
        dicts (JSON objects) as JSON strings, which can be pre-parsed here.
        """
        new_data = data.copy()  # Shallow copy
        for field_name in self.arg_model.model_fields.keys():
            if field_name not in data.keys():
                continue
            if isinstance(data[field_name], str):
                try:
                    pre_parsed = json.loads(data[field_name])
                except json.JSONDecodeError:
                    continue  # Not JSON - skip
                if isinstance(pre_parsed, str | int | float):
                    # This is likely that the raw value is e.g. `"hello"` which we
                    # Should really be parsed as '"hello"' in Python - but if we parse
                    # it as JSON it'll turn into just 'hello'. So we skip it.
                    continue
                new_data[field_name] = pre_parsed
        assert new_data.keys() == data.keys()
        return new_data

    model_config = ConfigDict(
        arbitrary_types_allowed=True,
    )


def func_metadata(func: Callable[..., Any], skip_names: Sequence[str] = ()) -> ServiceFuncMetadata:
    """Given a function, return metadata including a pydantic model representing its
    signature.

    The use case for this is
    ```
    meta = func_to_pyd(func)
    validated_args = meta.arg_model.model_validate(some_raw_data_dict)
    return func(**validated_args.model_dump_one_level())
    ```

    **critically** it also provides pre-parse helper to attempt to parse things from
    JSON.

    Args:
        func: The function to convert to a pydantic model
        skip_names: A list of parameter names to skip. These will not be included in
            the model.
    Returns:
        A pydantic model representing the function's signature.
    """
    sig = _get_typed_signature(func)
    params = sig.parameters
    dynamic_pydantic_model_params: dict[str, Any] = {}
    globalns = getattr(func, "__globals__", {})
    for param in params.values():
        if param.name.startswith("_"):
            raise RuntimeError(f"Parameter {param.name} of {func.__name__} cannot start with '_'")
        if param.name in skip_names:
            continue
        annotation = param.annotation

        # `x: None` / `x: None = None`
        if annotation is None:
            annotation = Annotated[
                None,
                Field(default=param.default if param.default is not inspect.Parameter.empty else PydanticUndefined),
            ]

        # Untyped field
        if annotation is inspect.Parameter.empty:
            annotation = Annotated[
                Any,
                Field(),
                # 🤷
                WithJsonSchema({"title": param.name, "type": "string"}),
            ]

        field_info = FieldInfo.from_annotated_attribute(
            _get_typed_annotation(annotation, globalns),
            param.default if param.default is not inspect.Parameter.empty else PydanticUndefined,
        )
        dynamic_pydantic_model_params[param.name] = (field_info.annotation, field_info)
        continue

    arguments_model = create_model(
        f"{func.__name__}Arguments",
        **dynamic_pydantic_model_params,
        __base__=ArgModelBase,
    )

    # Build output model from return annotation
    return_annotation = _get_return_signature(func)
    out_model = _build_output_model(func.__name__, return_annotation, globalns)

    resp = ServiceFuncMetadata(arg_model=arguments_model, out_model=out_model)
    return resp


def _get_typed_annotation(annotation: Any, globalns: dict[str, Any]) -> Any:
    def try_eval_type(value: Any, globalns: dict[str, Any], localns: dict[str, Any]) -> tuple[Any, bool]:
        try:
            return eval_type_backport(value, globalns, localns), True
        except NameError:
            return value, False

    if isinstance(annotation, str):
        annotation = ForwardRef(annotation)
        annotation, status = try_eval_type(annotation, globalns, globalns)

        # This check and raise could perhaps be skipped, and we (FastMCP) just call
        # model_rebuild right before using it 🤷
        if status is False:
            raise RuntimeError(f"Unable to evaluate type annotation {annotation}")

    return annotation


def _get_typed_signature(call: Callable[..., Any]) -> inspect.Signature:
    """Get function signature while evaluating forward references"""
    signature = inspect.signature(call)
    globalns = getattr(call, "__globals__", {})
    typed_params = [
        inspect.Parameter(
            name=param.name,
            kind=param.kind,
            default=param.default,
            annotation=_get_typed_annotation(param.annotation, globalns),
        )
        for param in signature.parameters.values()
    ]
    typed_signature = inspect.Signature(typed_params)
    return typed_signature


def _get_return_signature(call: Callable[..., Any]) -> Any:
    """Get function return annotation while evaluating forward references"""
    signature = inspect.signature(call)
    globalns = getattr(call, "__globals__", {})
    return _get_typed_annotation(signature.return_annotation, globalns)


def _build_output_model(
    func_name: str,
    return_annotation: Any,
    globalns: dict[str, Any],
) -> type[OutModelBase]:
    """Build a Pydantic model for the function's return type.

    Args:
        func_name: Name of the function (for model naming).
        return_annotation: The evaluated return type annotation.
        globalns: Global namespace for type resolution.

    Returns:
        A Pydantic model class representing the return type.
    """
    # Handle missing or empty return annotation
    if return_annotation is inspect.Parameter.empty or return_annotation is None:
        # No return type specified - use Any
        return create_model(
            f"{func_name}Output",
            result=(Any, Field(default=None, description="Function result")),
            __base__=OutModelBase,
        )

    # Handle None return type (functions that return None)
    if return_annotation is type(None):
        return create_model(
            f"{func_name}Output",
            result=(None, Field(default=None, description="No return value")),
            __base__=OutModelBase,
        )

    # For BaseModel subclasses, wrap them directly
    try:
        if isinstance(return_annotation, type) and issubclass(return_annotation, BaseModel):
            # The return type is already a Pydantic model
            return create_model(
                f"{func_name}Output",
                result=(return_annotation, Field(description="Function result")),
                __base__=OutModelBase,
            )
    except TypeError:
        # issubclass can raise TypeError for non-class types
        pass

    # For other types (primitives, generics, etc.), wrap in a result field
    return create_model(
        f"{func_name}Output",
        result=(return_annotation, Field(description="Function result")),
        __base__=OutModelBase,
    )


class ServiceFunc(BaseModel):
    """Internal service tool representation."""

    fn: Callable[..., Any] = Field(exclude=True)
    wrap_fn: Callable[..., Any] | None = Field(
        default=None,
        description="A wrapper function that takes the same arguments as fn and returns"
        " its result. This can be used to add additional functionality to"
        " the function, such as logging or error handling.",
        exclude=True,
    )
    name: str = Field(description="Name of the tool")
    full_name: str = Field(default="", description="Full name of the tool including namespace")
    description: str = Field(description="Description of what the tool does")
    parameters: dict[str, Any] = Field(description="JSON schema for tool parameters")
    fn_metadata: ServiceFuncMetadata = Field(
        description="Metadata about the function including a pydantic model for tool arguments"
    )
    outputs: dict[str, Any] = Field(description="JSON schema for tool outputs")
    is_async: bool = Field(description="Whether the tool is async")
    version: str = Field(description="Version of the tool")
    deprecated: bool = Field(default=False, description="Whether the tool is deprecated")
    deprecation_message: str = Field(default="", description="Message explaining the deprecation")
    replaced_by: str | None = Field(default=None, description="Name of the tool that replaces this one")
    idempotent_key: str | None = Field(default=None, description="Key for idempotent requests")
    timeout: int | None = Field(default=None, description="Timeout for the tool in seconds")
    long_running: bool = Field(default=False, description="Whether the tool is long-running")
    metadata: dict[str, Any] = Field(default_factory=dict, description="Additional metadata about the tool")
    client_stream: bool = Field(default=False, description="Whether the tool supports client streaming")
    server_stream: bool = Field(default=False, description="Whether the tool supports server streaming")
    bidirectional_stream: bool = Field(default=False, description="Whether the tool supports bidirectional streaming")

    @classmethod
    def from_function(
        cls,
        fn: Callable[..., Any],
        wrap_fn: Callable[..., Any],
        name: str | None = None,
        full_name: str | None = None,
        description: str | None = None,
        version: str = "1.0.0",
        deprecated: bool = False,
        deprecation_message: str | None = None,
        replaced_by: str | None = None,
        idempotent_key: str | None = None,
        timeout: int | None = None,
        long_running: bool = False,
        metadata: dict[str, Any] = None,
        client_stream: bool = False,
        server_stream: bool = False,
        bidirectional_stream: bool = False,
    ) -> ServiceFunc:
        """Create a ServiceFunc from a function."""
        func_name = name or fn.__name__

        if func_name == "<lambda>":
            raise ValueError("You must provide a name for lambda functions")

        func_doc = description or fn.__doc__ or ""
        is_async = _is_async_callable(fn)

        func_arg_metadata = func_metadata(
            fn,
            [],
        )
        parameters = func_arg_metadata.arg_model.model_json_schema()
        outputs = func_arg_metadata.out_model.model_json_schema()

        return cls(
            fn=fn,
            wrap_fn=wrap_fn,
            name=func_name,
            full_name=full_name,
            description=func_doc,
            parameters=parameters,
            fn_metadata=func_arg_metadata,
            outputs=outputs,
            is_async=is_async,
            version=version,
            deprecated=deprecated,
            deprecation_message=deprecation_message or "",
            replaced_by=replaced_by,
            idempotent_key=idempotent_key,
            timeout=timeout,
            long_running=long_running,
            metadata=metadata or {},
            client_stream=client_stream,
            server_stream=server_stream,
            bidirectional_stream=bidirectional_stream,
        )

    def to_descriptor(self) -> MethodDescriptor:
        """Convert to a descriptor dict."""
        return MethodDescriptor(
            name=self.name,
            full_name=self.full_name,
            description=self.description,
            version=self.version,
            deprecated=self.deprecated,
            client_stream=self.client_stream,
            server_stream=self.server_stream,
            bidirectional_stream=self.bidirectional_stream,
        )

    async def run(
        self,
        arguments: dict[str, Any],
    ) -> Any:
        """Run the tool with arguments."""
        try:
            return await self.fn_metadata.call_fn_with_arg_validation(
                self.wrap_fn,
                self.is_async,
                arguments,
                None,
            )
        except Exception as e:
            logger.exception("Error executing tool %s", self.name)
            raise RuntimeError(f"Error executing tool {self.name}") from e


def _is_async_callable(obj: Any) -> bool:
    while isinstance(obj, functools.partial):
        obj = obj.func

    # Coroutine functions are async.
    if inspect.iscoroutinefunction(obj) or (
        callable(obj) and inspect.iscoroutinefunction(getattr(obj, "__call__", None))
    ):
        return True

    # Async-generator functions (`async def ...: yield ...`) are also async callables.
    if inspect.isasyncgenfunction(obj) or (
        callable(obj) and inspect.isasyncgenfunction(getattr(obj, "__call__", None))
    ):
        return True

    return False
