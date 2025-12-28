from __future__ import annotations

from dataclasses import dataclass


_V2_PREFIX = "rpc.v2/"


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
