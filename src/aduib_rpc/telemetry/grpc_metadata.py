from __future__ import annotations

from collections.abc import Sequence
from typing import Any

try:
    import grpc
except Exception:  # pragma: no cover
    grpc = None  # type: ignore


def _otel_inject_to_grpc_metadata(metadata: Sequence[tuple[str, str]] | None) -> list[tuple[str, str]]:
    """Inject current trace context into gRPC metadata.

    Best-effort:
    - If OpenTelemetry isn't installed, returns metadata unchanged.
    """

    md = list(metadata or [])

    try:
        from opentelemetry.propagate import inject
    except Exception:
        return md

    carrier: dict[str, str] = {}
    inject(carrier)
    for k, v in carrier.items():
        md.append((str(k).lower(), str(v)))
    return md


def _otel_extract_from_grpc_metadata(metadata: Sequence[tuple[str, str]] | None):
    """Extract remote trace context from gRPC metadata (best-effort)."""

    try:
        from opentelemetry.propagate import extract
    except Exception:
        return None

    carrier = {str(k).lower(): str(v) for (k, v) in (metadata or [])}
    return extract(carrier)


def _make_client_call_details(client_call_details: Any, metadata: Sequence[tuple[str, str]] | None):
    """Create a concrete grpc.aio.ClientCallDetails.

    grpc.aio.ClientCallDetails is an interface; different grpcio versions expose
    different helper types. This function creates a minimal compatible object.
    """

    if grpc is None:
        raise RuntimeError("grpc is not installed")

    class _ClientCallDetails(grpc.aio.ClientCallDetails):
        def __init__(self, base, md):
            self.method = base.method
            self.timeout = getattr(base, "timeout", None)
            self.metadata = md
            self.credentials = getattr(base, "credentials", None)
            self.wait_for_ready = getattr(base, "wait_for_ready", None)
            self.compression = getattr(base, "compression", None)

    return _ClientCallDetails(client_call_details, metadata)


def inject_otel_to_grpc_metadata(metadata: Sequence[tuple[str, str]] | None) -> list[tuple[str, str]]:
    """Public helper: inject OpenTelemetry context into a gRPC metadata list."""
    return _otel_inject_to_grpc_metadata(metadata)
