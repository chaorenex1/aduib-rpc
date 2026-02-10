from __future__ import annotations

import asyncio
import time
import uuid
from abc import ABC, abstractmethod
from collections import defaultdict
from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Dict

from aduib_rpc.protocol.v2.errors import ERROR_CODE_NAMES, ErrorCode
from aduib_rpc.protocol.v2.types import RpcError
from aduib_rpc.server.tasks import TaskRecord, TaskEvent, TaskStatus
from aduib_rpc.server.tasks.provider import task_manager_provider


@dataclass
class TaskManagerConfig:
    default_ttl_seconds: int | None = 3600
    max_tasks: int = 10_000


class TaskNotFoundError(KeyError):
    pass

class TaskManager(ABC):

    @abstractmethod
    async def submit(
            self,
            coro_factory: Callable[[], Awaitable[Any]],
            *,
            ttl_seconds: int | None = None,
            task_id: str | None = None,
    ) -> TaskRecord:
        """Submit a coroutine factory to run in background."""

    @abstractmethod
    async def get(self, task_id: str) -> TaskRecord:
        """Get task record by ID."""

    @abstractmethod
    async def subscribe(self, task_id: str) -> asyncio.Queue[TaskEvent]:
        """Subscribe to task events. Returns an asyncio.Queue of TaskEvent."""

    @abstractmethod
    async def unsubscribe(self, task_id: str, q: asyncio.Queue[TaskEvent]) -> None:
        """Unsubscribe from task events."""


