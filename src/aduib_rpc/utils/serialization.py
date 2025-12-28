from __future__ import annotations

import json
import pickle
from dataclasses import dataclass
from typing import Any, Protocol

from aduib_rpc.utils.encoders import jsonable_encoder


class SerializationError(ValueError):
    pass


class Serializer(Protocol):
    name: str

    def dumps(self, obj: Any) -> bytes:  # pragma: no cover
        ...

    def loads(self, data: bytes) -> Any:  # pragma: no cover
        ...


@dataclass(frozen=True, slots=True)
class JsonSerializer:
    """Safe, language-agnostic serializer.

    - dumps: json.dumps(jsonable_encoder(obj)) encoded as UTF-8
    - loads: json.loads(bytes)

    Note: bytes are encoded as base64-packed dict: {"__bytes__": "..."}
    """

    name: str = "json"

    def dumps(self, obj: Any) -> bytes:
        try:
            safe_obj = jsonable_encoder(obj)
            return json.dumps(safe_obj, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        except Exception as e:  # noqa: BLE001
            raise SerializationError(str(e)) from e

    def loads(self, data: bytes) -> Any:
        try:
            if not data:
                return None
            obj = json.loads(data.decode("utf-8"))
            return obj
        except Exception as e:  # noqa: BLE001
            raise SerializationError(str(e)) from e


@dataclass(frozen=True, slots=True)
class DangerousPickleSerializer:
    """DANGEROUS: Python pickle serializer.

    This is not safe for untrusted inputs.
    Only use in trusted environments or for short migration windows.
    """

    name: str = "pickle"

    def dumps(self, obj: Any) -> bytes:
        try:
            return pickle.dumps(obj)
        except Exception as e:  # noqa: BLE001
            raise SerializationError(str(e)) from e

    def loads(self, data: bytes) -> Any:
        try:
            if not data:
                return None
            return pickle.loads(data)
        except Exception as e:  # noqa: BLE001
            raise SerializationError(str(e)) from e


def serializer_from_meta(meta: dict[str, Any] | None, *, default: Serializer) -> Serializer:
    """Choose serializer from request meta.

    Supported meta keys:
      - serialization: "json" | "pickle"

    If unknown, falls back to default.
    """

    if not meta:
        return default
    name = meta.get("serialization")
    if name == "json" or name is None:
        return default
    if name == "pickle":
        return DangerousPickleSerializer()
    return default
