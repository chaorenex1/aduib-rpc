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
        - v2: "rpc.v2/{service}/{handler}"
        - legacy unary: "{service}.{handler}"
        - legacy (module) unary: "{service}.{module}.{func}" -> handler becomes "module.func"
        - legacy stream-ish: "{service}.{Class}.{method}" -> handler becomes "Class.method"

        Note: We intentionally do NOT try to guess where class vs module begins beyond
        the above, because legacy formats are ambiguous. We keep the remaining tail
        joined with '.' as handler.
        """
        if not method:
            raise ValueError("method must not be empty")

        if method.startswith(_V2_PREFIX):
            rest = method[len(_V2_PREFIX) :]
            service, sep, handler = rest.partition("/")
            if not sep or not service or not handler:
                raise ValueError(f"Invalid v2 method: {method!r}")
            return MethodName(service=service, handler=handler)

        parts = method.split(".")
        if len(parts) < 2:
            raise ValueError(f"Invalid legacy method: {method!r}")

        service = parts[0]
        handler = ".".join(parts[1:])
        return MethodName(service=service, handler=handler)