@task_manager_provider(name="in-memory")
class InMemoryTaskManager(TaskManager):
    """Simple in-memory task manager.

    Notes:
      - Single-process only.
      - Stores results in memory with optional TTL.
      - Supports subscription via asyncio.Queue.
    """

    def __init__(self, *, config: TaskManagerConfig | None = None) -> None:
        cfg = config
        self._default_ttl_seconds = cfg.default_ttl_seconds if cfg else 3600
        self._max_tasks = cfg.max_tasks if cfg else 10_000
        self._tasks: Dict[str, TaskRecord] = {}
        self._expiry: Dict[str, int | None] = {}  # task_id -> epoch_ms
        self._subs: Dict[str, set[asyncio.Queue[TaskEvent]]] = defaultdict(set)
        self._lock = asyncio.Lock()

    def _now_ms(self) -> int:
        return int(time.time() * 1000)

    async def submit(
        self,
        coro_factory: Callable[[], Awaitable[Any]],
        *,
        ttl_seconds: int | None = None,
        task_id: str | None = None,
    ) -> TaskRecord:
        """Submit a coroutine factory to run in background."""
        tid = task_id or str(uuid.uuid4())
        now = self._now_ms()
        ttl = self._default_ttl_seconds if ttl_seconds is None else ttl_seconds
        expires_at = None if ttl is None else now + int(ttl * 1000)

        async with self._lock:
            self._gc_locked(now)
            if tid in self._tasks:
                return self._tasks[tid]
            if len(self._tasks) >= self._max_tasks:
                self._gc_locked(now, aggressive=True)
                if len(self._tasks) >= self._max_tasks:
                    # drop the oldest task
                    oldest = min(self._tasks.values(), key=lambda r: r.created_at_ms)
                    self._delete_locked(oldest.task_id)

            rec = TaskRecord(
                task_id=tid,
                status=TaskStatus.PENDING,
                created_at_ms=now,
            )
            self._tasks[tid] = rec
            self._expiry[tid] = expires_at

        self._emit(tid, self._event_for_task(rec))

        async def runner() -> None:
            await self._set_status(tid, TaskStatus.RUNNING)
            try:
                value = await coro_factory()
                await self._set_result(tid, result=value)
            except asyncio.CancelledError as e:
                await self._set_error(
                    tid,
                    RpcError(
                        code=499,
                        name="CANCELED",
                        message="Task cancelled",
                        details=[{"type": "aduib.rpc/task", "reason": str(e) if str(e) else "cancelled"}],
                    ),
                    status=TaskStatus.CANCELED,
                )
                raise
            except Exception as e:  # noqa: BLE001
                await self._set_error(
                    tid,
                    RpcError(
                        code=int(ErrorCode.INTERNAL_ERROR),
                        name=ERROR_CODE_NAMES.get(int(ErrorCode.INTERNAL_ERROR), "UNKNOWN"),
                        message="Task failed",
                        details=[{"type": "aduib.rpc/task", "reason": str(e)}],
                    ),
                    status=TaskStatus.FAILED,
                )

        asyncio.create_task(runner())
        return rec

    async def get(self, task_id: str) -> TaskRecord:
        now = self._now_ms()
        async with self._lock:
            self._gc_locked(now)
            rec = self._tasks.get(task_id)
            if rec is None:
                raise TaskNotFoundError(task_id)
            return rec

    async def subscribe(self, task_id: str) -> asyncio.Queue[TaskEvent]:
        q: asyncio.Queue[TaskEvent] = asyncio.Queue()
        # ensure task exists
        rec = await self.get(task_id)
        self._subs[task_id].add(q)
        q.put_nowait(self._event_for_task(rec))
        return q

    async def unsubscribe(self, task_id: str, q: asyncio.Queue[TaskEvent]) -> None:
        async with self._lock:
            self._subs[task_id].discard(q)
            if not self._subs[task_id]:
                self._subs.pop(task_id, None)

    async def _set_status(self, task_id: str, status: TaskStatus) -> None:
        now = self._now_ms()
        async with self._lock:
            rec = self._tasks.get(task_id)
            if rec is None:
                return
            rec.status = status
            if status == TaskStatus.RUNNING and rec.started_at_ms is None:
                rec.started_at_ms = now
        self._emit(task_id, self._event_for_task(rec))

    async def _set_result(self, task_id: str, *, result: Any) -> None:
        now = self._now_ms()
        async with self._lock:
            rec = self._tasks.get(task_id)
            if rec is None:
                return
            rec.status = TaskStatus.SUCCEEDED
            rec.result = result
            rec.error = None
            rec.completed_at_ms = now
        self._emit(task_id, self._event_for_task(rec))

    async def _set_error(self, task_id: str, err: RpcError, *, status: TaskStatus) -> None:
        now = self._now_ms()
        async with self._lock:
            rec = self._tasks.get(task_id)
            if rec is None:
                return
            rec.status = status
            rec.error = err
            rec.result = None
            if rec.is_terminal:
                rec.completed_at_ms = now
        self._emit(task_id, self._event_for_task(rec))

    def _emit(self, task_id: str, ev: TaskEvent) -> None:
        for q in list(self._subs.get(task_id, ())):
            try:
                q.put_nowait(ev)
            except Exception:
                # drop broken subscribers
                self._subs[task_id].discard(q)

    def _is_expired_locked(self, task_id: str, now_ms: int) -> bool:
        expires_at = self._expiry.get(task_id)
        return expires_at is not None and expires_at <= now_ms

    def _delete_locked(self, task_id: str) -> None:
        self._tasks.pop(task_id, None)
        self._expiry.pop(task_id, None)
        self._subs.pop(task_id, None)

    def _gc_locked(self, now_ms: int, *, aggressive: bool = False) -> None:
        # normal: only delete expired; aggressive: delete expired + finished old tasks
        expired = [tid for tid in self._tasks.keys() if self._is_expired_locked(tid, now_ms)]
        for tid in expired:
            self._delete_locked(tid)

        if aggressive:
            # delete finished tasks oldest-first until under cap
            finished = [
                r for r in self._tasks.values() if r.status in {TaskStatus.SUCCEEDED, TaskStatus.FAILED, TaskStatus.CANCELED}
            ]
            finished.sort(key=lambda r: r.completed_at_ms or r.created_at_ms)
            while len(self._tasks) > int(self._max_tasks * 0.9) and finished:
                self._delete_locked(finished.pop(0).task_id)

    def _event_for_task(self, record: TaskRecord) -> TaskEvent:
        if record.status == TaskStatus.RUNNING:
            event = "started"
        elif record.status == TaskStatus.SUCCEEDED:
            event = "completed"
        elif record.status in {TaskStatus.FAILED, TaskStatus.CANCELED}:
            event = "failed"
        else:
            event = "progress"
        return TaskEvent(event=event, task=record, timestamp_ms=self._now_ms())
