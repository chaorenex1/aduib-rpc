from __future__ import annotations

import asyncio
import time
import uuid
from collections import defaultdict
from dataclasses import dataclass
from enum import Enum
from typing import Any, Awaitable, Callable, Dict

from aduib_rpc.types import AduibRpcError


class TaskStatus(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELED = "canceled"
    EXPIRED = "expired"


@dataclass
class TaskRecord:
    task_id: str
    status: TaskStatus
    created_at_ms: int
    updated_at_ms: int
    value: Any | None = None
    error: AduibRpcError | None = None


@dataclass
class TaskEvent:
    event: str  # snapshot|update|completed
    task: TaskRecord


class TaskNotFoundError(KeyError):
    pass


class InMemoryTaskManager:
    """Simple in-memory task manager.

    Notes:
      - Single-process only.
      - Stores results in memory with optional TTL.
      - Supports subscription via asyncio.Queue.
    """

    def __init__(self, *, default_ttl_seconds: int | None = 3600, max_tasks: int = 10_000):
        self._default_ttl_seconds = default_ttl_seconds
        self._max_tasks = max_tasks
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
                status=TaskStatus.QUEUED,
                created_at_ms=now,
                updated_at_ms=now,
            )
            self._tasks[tid] = rec
            self._expiry[tid] = expires_at

        self._emit(tid, TaskEvent(event="snapshot", task=rec))

        async def runner() -> None:
            await self._set_status(tid, TaskStatus.RUNNING)
            try:
                value = await coro_factory()
                await self._set_result(tid, value=value)
            except asyncio.CancelledError as e:
                await self._set_error(
                    tid,
                    AduibRpcError(code=499, message="Task cancelled", data=str(e) if str(e) else None),
                    status=TaskStatus.CANCELED,
                )
                raise
            except Exception as e:  # noqa: BLE001
                await self._set_error(
                    tid,
                    AduibRpcError(code=500, message="Task failed", data=str(e)),
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
        q.put_nowait(TaskEvent(event="snapshot", task=rec))

        # If the task has already completed before we subscribed, also enqueue a
        # terminal event so consumers can reliably observe completion.
        if rec.status in {TaskStatus.SUCCEEDED, TaskStatus.FAILED, TaskStatus.CANCELED, TaskStatus.EXPIRED}:
            q.put_nowait(TaskEvent(event="completed", task=rec))
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
            rec.updated_at_ms = now
        self._emit(task_id, TaskEvent(event="update", task=rec))

    async def _set_result(self, task_id: str, *, value: Any) -> None:
        now = self._now_ms()
        async with self._lock:
            rec = self._tasks.get(task_id)
            if rec is None:
                return
            rec.status = TaskStatus.SUCCEEDED
            rec.value = value
            rec.error = None
            rec.updated_at_ms = now
        self._emit(task_id, TaskEvent(event="completed", task=rec))

    async def _set_error(self, task_id: str, err: AduibRpcError, *, status: TaskStatus) -> None:
        now = self._now_ms()
        async with self._lock:
            rec = self._tasks.get(task_id)
            if rec is None:
                return
            rec.status = status
            rec.error = err
            rec.value = None
            rec.updated_at_ms = now
        self._emit(task_id, TaskEvent(event="completed", task=rec))

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
            finished.sort(key=lambda r: r.updated_at_ms)
            while len(self._tasks) > int(self._max_tasks * 0.9) and finished:
                self._delete_locked(finished.pop(0).task_id)
