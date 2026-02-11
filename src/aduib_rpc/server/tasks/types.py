"""Task protocol entities for Aduib RPC Protocol v2.0.

This module provides the v2 protocol entities for task management,
matching the specification in docs/protocol_v2_specification.md.
"""

from __future__ import annotations

import time
import uuid
from enum import StrEnum
from typing import Any

from pydantic import BaseModel

from aduib_rpc.protocol.v2.qos import Priority


class TaskMethod(StrEnum):
    """RPC methods for task operations in the v2 protocol."""

    SUBMIT_TASK = "task/submit"
    CANCEL_TASK = "task/cancel"
    SUBSCRIBE_TASK = "task/subscribe"
    STATUS_TASK = "task/status"
    RESULT_TASK = "task/result"
    QUERY_TASK = "task/query"

    @classmethod
    def list(cls) -> list[str]:
        """List all task method names."""
        return [method.value for method in cls]


class TaskStatus(StrEnum):
    """Task status in the v2 protocol."""

    PENDING = "pending"
    SCHEDULED = "scheduled"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELED = "canceled"
    RETRYING = "retrying"

    @classmethod
    def from_proto(cls, value: Any) -> "TaskStatus":
        return cls._from_wire(value)

    @classmethod
    def from_thrift(cls, value: Any) -> "TaskStatus":
        return cls._from_wire(value)

    @classmethod
    def _from_wire(cls, value: Any) -> "TaskStatus":
        if isinstance(value, cls):
            return value
        if value is None:
            return cls.PENDING
        raw = getattr(value, "value", value)
        if isinstance(raw, str):
            key = raw.lower()
            if key == "pending":
                return cls.PENDING
            if key == "scheduled":
                return cls.SCHEDULED
            if key == "running":
                return cls.RUNNING
            if key == "succeeded":
                return cls.SUCCEEDED
            if key == "failed":
                return cls.FAILED
            if key == "canceled":
                return cls.CANCELED
            if key == "retrying":
                return cls.RETRYING
            try:
                raw = int(raw)
            except Exception:
                return cls.PENDING
        try:
            num = int(raw)
        except Exception:
            return cls.PENDING
        if num == 1:
            return cls.PENDING
        if num == 2:
            return cls.SCHEDULED
        if num == 3:
            return cls.RUNNING
        if num == 4:
            return cls.SUCCEEDED
        if num == 5:
            return cls.FAILED
        if num == 6:
            return cls.CANCELED
        if num == 7:
            return cls.RETRYING
        return cls.PENDING

    @classmethod
    def to_proto(cls, value: "TaskStatus | str | int | None") -> int:
        return cls._to_wire(value)

    @classmethod
    def to_thrift(cls, value: "TaskStatus | str | int | None") -> int:
        return cls._to_wire(value)

    @classmethod
    def _to_wire(cls, value: "TaskStatus | str | int | None") -> int:
        if value is None:
            return 0
        if isinstance(value, cls):
            if value == cls.PENDING:
                return 1
            if value == cls.SCHEDULED:
                return 2
            if value == cls.RUNNING:
                return 3
            if value == cls.SUCCEEDED:
                return 4
            if value == cls.FAILED:
                return 5
            if value == cls.CANCELED:
                return 6
            if value == cls.RETRYING:
                return 7
            return 0
        raw = getattr(value, "value", value)
        if isinstance(raw, str):
            key = raw.lower()
            if key == "pending":
                return 1
            if key == "scheduled":
                return 2
            if key == "running":
                return 3
            if key == "succeeded":
                return 4
            if key == "failed":
                return 5
            if key == "canceled":
                return 6
            if key == "retrying":
                return 7
            try:
                raw = int(raw)
            except Exception:
                return 0
        try:
            num = int(raw)
        except Exception:
            return 0
        if 0 <= num <= 7:
            return num
        return 0


class TaskProgress(BaseModel):
    """Progress information for a task.

    Attributes:
        current: Current progress value.
        total: Total progress value.
        message: Optional progress message.
        percentage: Optional percentage (0-100).
    """

    current: int
    total: int
    message: str | None = None
    percentage: float | None = None


