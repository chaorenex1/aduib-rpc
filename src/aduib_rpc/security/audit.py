from __future__ import annotations

"""Audit logging utilities with structured JSON output."""

import json
import logging
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Mapping

__all__ = [
    "AuditEvent",
    "AuditLogger",
]


def _now_ms() -> int:
    return int(time.time() * 1000)


@dataclass(frozen=True, slots=True)
class AuditEvent:
    """Structured audit event payload."""

    action: str
    resource: str
    event_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    timestamp_ms: int = field(default_factory=_now_ms)
    subject_id: str | None = None
    subject_type: str | None = None
    status: str = "success"
    metadata: Mapping[str, Any] = field(default_factory=dict)
    request_id: str | None = None
    trace_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "event_id": self.event_id,
            "timestamp_ms": self.timestamp_ms,
            "action": self.action,
            "resource": self.resource,
            "subject_id": self.subject_id,
            "subject_type": self.subject_type,
            "status": self.status,
            "metadata": dict(self.metadata),
            "request_id": self.request_id,
            "trace_id": self.trace_id,
        }


class AuditLogger:
    """Logger emitting JSON-formatted audit events."""

    def __init__(self, logger: logging.Logger | None = None) -> None:
        self._logger = logger or logging.getLogger("aduib_rpc.audit")

    def log_event(self, event: AuditEvent) -> str:
        """Serialize and emit an audit event, returning the JSON payload."""

        payload = json.dumps(
            event.to_dict(),
            ensure_ascii=True,
            default=str,
            separators=(",", ":"),
        )
        self._logger.info(payload)
        return payload

    def log(
        self,
        action: str,
        resource: str,
        *,
        subject_id: str | None = None,
        subject_type: str | None = None,
        status: str = "success",
        metadata: Mapping[str, Any] | None = None,
        request_id: str | None = None,
        trace_id: str | None = None,
    ) -> AuditEvent:
        """Create and emit an audit event from arguments."""

        event = AuditEvent(
            action=action,
            resource=resource,
            subject_id=subject_id,
            subject_type=subject_type,
            status=status,
            metadata=metadata or {},
            request_id=request_id,
            trace_id=trace_id,
        )
        self.log_event(event)
        return event
