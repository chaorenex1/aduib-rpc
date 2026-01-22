from __future__ import annotations

import asyncio
import inspect
import itertools
import json
import time
import uuid
from abc import ABC, abstractmethod
from enum import IntEnum
from typing import Any, Callable

from aduib_rpc.types import AduibRpcError

from .task_manager import TaskNotFoundError, TaskRecord, TaskStatus

__all__ = [
    "TaskPriority",
    "TaskStore",
    "RedisTaskStore",
    "DistributedTaskManager",
    "TaskStatus",
    "TaskRecord",
    "TaskNotFoundError",
]


class TaskPriority(IntEnum):
    LOW = 0
    NORMAL = 1
    HIGH = 2
    CRITICAL = 3


class TaskStore(ABC):
    @abstractmethod
    async def save(self, record: TaskRecord) -> None:
        pass

    @abstractmethod
    async def get(self, task_id: str) -> TaskRecord | None:
        pass

    @abstractmethod
    async def update(self, task_id: str, **updates) -> TaskRecord | None:
        pass

    @abstractmethod
    async def list_by_status(self, status: TaskStatus, limit: int = 100) -> list[TaskRecord]:
        pass

    @abstractmethod
    async def delete_expired(self, ttl_seconds: int) -> int:
        pass


class RedisTaskStore(TaskStore):
    def __init__(self, redis_url: str, key_prefix: str = "aduib:task:") -> None:
        self._redis_url = redis_url
        self._key_prefix = key_prefix
        self._redis = None

    async def _get_redis(self):
        if self._redis is None:
            import redis.asyncio as redis

            self._redis = redis.from_url(self._redis_url)
        return self._redis

    def _task_key(self, task_id: str) -> str:
        return f"{self._key_prefix}{task_id}"

    def _status_key(self, status: str) -> str:
        return f"{self._key_prefix}status:{status}"

    def _now_ms(self) -> int:
        return int(time.time() * 1000)

    def _decode(self, value: Any) -> Any:
        if isinstance(value, (bytes, bytearray)):
            return value.decode()
        return value

    def _serialize_value(self, value: Any) -> str:
        return json.dumps(value, ensure_ascii=True, default=str)

    def _serialize_error(self, error: Any) -> str:
        if isinstance(error, AduibRpcError):
            payload = error.model_dump()
        elif isinstance(error, dict):
            payload = error
        else:
            payload = {"message": str(error), "type": type(error).__name__}
        return self._serialize_value(payload)

    def _deserialize_error(self, raw: str | None) -> AduibRpcError | dict | None:
        if not raw:
            return None
        payload = json.loads(raw)
        if isinstance(payload, dict) and "code" in payload and "message" in payload:
            return AduibRpcError(**payload)
        return payload

    def _serialize_record(self, record: TaskRecord) -> dict[str, Any]:
        data: dict[str, Any] = {
            "task_id": record.task_id,
            "status": record.status.value,
            "created_at_ms": record.created_at_ms,
            "updated_at_ms": record.updated_at_ms,
            "priority": getattr(record, "priority", TaskPriority.NORMAL),
            "started_at_ms": getattr(record, "started_at_ms", None),
            "completed_at_ms": getattr(record, "completed_at_ms", None),
            "retry_count": getattr(record, "retry_count", 0),
            "max_retries": getattr(record, "max_retries", 0),
            "metadata": self._serialize_value(getattr(record, "metadata", {}) or {}),
        }
        if record.value is not None:
            data["value"] = self._serialize_value(record.value)
        if record.error is not None:
            data["error"] = self._serialize_error(record.error)
        return {key: value for key, value in data.items() if value is not None}

    def _deserialize(self, raw: dict[Any, Any]) -> TaskRecord:
        data = {self._decode(key): self._decode(value) for key, value in raw.items()}
        status_value = data.get("status")
        status = TaskStatus(status_value) if status_value else TaskStatus.QUEUED
        record = TaskRecord(
            task_id=str(data.get("task_id", "")),
            status=status,
            created_at_ms=int(data.get("created_at_ms", 0)),
            updated_at_ms=int(data.get("updated_at_ms", 0)),
            priority=int(data.get("priority", TaskPriority.NORMAL)),
            started_at_ms=int(data["started_at_ms"]) if data.get("started_at_ms") else None,
            completed_at_ms=int(data["completed_at_ms"]) if data.get("completed_at_ms") else None,
            retry_count=int(data.get("retry_count", 0)),
            max_retries=int(data.get("max_retries", 0)),
            metadata=json.loads(data.get("metadata", "{}") or "{}"),
            value=json.loads(data["value"]) if data.get("value") else None,
            error=self._deserialize_error(data.get("error")),
        )
        return record

    async def save(self, record: TaskRecord) -> None:
        redis = await self._get_redis()
        key = self._task_key(record.task_id)
        data = self._serialize_record(record)
        await redis.hset(key, mapping=data)
        await redis.sadd(self._status_key(record.status.value), record.task_id)

    async def get(self, task_id: str) -> TaskRecord | None:
        redis = await self._get_redis()
        data = await redis.hgetall(self._task_key(task_id))
        if not data:
            return None
        return self._deserialize(data)

    async def update(self, task_id: str, **updates) -> TaskRecord | None:
        redis = await self._get_redis()
        key = self._task_key(task_id)

        old_status = await redis.hget(key, "status")
        old_status = self._decode(old_status) if old_status else None

        updates = dict(updates)
        updates.setdefault("updated_at_ms", self._now_ms())

        mapping: dict[str, Any] = {}
        delete_fields: list[str] = []

        for field_name, value in updates.items():
            if value is None:
                delete_fields.append(field_name)
                continue
            if field_name == "status" and isinstance(value, TaskStatus):
                value = value.value
            if field_name == "priority" and isinstance(value, TaskPriority):
                value = int(value)
            if field_name == "error":
                value = self._serialize_error(value)
            elif field_name in {"value", "metadata"}:
                value = self._serialize_value(value)
            mapping[field_name] = value

        if "status" in mapping:
            new_status = mapping["status"]
            if old_status:
                await redis.srem(self._status_key(old_status), task_id)
            await redis.sadd(self._status_key(new_status), task_id)

        if mapping:
            await redis.hset(key, mapping=mapping)
        if delete_fields:
            await redis.hdel(key, *delete_fields)
        return await self.get(task_id)

    async def list_by_status(self, status: TaskStatus, limit: int = 100) -> list[TaskRecord]:
        redis = await self._get_redis()
        task_ids = await redis.smembers(self._status_key(status.value))
        records: list[TaskRecord] = []
        for raw_task_id in list(task_ids)[:limit]:
            task_id = self._decode(raw_task_id)
            record = await self.get(task_id)
            if record:
                records.append(record)
        return records

    async def delete_expired(self, ttl_seconds: int) -> int:
        if ttl_seconds <= 0:
            return 0
        redis = await self._get_redis()
        cutoff = self._now_ms() - int(ttl_seconds * 1000)
        removed = 0

        terminal_statuses = (
            TaskStatus.SUCCEEDED,
            TaskStatus.FAILED,
            TaskStatus.CANCELED,
            TaskStatus.EXPIRED,
        )

        for status in terminal_statuses:
            task_ids = await redis.smembers(self._status_key(status.value))
            for raw_task_id in task_ids:
                task_id = self._decode(raw_task_id)
                record = await self.get(task_id)
                if record is None:
                    await redis.srem(self._status_key(status.value), task_id)
                    continue
                completed_at = getattr(record, "completed_at_ms", None)
                if completed_at is None or completed_at >= cutoff:
                    continue
                await redis.delete(self._task_key(task_id))
                await redis.srem(self._status_key(record.status.value), task_id)
                removed += 1

        return removed