class TaskRecord(BaseModel):
    """Task record matching the v2 protocol specification.

    Attributes:
        task_id: Unique task identifier.
        parent_task_id: Optional parent task ID.
        status: Current task status.
        priority: Task priority.
        created_at_ms: Creation timestamp (ms).
        scheduled_at_ms: Scheduled execution timestamp (ms).
        started_at_ms: Start timestamp (ms).
        completed_at_ms: Completion timestamp (ms).
        attempt: Current attempt number.
        max_attempts: Maximum retry attempts.
        next_retry_at_ms: Next retry timestamp (ms).
        result: Task result (on success).
        error: Error information (on failure).
        progress: Optional progress information.
        metadata: Optional metadata.
        tags: Optional tags.
    """

    task_id: str
    parent_task_id: str | None = None
    status: TaskStatus = TaskStatus.PENDING
    priority: Priority = Priority.NORMAL
    created_at_ms: int
    scheduled_at_ms: int | None = None
    started_at_ms: int | None = None
    completed_at_ms: int | None = None
    attempt: int = 1
    max_attempts: int = 3
    next_retry_at_ms: int | None = None
    result: Any | None = None
    error: Any | None = None
    progress: TaskProgress | None = None
    metadata: dict[str, Any] | None = None
    tags: list[str] | None = None

    @property
    def is_terminal(self) -> bool:
        """Check if the task is in a terminal state."""
        return self.status in {
            TaskStatus.SUCCEEDED,
            TaskStatus.FAILED,
            TaskStatus.CANCELED,
        }

    @property
    def is_active(self) -> bool:
        """Check if the task is still active."""
        return self.status in {
            TaskStatus.PENDING,
            TaskStatus.SCHEDULED,
            TaskStatus.RUNNING,
            TaskStatus.RETRYING,
        }

    @classmethod
    def create(
        cls,
        target_method: str,
        params: dict[str, Any] | None = None,
        priority: Priority = Priority.NORMAL,
        max_attempts: int = 3,
        timeout_ms: int | None = None,
        scheduled_at_ms: int | None = None,
        idempotency_key: str | None = None,
        metadata: dict[str, Any] | None = None,
        tags: list[str] | None = None,
        task_id: str | None = None,
        parent_task_id: str | None = None,
    ) -> "TaskRecord":
        """Create a new task record.

        Args:
            target_method: Target RPC method.
            params: Method parameters.
            priority: Task priority.
            max_attempts: Maximum retry attempts.
            timeout_ms: Timeout in milliseconds.
            scheduled_at_ms: Scheduled execution time.
            idempotency_key: Idempotency key for deduplication.
            metadata: Optional metadata.
            tags: Optional tags.
            task_id: Task ID (generated if not provided).
            parent_task_id: Parent task ID.

        Returns:
            A new TaskRecord.
        """
        now_ms = int(time.time() * 1000)
        task_metadata = {
            "target_method": target_method,
            "params": params or {},
            "timeout_ms": timeout_ms,
            "idempotency_key": idempotency_key,
        }
        if metadata:
            task_metadata.update(metadata)

        return cls(
            task_id=task_id or str(uuid.uuid4()),
            parent_task_id=parent_task_id,
            status=TaskStatus.PENDING,
            priority=priority,
            created_at_ms=now_ms,
            scheduled_at_ms=scheduled_at_ms,
            max_attempts=max_attempts,
            attempt=1,
            metadata=task_metadata,
            tags=tags,
        )


class TaskEventType(StrEnum):
    STARTED = "STARTED"
    PROCESSING = "PROCESSING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class TaskEvent(BaseModel):
    """Task event for subscriptions.

    Attributes:
        event: Event type ("started" | "progress" | "completed" | "failed").
        task: The task record.
        timestamp_ms: Event timestamp (ms).
    """

    event: str
    task: TaskRecord
    timestamp_ms: int


# Request/Response types for task operations
class TaskSubmitRequest(BaseModel):
    """Request to submit a new task."""

    target_method: str
    params: dict[str, Any] | None = None
    priority: Priority = (Priority.NORMAL,)


class TaskSubmitResponse(BaseModel):
    """Response for task submission."""

    task_id: str
    status: TaskStatus
    created_at_ms: int


class TaskQueryRequest(BaseModel):
    """Request to query a task."""

    task_id: str


class TaskQueryResponse(BaseModel):
    """Response for task query."""

    task: TaskRecord


class TaskCancelRequest(BaseModel):
    """Request to cancel a task."""

    task_id: str
    reason: str | None = None


class TaskCancelResponse(BaseModel):
    """Response for task cancellation."""

    task_id: str
    status: TaskStatus
    canceled: bool


class TaskSubscribeRequest(BaseModel):
    """Request to subscribe to task events."""

    task_id: str
    events: list[str] | None = None
