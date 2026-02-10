"""Server-side async task support (long-running jobs).

This module provides task managers plus the v2 task protocol entities used by
handlers and transports.
"""

from __future__ import annotations

# v2 protocol types
from aduib_rpc.server.tasks.types import (
    TaskMethod,
    TaskCancelRequest,
    TaskCancelResponse,
    TaskEvent,
    TaskProgress,
    TaskQueryRequest,
    TaskQueryResponse,
    TaskRecord,
    TaskStatus,
    TaskSubmitRequest,
    TaskSubmitResponse,
    TaskSubscribeRequest,
)

from aduib_rpc.server.tasks.task_manager import (
    InMemoryTaskManager,
    TaskNotFoundError,
)

__all__ = [
    "TaskMethod",
    "TaskEvent",
    "TaskRecord",
    "TaskStatus",
    "TaskProgress",
    "TaskCancelRequest",
    "TaskCancelResponse",
    "TaskQueryRequest",
    "TaskQueryResponse",
    "TaskSubmitRequest",
    "TaskSubmitResponse",
    "TaskSubscribeRequest",
    "InMemoryTaskManager",
    "TaskNotFoundError",
]
