from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

_V2_PREFIX = "rpc.v2/"

class MethodProtocol(StrEnum):
    """RPC protocol versions."""

    V1 = "1.0"
    V2 = "2.0"


# Pattern for rpc.v2/{service}/{handler} format
_V2_METHOD_PATTERN = re.compile(
    r"^rpc\.v2/(?P<service>[a-zA-Z][a-zA-Z0-9_]*)/(?P<handler>[a-zA-Z][a-zA-Z0-9_]*)$"
)

# Pattern for legacy format {service}.{handler}
_LEGACY_METHOD_PATTERN = re.compile(
    r"^(?P<service>[a-zA-Z][a-zA-Z0-9_]*)\.(?P<handler>[a-zA-Z][a-zA-Z0-9_]*)$"
)


def parse_method_name(method: str) -> dict[str, Any] | None:
    """Parse a method name into its components.

    Supports formats:
    - `rpc.v2/{service}/{handler}` - v2 format with protocol prefix
    - `{service}.{handler}` - legacy format

    Args:
        method: Method name to parse.

    Returns:
        Dict with keys: protocol, service, handler, normalized
        Returns None if format is unrecognized.
    """
    # Try v2 format first
    match = _V2_METHOD_PATTERN.match(method)
    if match:
        return {
            "protocol": "v2",
            "service": match.group("service"),
            "handler": match.group("handler"),
            "normalized": method,
        }

    # Try legacy format
    match = _LEGACY_METHOD_PATTERN.match(method)
    if match:
        service = match.group("service")
        handler = match.group("handler")
        return {
            "protocol": "v1",
            "service": service,
            "handler": handler,
            "normalized": f"{service}.{handler}",
        }

    return None


def normalize_method_name(method: str, target_protocol: str = "v2") -> str | None:
    """Normalize a method name to the target protocol format.

    Args:
        method: Method name to normalize.
        target_protocol: Target protocol (v1 or v2).

    Returns:
        Normalized method name or None if parsing fails.
    """
    parsed = parse_method_name(method)
    if not parsed:
        return None

    if target_protocol == "v2":
        if parsed["protocol"] == "v2":
            return parsed["normalized"]
        # Convert v1 to v2
        return f"rpc.v2/{parsed['service']}/{parsed['handler']}"
    else:  # v1
        if parsed["protocol"] == "v1":
            return parsed["normalized"]
        # Convert v2 to v1
        return f"{parsed['service']}.{parsed['handler']}"

@dataclass(frozen=True, slots=True)
class MethodName:
    """Normalized RPC method name.

    Contract:
    - service: logical service name (from @service("...") / @client("...")).
    - handler: stable handler identifier, recommended "ClassName.method".

    We support a versioned wire format and a compatibility parser for legacy formats.
    """

    service: str
    handler: str

    @property
    def v2(self) -> str:
        return self.format_v2(self.service, self.handler)

    @staticmethod
    def format_v2(service: str, handler: str) -> str:
        if not service:
            raise ValueError("service must not be empty")
        if not handler:
            raise ValueError("handler must not be empty")
        return f"{_V2_PREFIX}{service}/{handler}"

    @staticmethod
    def parse_compat(method: str) -> "MethodName":
        """Parse incoming method string.

        Supported:
        - v2: "rpc.v2/{service}/{handler}" (also tolerates leading '/', whitespace)
        - legacy unary: "{service}.{handler}"
        - legacy (module) unary: "{service}.{module}.{func}" -> handler becomes "module.func"
        - legacy separators: allow '/', ':' as separators (e.g. "Svc/Cls.m", "Svc:Cls.m")

        Note: legacy formats are ambiguous; after extracting service, we keep the
        remaining tail joined with '.' as handler.
        """
        if method is None:
            raise ValueError("method must not be None")

        m = method.strip()
        if not m:
            raise ValueError("method must not be empty")

        # Tolerate leading slash from some HTTP routers.
        if m.startswith("/"):
            m = m.lstrip("/")

        if m.startswith(_V2_PREFIX):
            rest = m[len(_V2_PREFIX) :]
            service, sep, handler = rest.partition("/")
            if not sep or not service or not handler:
                raise ValueError(f"Invalid v2 method: {method!r}")
            return MethodName(service=service, handler=handler)

        # Normalize other legacy separators into dotted form.
        # We only replace the first separator between service and handler.
        if ":" in m:
            service, sep, tail = m.partition(":")
            if sep and service and tail:
                m = f"{service}.{tail}"
        elif "/" in m and "." not in m:
            service, sep, tail = m.partition("/")
            if sep and service and tail:
                m = f"{service}.{tail}"

        parts = m.split(".")
        if len(parts) < 2:
            raise ValueError(f"Invalid legacy method: {method!r}")

        service = parts[0]
        handler = ".".join(parts[1:])
        if not service or not handler:
            raise ValueError(f"Invalid legacy method: {method!r}")
        return MethodName(service=service, handler=handler)
