"""Server-side async task support (long-running jobs).

This module provides a transport-agnostic task manager that can be used by
request handlers to run long-running work in the background and allow clients
to poll or subscribe to progress/results.
"""

from __future__ import annotations

from aduib_rpc.server.tasks.distributed import (
    DistributedTaskManager,
    RedisTaskStore,
    TaskPriority,
    TaskStore,
)
from aduib_rpc.server.tasks.task_manager import (
    InMemoryTaskManager,
    TaskEvent,
    TaskNotFoundError,
    TaskRecord,
    TaskStatus,
)

__all__ = [
    "InMemoryTaskManager",
    "TaskEvent",
    "TaskNotFoundError",
    "TaskRecord",
    "TaskStatus",
    "DistributedTaskManager",
    "RedisTaskStore",
    "TaskPriority",
    "TaskStore",
]