class DistributedTaskManager:
    def __init__(self, store: TaskStore) -> None:
        self.store = store
        self._executor_pool: asyncio.PriorityQueue[
            tuple[int, int, TaskRecord, Callable[..., Any]]
        ] = asyncio.PriorityQueue(maxsize=100)
        self._enqueue_counter = itertools.count()
        self._subscribers: dict[str, set[asyncio.Queue]] = {}
        self._worker_tasks: list[asyncio.Task] = []
        self._running = False

    async def start(self, worker_count: int = 4) -> None:
        self._running = True
        for i in range(worker_count):
            task = asyncio.create_task(self._worker_loop(f"worker-{i}"))
            self._worker_tasks.append(task)

    async def stop(self) -> None:
        self._running = False
        for task in self._worker_tasks:
            task.cancel()
        if self._worker_tasks:
            await asyncio.gather(*self._worker_tasks, return_exceptions=True)
        self._worker_tasks.clear()

    async def submit(
        self,
        func: Callable[..., Any],
        *,
        priority: TaskPriority,
        max_retries: int,
        ttl_seconds: int | None,
        metadata: dict | None,
    ) -> TaskRecord:
        task_id = str(uuid.uuid4())
        now_ms = int(time.time() * 1000)
        record = TaskRecord(
            task_id=task_id,
            status=TaskStatus.QUEUED,
            created_at_ms=now_ms,
            updated_at_ms=now_ms,
            priority=int(priority),
            max_retries=max_retries,
            metadata=metadata or {},
        )
        if ttl_seconds is not None:
            record.metadata["ttl_seconds"] = ttl_seconds
            record.metadata["expires_at_ms"] = now_ms + int(ttl_seconds * 1000)
        await self.store.save(record)
        await self._enqueue(record, func)
        return record

    async def get(self, task_id: str) -> TaskRecord:
        record = await self.store.get(task_id)
        if not record:
            raise TaskNotFoundError(task_id)
        return record

    async def cancel(self, task_id: str) -> TaskRecord:
        now_ms = int(time.time() * 1000)
        record = await self.store.update(
            task_id,
            status=TaskStatus.CANCELED,
            completed_at_ms=now_ms,
        )
        if not record:
            raise TaskNotFoundError(task_id)
        await self._notify_subscribers(task_id, "canceled")
        return record

    async def subscribe(self, task_id: str) -> asyncio.Queue:
        record = await self.store.get(task_id)
        if not record:
            raise TaskNotFoundError(task_id)
        queue: asyncio.Queue = asyncio.Queue()
        self._subscribers.setdefault(task_id, set()).add(queue)
        await queue.put({"event": "snapshot", "task": record})
        return queue

    async def _enqueue(self, record: TaskRecord, func: Callable[..., Any]) -> None:
        priority_value = getattr(record, "priority", TaskPriority.NORMAL)
        if isinstance(priority_value, TaskPriority):
            priority_value = int(priority_value)
        priority_key = -int(priority_value)
        sequence = next(self._enqueue_counter)
        await self._executor_pool.put((priority_key, sequence, record, func))

    async def _worker_loop(self, worker_name: str) -> None:
        while self._running:
            try:
                _, _, record, func = await asyncio.wait_for(
                    self._executor_pool.get(),
                    timeout=1.0,
                )
                await self._execute_task(record, func)
            except asyncio.TimeoutError:
                continue
            except asyncio.CancelledError:
                break
            except Exception:
                continue

    async def _execute_task(self, record: TaskRecord, func: Callable) -> None:
        current = await self.store.get(record.task_id)
        if current and current.status == TaskStatus.CANCELED:
            return

        await self.store.update(
            record.task_id,
            status=TaskStatus.RUNNING,
            started_at_ms=int(time.time() * 1000),
        )
        await self._notify_subscribers(record.task_id, "started")

        try:
            result = func()
            if inspect.isawaitable(result):
                result = await result
            await self.store.update(
                record.task_id,
                status=TaskStatus.SUCCEEDED,
                value=result,
                completed_at_ms=int(time.time() * 1000),
            )
            await self._notify_subscribers(record.task_id, "completed")
        except asyncio.CancelledError as exc:
            await self.store.update(
                record.task_id,
                status=TaskStatus.CANCELED,
                error=self._exception_to_error(exc),
                completed_at_ms=int(time.time() * 1000),
            )
            await self._notify_subscribers(record.task_id, "canceled")
            raise
        except Exception as exc:
            retry_count = getattr(record, "retry_count", 0)
            max_retries = getattr(record, "max_retries", 0)
            if retry_count < max_retries:
                retry_count += 1
                updated = await self.store.update(
                    record.task_id,
                    status=TaskStatus.RETRYING,
                    retry_count=retry_count,
                    error=self._exception_to_error(exc),
                )
                if updated:
                    record = updated
                await self._notify_subscribers(record.task_id, "retrying")
                await self._enqueue(record, func)
                return

            await self.store.update(
                record.task_id,
                status=TaskStatus.FAILED,
                error=self._exception_to_error(exc),
                completed_at_ms=int(time.time() * 1000),
            )
            await self._notify_subscribers(record.task_id, "failed")

    async def _notify_subscribers(self, task_id: str, event: str) -> None:
        if task_id not in self._subscribers:
            return
        record = await self.store.get(task_id)
        if not record:
            return
        for queue in list(self._subscribers.get(task_id, set())):
            await queue.put({"event": event, "task": record})

    def _exception_to_error(self, exc: BaseException) -> AduibRpcError:
        return AduibRpcError(
            code=500,
            message="Task failed",
            data={"type": type(exc).__name__, "message": str(exc)},
        )
