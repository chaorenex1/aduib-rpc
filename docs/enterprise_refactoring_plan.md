# Aduib RPC 企业级重构方案

> **目标**：将现有 RPC 框架升级为**生产就绪、高可用、可扩展**的企业级解决方案，满足大规模分布式系统的需求。

## 执行摘要

| 维度 | 现状评估 | 目标状态 | 优先级 |
|------|----------|----------|--------|
| 可靠性 | 基础重试/超时 | 熔断器、限流、优雅降级 | **P0** |
| 可观测性 | 可选 OTEL | 全链路追踪 + 指标 + 日志标准化 | **P0** |
| 安全性 | 基础认证拦截器 | mTLS + RBAC + 审计日志 | **P1** |
| 可扩展性 | 单实例注册 | 多注册中心 + 健康检查 + 动态配置 | **P1** |
| 开发体验 | 手动配置 | 自动配置 + 代码生成 + IDE 支持 | **P2** |

---

## 第一部分：架构问题诊断

### 1.1 关键问题清单

#### 🔴 严重 (P0) - 影响生产稳定性

| ID | 问题 | 位置 | 影响 |
|----|------|------|------|
| P0-1 | **全局单例 Runtime** | `runtime.py:51-63` | 多租户隔离困难，测试污染风险 |
| P0-2 | **缺乏熔断器** | 全局 | 级联故障风险 |
| P0-3 | **内存任务管理器** | `task_manager.py` | 无持久化，重启丢失 |
| P0-4 | **异常处理不统一** | 多处 `except Exception` | 调试困难，错误恢复不可靠 |
| P0-5 | **服务发现无健康检查** | `service_registry.py` | 可能路由到不健康实例 |

#### 🟡 中等 (P1) - 影响扩展性和维护性

| ID | 问题 | 位置 | 影响 |
|----|------|------|------|
| P1-1 | **硬编码协议版本** | `types.py:26` | 协议升级困难 |
| P1-2 | **缺乏配置中心集成** | - | 动态配置能力缺失 |
| P1-3 | **日志结构化不完整** | 多处 | 日志分析困难 |
| P1-4 | **缺乏 API 版本管理** | `methods.py` | 向后兼容性风险 |
| P1-5 | **Thrift 客户端未实现** | `client/transports/` | 协议支持不对称 |

#### 🟢 低优先级 (P2) - 影响开发体验

| ID | 问题 | 位置 | 影响 |
|----|------|------|------|
| P2-1 | **缺乏 CLI 工具** | - | 调试效率低 |
| P2-2 | **文档不完整** | `docs/` | 上手成本高 |
| P2-3 | **缺乏代码生成器** | - | 样板代码多 |

---

## 第二部分：重构方案详细设计

### 2.1 P0-1: Runtime 依赖注入重构

**现状问题**：
```python
# runtime.py:51-63 - 全局单例模式
_global_runtime: RpcRuntime | None = None

def get_runtime() -> RpcRuntime:
    global _global_runtime
    if _global_runtime is None:
        _global_runtime = RpcRuntime()
    return _global_runtime
```

**重构方案**：引入 Context-based Runtime 管理

```python
# 新文件: src/aduib_rpc/core/context.py
from __future__ import annotations
from contextvars import ContextVar
from dataclasses import dataclass, field
from typing import Any, TypeVar, Generic

T = TypeVar("T")

@dataclass(frozen=True)
class RuntimeConfig:
    """不可变运行时配置"""
    tenant_id: str = "default"
    environment: str = "production"
    max_connections: int = 100
    request_timeout_ms: int = 30000
    enable_telemetry: bool = True

@dataclass
class ScopedRuntime:
    """作用域隔离的运行时"""
    config: RuntimeConfig
    service_funcs: dict[str, Any] = field(default_factory=dict)
    client_funcs: dict[str, Any] = field(default_factory=dict)
    interceptors: list[Any] = field(default_factory=list)
    _parent: ScopedRuntime | None = field(default=None, repr=False)

    def child(self, **overrides) -> ScopedRuntime:
        """创建子作用域，继承父配置"""
        new_config = RuntimeConfig(
            **{**self.config.__dict__, **overrides}
        )
        return ScopedRuntime(
            config=new_config,
            service_funcs=self.service_funcs.copy(),
            client_funcs=self.client_funcs.copy(),
            interceptors=self.interceptors.copy(),
            _parent=self,
        )

# Context Variable for async-safe runtime access
_runtime_ctx: ContextVar[ScopedRuntime] = ContextVar("runtime")

def get_current_runtime() -> ScopedRuntime:
    """获取当前上下文的 Runtime"""
    try:
        return _runtime_ctx.get()
    except LookupError:
        # 返回默认 runtime 以保持向后兼容
        default = ScopedRuntime(config=RuntimeConfig())
        _runtime_ctx.set(default)
        return default

def with_runtime(runtime: ScopedRuntime):
    """上下文管理器：在作用域内使用指定 runtime"""
    import contextlib

    @contextlib.contextmanager
    def _context():
        token = _runtime_ctx.set(runtime)
        try:
            yield runtime
        finally:
            _runtime_ctx.reset(token)

    return _context()
```

**迁移策略**：
1. 保持 `get_runtime()` 向后兼容，内部委托到新实现
2. 新增 `@with_tenant(tenant_id)` 装饰器支持多租户
3. 逐步迁移现有代码使用 `get_current_runtime()`

---

### 2.2 P0-2: 熔断器与弹性模式

**新增文件**: `src/aduib_rpc/resilience/`

```
src/aduib_rpc/resilience/
├── __init__.py
├── circuit_breaker.py      # 熔断器实现
├── rate_limiter.py         # 限流器
├── retry_policy.py         # 增强重试策略
├── bulkhead.py             # 舱壁隔离
└── fallback.py             # 降级策略
```

**熔断器设计**：

```python
# src/aduib_rpc/resilience/circuit_breaker.py
from __future__ import annotations
import asyncio
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Callable, TypeVar, Generic

T = TypeVar("T")

class CircuitState(Enum):
    CLOSED = "closed"       # 正常状态
    OPEN = "open"           # 熔断状态
    HALF_OPEN = "half_open" # 探测状态

@dataclass
class CircuitBreakerConfig:
    """熔断器配置"""
    failure_threshold: int = 5          # 失败阈值
    success_threshold: int = 3          # 恢复阈值
    timeout_seconds: float = 30.0       # 熔断超时
    half_open_max_calls: int = 3        # 半开状态最大调用数
    excluded_exceptions: tuple = ()     # 不计入失败的异常类型

@dataclass
class CircuitBreaker:
    """熔断器实现"""
    name: str
    config: CircuitBreakerConfig = field(default_factory=CircuitBreakerConfig)
    _state: CircuitState = field(default=CircuitState.CLOSED, init=False)
    _failure_count: int = field(default=0, init=False)
    _success_count: int = field(default=0, init=False)
    _last_failure_time: float = field(default=0.0, init=False)
    _half_open_calls: int = field(default=0, init=False)
    _lock: asyncio.Lock = field(default_factory=asyncio.Lock, init=False)

    @property
    def state(self) -> CircuitState:
        return self._state

    async def call(self, func: Callable[..., T], *args, **kwargs) -> T:
        """通过熔断器执行调用"""
        async with self._lock:
            await self._check_state_transition()

            if self._state == CircuitState.OPEN:
                raise CircuitBreakerOpenError(
                    f"Circuit breaker '{self.name}' is open"
                )

            if self._state == CircuitState.HALF_OPEN:
                if self._half_open_calls >= self.config.half_open_max_calls:
                    raise CircuitBreakerOpenError(
                        f"Circuit breaker '{self.name}' half-open limit reached"
                    )
                self._half_open_calls += 1

        try:
            result = await func(*args, **kwargs) if asyncio.iscoroutinefunction(func) else func(*args, **kwargs)
            await self._on_success()
            return result
        except Exception as e:
            if not isinstance(e, self.config.excluded_exceptions):
                await self._on_failure()
            raise

    async def _on_success(self) -> None:
        async with self._lock:
            if self._state == CircuitState.HALF_OPEN:
                self._success_count += 1
                if self._success_count >= self.config.success_threshold:
                    self._transition_to(CircuitState.CLOSED)
            elif self._state == CircuitState.CLOSED:
                self._failure_count = 0

    async def _on_failure(self) -> None:
        async with self._lock:
            self._last_failure_time = time.monotonic()
            if self._state == CircuitState.HALF_OPEN:
                self._transition_to(CircuitState.OPEN)
            elif self._state == CircuitState.CLOSED:
                self._failure_count += 1
                if self._failure_count >= self.config.failure_threshold:
                    self._transition_to(CircuitState.OPEN)

    async def _check_state_transition(self) -> None:
        if self._state == CircuitState.OPEN:
            if time.monotonic() - self._last_failure_time >= self.config.timeout_seconds:
                self._transition_to(CircuitState.HALF_OPEN)

    def _transition_to(self, new_state: CircuitState) -> None:
        old_state = self._state
        self._state = new_state
        self._failure_count = 0
        self._success_count = 0
        self._half_open_calls = 0
        # 发出状态变更事件（可接入监控）
        # logger.info(f"Circuit breaker '{self.name}': {old_state} -> {new_state}")

class CircuitBreakerOpenError(Exception):
    """熔断器打开异常"""
    pass

# 熔断器注册表
_circuit_breakers: dict[str, CircuitBreaker] = {}

def get_circuit_breaker(name: str, config: CircuitBreakerConfig | None = None) -> CircuitBreaker:
    """获取或创建熔断器"""
    if name not in _circuit_breakers:
        _circuit_breakers[name] = CircuitBreaker(
            name=name,
            config=config or CircuitBreakerConfig()
        )
    return _circuit_breakers[name]
```

**限流器设计**：

```python
# src/aduib_rpc/resilience/rate_limiter.py
from __future__ import annotations
import asyncio
import time
from dataclasses import dataclass, field
from enum import Enum

class RateLimitAlgorithm(Enum):
    TOKEN_BUCKET = "token_bucket"
    SLIDING_WINDOW = "sliding_window"
    FIXED_WINDOW = "fixed_window"

@dataclass
class RateLimiterConfig:
    """限流器配置"""
    algorithm: RateLimitAlgorithm = RateLimitAlgorithm.TOKEN_BUCKET
    rate: float = 100.0          # 每秒请求数
    burst: int = 150             # 突发容量
    wait_timeout_ms: int = 1000  # 等待超时

@dataclass
class TokenBucketLimiter:
    """令牌桶限流器"""
    config: RateLimiterConfig
    _tokens: float = field(init=False)
    _last_update: float = field(default_factory=time.monotonic, init=False)
    _lock: asyncio.Lock = field(default_factory=asyncio.Lock, init=False)

    def __post_init__(self):
        self._tokens = float(self.config.burst)

    async def acquire(self, tokens: int = 1) -> bool:
        """获取令牌"""
        async with self._lock:
            now = time.monotonic()
            elapsed = now - self._last_update
            self._tokens = min(
                self.config.burst,
                self._tokens + elapsed * self.config.rate
            )
            self._last_update = now

            if self._tokens >= tokens:
                self._tokens -= tokens
                return True
            return False

    async def acquire_or_wait(self, tokens: int = 1) -> bool:
        """获取令牌，必要时等待"""
        deadline = time.monotonic() + self.config.wait_timeout_ms / 1000
        while time.monotonic() < deadline:
            if await self.acquire(tokens):
                return True
            await asyncio.sleep(0.01)  # 10ms 重试间隔
        return False

class RateLimitExceededError(Exception):
    """限流异常"""
    pass
```

---

### 2.3 P0-3: 分布式任务管理器

**重构目标**：支持持久化、分布式执行、任务优先级

```python
# src/aduib_rpc/server/tasks/distributed_task_manager.py
from __future__ import annotations
import asyncio
import json
import time
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Generic, TypeVar

T = TypeVar("T")

class TaskStatus(Enum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELED = "canceled"
    RETRYING = "retrying"

class TaskPriority(Enum):
    LOW = 0
    NORMAL = 1
    HIGH = 2
    CRITICAL = 3

@dataclass
class TaskRecord:
    """任务记录"""
    task_id: str
    status: TaskStatus
    priority: TaskPriority = TaskPriority.NORMAL
    created_at_ms: int = field(default_factory=lambda: int(time.time() * 1000))
    updated_at_ms: int = field(default_factory=lambda: int(time.time() * 1000))
    started_at_ms: int | None = None
    completed_at_ms: int | None = None
    value: Any = None
    error: dict | None = None
    retry_count: int = 0
    max_retries: int = 3
    metadata: dict = field(default_factory=dict)

class TaskStore(ABC):
    """任务存储抽象接口"""

    @abstractmethod
    async def save(self, record: TaskRecord) -> None:
        """保存任务"""
        pass

    @abstractmethod
    async def get(self, task_id: str) -> TaskRecord | None:
        """获取任务"""
        pass

    @abstractmethod
    async def update(self, task_id: str, **updates) -> TaskRecord | None:
        """更新任务"""
        pass

    @abstractmethod
    async def list_by_status(self, status: TaskStatus, limit: int = 100) -> list[TaskRecord]:
        """按状态列出任务"""
        pass

    @abstractmethod
    async def delete_expired(self, ttl_seconds: int) -> int:
        """删除过期任务"""
        pass

class InMemoryTaskStore(TaskStore):
    """内存任务存储（开发/测试用）"""

    def __init__(self):
        self._tasks: dict[str, TaskRecord] = {}
        self._lock = asyncio.Lock()

    async def save(self, record: TaskRecord) -> None:
        async with self._lock:
            self._tasks[record.task_id] = record

    async def get(self, task_id: str) -> TaskRecord | None:
        return self._tasks.get(task_id)

    async def update(self, task_id: str, **updates) -> TaskRecord | None:
        async with self._lock:
            if task_id not in self._tasks:
                return None
            record = self._tasks[task_id]
            for key, value in updates.items():
                if hasattr(record, key):
                    setattr(record, key, value)
            record.updated_at_ms = int(time.time() * 1000)
            return record

    async def list_by_status(self, status: TaskStatus, limit: int = 100) -> list[TaskRecord]:
        return [
            r for r in self._tasks.values()
            if r.status == status
        ][:limit]

    async def delete_expired(self, ttl_seconds: int) -> int:
        async with self._lock:
            cutoff = int(time.time() * 1000) - ttl_seconds * 1000
            expired = [
                tid for tid, r in self._tasks.items()
                if r.completed_at_ms and r.completed_at_ms < cutoff
            ]
            for tid in expired:
                del self._tasks[tid]
            return len(expired)

class RedisTaskStore(TaskStore):
    """Redis 任务存储（生产用）"""

    def __init__(self, redis_url: str, key_prefix: str = "aduib:task:"):
        self._redis_url = redis_url
        self._key_prefix = key_prefix
        self._redis = None  # Lazy initialization

    async def _get_redis(self):
        if self._redis is None:
            import redis.asyncio as redis
            self._redis = redis.from_url(self._redis_url)
        return self._redis

    async def save(self, record: TaskRecord) -> None:
        r = await self._get_redis()
        key = f"{self._key_prefix}{record.task_id}"
        data = {
            "task_id": record.task_id,
            "status": record.status.value,
            "priority": record.priority.value,
            "created_at_ms": record.created_at_ms,
            "updated_at_ms": record.updated_at_ms,
            "started_at_ms": record.started_at_ms,
            "completed_at_ms": record.completed_at_ms,
            "value": json.dumps(record.value) if record.value else None,
            "error": json.dumps(record.error) if record.error else None,
            "retry_count": record.retry_count,
            "max_retries": record.max_retries,
            "metadata": json.dumps(record.metadata),
        }
        await r.hset(key, mapping=data)
        # 添加到状态索引
        await r.sadd(f"{self._key_prefix}status:{record.status.value}", record.task_id)

    async def get(self, task_id: str) -> TaskRecord | None:
        r = await self._get_redis()
        key = f"{self._key_prefix}{task_id}"
        data = await r.hgetall(key)
        if not data:
            return None
        return self._deserialize(data)

    async def update(self, task_id: str, **updates) -> TaskRecord | None:
        r = await self._get_redis()
        key = f"{self._key_prefix}{task_id}"

        # 获取旧状态
        old_status = await r.hget(key, "status")

        updates["updated_at_ms"] = int(time.time() * 1000)

        # 处理状态变更
        if "status" in updates:
            new_status = updates["status"]
            if isinstance(new_status, TaskStatus):
                updates["status"] = new_status.value

            # 更新状态索引
            if old_status:
                await r.srem(f"{self._key_prefix}status:{old_status.decode()}", task_id)
            await r.sadd(f"{self._key_prefix}status:{updates['status']}", task_id)

        # 序列化复杂字段
        if "value" in updates:
            updates["value"] = json.dumps(updates["value"])
        if "error" in updates:
            updates["error"] = json.dumps(updates["error"])

        await r.hset(key, mapping=updates)
        return await self.get(task_id)

    async def list_by_status(self, status: TaskStatus, limit: int = 100) -> list[TaskRecord]:
        r = await self._get_redis()
        task_ids = await r.smembers(f"{self._key_prefix}status:{status.value}")
        records = []
        for tid in list(task_ids)[:limit]:
            record = await self.get(tid.decode() if isinstance(tid, bytes) else tid)
            if record:
                records.append(record)
        return records

    async def delete_expired(self, ttl_seconds: int) -> int:
        # 实现过期任务清理逻辑
        pass

    def _deserialize(self, data: dict) -> TaskRecord:
        return TaskRecord(
            task_id=data[b"task_id"].decode(),
            status=TaskStatus(data[b"status"].decode()),
            priority=TaskPriority(int(data[b"priority"])),
            created_at_ms=int(data[b"created_at_ms"]),
            updated_at_ms=int(data[b"updated_at_ms"]),
            started_at_ms=int(data[b"started_at_ms"]) if data.get(b"started_at_ms") else None,
            completed_at_ms=int(data[b"completed_at_ms"]) if data.get(b"completed_at_ms") else None,
            value=json.loads(data[b"value"]) if data.get(b"value") else None,
            error=json.loads(data[b"error"]) if data.get(b"error") else None,
            retry_count=int(data.get(b"retry_count", 0)),
            max_retries=int(data.get(b"max_retries", 3)),
            metadata=json.loads(data.get(b"metadata", b"{}")),
        )

@dataclass
class DistributedTaskManager:
    """分布式任务管理器"""
    store: TaskStore
    _executor_pool: asyncio.Queue = field(default_factory=lambda: asyncio.Queue(maxsize=100))
    _subscribers: dict[str, list[asyncio.Queue]] = field(default_factory=dict)
    _worker_tasks: list[asyncio.Task] = field(default_factory=list)
    _running: bool = False

    async def start(self, worker_count: int = 4) -> None:
        """启动工作线程"""
        self._running = True
        for i in range(worker_count):
            task = asyncio.create_task(self._worker_loop(f"worker-{i}"))
            self._worker_tasks.append(task)

    async def stop(self) -> None:
        """停止任务管理器"""
        self._running = False
        for task in self._worker_tasks:
            task.cancel()
        await asyncio.gather(*self._worker_tasks, return_exceptions=True)

    async def submit(
        self,
        func: Callable,
        *,
        priority: TaskPriority = TaskPriority.NORMAL,
        max_retries: int = 3,
        ttl_seconds: int | None = None,
        metadata: dict | None = None,
    ) -> TaskRecord:
        """提交任务"""
        task_id = str(uuid.uuid4())
        record = TaskRecord(
            task_id=task_id,
            status=TaskStatus.PENDING,
            priority=priority,
            max_retries=max_retries,
            metadata=metadata or {},
        )
        await self.store.save(record)

        # 将任务放入执行队列
        await self._executor_pool.put((record, func))

        return record

    async def get(self, task_id: str) -> TaskRecord:
        """获取任务状态"""
        record = await self.store.get(task_id)
        if not record:
            raise TaskNotFoundError(f"Task {task_id} not found")
        return record

    async def cancel(self, task_id: str) -> TaskRecord:
        """取消任务"""
        return await self.store.update(
            task_id,
            status=TaskStatus.CANCELED,
            completed_at_ms=int(time.time() * 1000)
        )

    async def subscribe(self, task_id: str) -> asyncio.Queue:
        """订阅任务状态变更"""
        if task_id not in self._subscribers:
            self._subscribers[task_id] = []
        queue = asyncio.Queue()
        self._subscribers[task_id].append(queue)
        return queue

    async def unsubscribe(self, task_id: str, queue: asyncio.Queue) -> None:
        """取消订阅"""
        if task_id in self._subscribers:
            self._subscribers[task_id].remove(queue)

    async def _worker_loop(self, worker_name: str) -> None:
        """工作线程循环"""
        while self._running:
            try:
                record, func = await asyncio.wait_for(
                    self._executor_pool.get(),
                    timeout=1.0
                )
                await self._execute_task(record, func)
            except asyncio.TimeoutError:
                continue
            except asyncio.CancelledError:
                break
            except Exception as e:
                # 记录异常但不中断工作线程
                pass

    async def _execute_task(self, record: TaskRecord, func: Callable) -> None:
        """执行单个任务"""
        # 更新为运行状态
        await self.store.update(
            record.task_id,
            status=TaskStatus.RUNNING,
            started_at_ms=int(time.time() * 1000)
        )
        await self._notify_subscribers(record.task_id, "started")

        try:
            result = await func() if asyncio.iscoroutinefunction(func) else func()
            await self.store.update(
                record.task_id,
                status=TaskStatus.SUCCEEDED,
                value=result,
                completed_at_ms=int(time.time() * 1000)
            )
            await self._notify_subscribers(record.task_id, "completed")
        except Exception as e:
            if record.retry_count < record.max_retries:
                # 重试
                await self.store.update(
                    record.task_id,
                    status=TaskStatus.RETRYING,
                    retry_count=record.retry_count + 1
                )
                # 重新入队
                record.retry_count += 1
                await self._executor_pool.put((record, func))
            else:
                # 最终失败
                await self.store.update(
                    record.task_id,
                    status=TaskStatus.FAILED,
                    error={"message": str(e), "type": type(e).__name__},
                    completed_at_ms=int(time.time() * 1000)
                )
                await self._notify_subscribers(record.task_id, "failed")

    async def _notify_subscribers(self, task_id: str, event: str) -> None:
        """通知订阅者"""
        if task_id in self._subscribers:
            record = await self.store.get(task_id)
            for queue in self._subscribers[task_id]:
                await queue.put({"event": event, "task": record})

class TaskNotFoundError(Exception):
    """任务未找到异常"""
    pass
```

---

### 2.4 P0-4: 统一异常体系

**新增文件**: `src/aduib_rpc/exceptions.py`

```python
# src/aduib_rpc/exceptions.py
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any

# 标准错误码定义
class ErrorCode:
    """标准错误码"""
    # 客户端错误 (4xx)
    INVALID_REQUEST = 4000
    INVALID_PARAMS = 4001
    METHOD_NOT_FOUND = 4004
    UNAUTHORIZED = 4010
    FORBIDDEN = 4030
    NOT_FOUND = 4040
    TIMEOUT = 4080
    RATE_LIMITED = 4290

    # 服务端错误 (5xx)
    INTERNAL_ERROR = 5000
    NOT_IMPLEMENTED = 5010
    SERVICE_UNAVAILABLE = 5030
    CIRCUIT_BREAKER_OPEN = 5031
    DEPENDENCY_FAILURE = 5032

@dataclass(frozen=True)
class RpcException(Exception):
    """RPC 基础异常"""
    code: int
    message: str
    data: Any = None
    cause: Exception | None = field(default=None, repr=False)

    def to_error_dict(self) -> dict:
        """转换为错误响应格式"""
        return {
            "code": self.code,
            "message": self.message,
            "data": self.data,
        }

# 客户端异常
class InvalidRequestError(RpcException):
    def __init__(self, message: str = "Invalid request", data: Any = None):
        super().__init__(ErrorCode.INVALID_REQUEST, message, data)

class InvalidParamsError(RpcException):
    def __init__(self, message: str = "Invalid parameters", data: Any = None):
        super().__init__(ErrorCode.INVALID_PARAMS, message, data)

class MethodNotFoundError(RpcException):
    def __init__(self, method: str):
        super().__init__(ErrorCode.METHOD_NOT_FOUND, f"Method '{method}' not found", {"method": method})

class UnauthorizedError(RpcException):
    def __init__(self, message: str = "Unauthorized"):
        super().__init__(ErrorCode.UNAUTHORIZED, message)

class ForbiddenError(RpcException):
    def __init__(self, message: str = "Forbidden"):
        super().__init__(ErrorCode.FORBIDDEN, message)

class NotFoundError(RpcException):
    def __init__(self, resource: str, identifier: str):
        super().__init__(ErrorCode.NOT_FOUND, f"{resource} '{identifier}' not found", {"resource": resource, "id": identifier})

class TimeoutError(RpcException):
    def __init__(self, operation: str, timeout_ms: int):
        super().__init__(ErrorCode.TIMEOUT, f"Operation '{operation}' timed out after {timeout_ms}ms", {"operation": operation, "timeout_ms": timeout_ms})

class RateLimitedError(RpcException):
    def __init__(self, limit: int, window_seconds: int, retry_after_seconds: int = None):
        data = {"limit": limit, "window_seconds": window_seconds}
        if retry_after_seconds:
            data["retry_after_seconds"] = retry_after_seconds
        super().__init__(ErrorCode.RATE_LIMITED, "Rate limit exceeded", data)

# 服务端异常
class InternalError(RpcException):
    def __init__(self, message: str = "Internal server error", cause: Exception = None):
        super().__init__(ErrorCode.INTERNAL_ERROR, message, cause=cause)

class NotImplementedError(RpcException):
    def __init__(self, feature: str):
        super().__init__(ErrorCode.NOT_IMPLEMENTED, f"Feature '{feature}' not implemented", {"feature": feature})

class ServiceUnavailableError(RpcException):
    def __init__(self, service: str, reason: str = None):
        data = {"service": service}
        if reason:
            data["reason"] = reason
        super().__init__(ErrorCode.SERVICE_UNAVAILABLE, f"Service '{service}' unavailable", data)

class CircuitBreakerOpenError(RpcException):
    def __init__(self, service: str):
        super().__init__(ErrorCode.CIRCUIT_BREAKER_OPEN, f"Circuit breaker for '{service}' is open", {"service": service})

class DependencyFailureError(RpcException):
    def __init__(self, dependency: str, cause: Exception = None):
        super().__init__(ErrorCode.DEPENDENCY_FAILURE, f"Dependency '{dependency}' failed", {"dependency": dependency}, cause)

# 异常处理工具
def exception_to_rpc_error(exc: Exception) -> dict:
    """将任意异常转换为 RPC 错误格式"""
    if isinstance(exc, RpcException):
        return exc.to_error_dict()

    # 映射常见异常
    if isinstance(exc, ValueError):
        return InvalidParamsError(str(exc)).to_error_dict()
    if isinstance(exc, PermissionError):
        return ForbiddenError(str(exc)).to_error_dict()
    if isinstance(exc, ConnectionError):
        return ServiceUnavailableError("unknown", str(exc)).to_error_dict()

    # 默认内部错误
    return InternalError(str(exc)).to_error_dict()
```

---

### 2.5 P0-5: 服务发现健康检查

**重构文件**: `src/aduib_rpc/discover/`

```python
# src/aduib_rpc/discover/health/health_checker.py
from __future__ import annotations
import asyncio
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Callable

from aduib_rpc.discover.entities import ServiceInstance

class HealthStatus(Enum):
    HEALTHY = "healthy"
    UNHEALTHY = "unhealthy"
    DEGRADED = "degraded"
    UNKNOWN = "unknown"

@dataclass
class HealthCheckResult:
    """健康检查结果"""
    status: HealthStatus
    latency_ms: float
    message: str | None = None
    checked_at_ms: int = field(default_factory=lambda: int(time.time() * 1000))

@dataclass
class HealthCheckConfig:
    """健康检查配置"""
    interval_seconds: float = 10.0
    timeout_seconds: float = 5.0
    healthy_threshold: int = 2
    unhealthy_threshold: int = 3
    path: str = "/health"

class HealthChecker(ABC):
    """健康检查器抽象接口"""

    @abstractmethod
    async def check(self, instance: ServiceInstance) -> HealthCheckResult:
        """执行健康检查"""
        pass

class HttpHealthChecker(HealthChecker):
    """HTTP 健康检查器"""

    def __init__(self, config: HealthCheckConfig):
        self.config = config
        self._client = None

    async def _get_client(self):
        if self._client is None:
            import httpx
            self._client = httpx.AsyncClient(timeout=self.config.timeout_seconds)
        return self._client

    async def check(self, instance: ServiceInstance) -> HealthCheckResult:
        start = time.monotonic()
        try:
            client = await self._get_client()
            url = f"{instance.scheme}://{instance.host}:{instance.port}{self.config.path}"
            response = await client.get(url)
            latency_ms = (time.monotonic() - start) * 1000

            if response.status_code == 200:
                return HealthCheckResult(HealthStatus.HEALTHY, latency_ms)
            elif response.status_code == 503:
                return HealthCheckResult(HealthStatus.DEGRADED, latency_ms, "Service degraded")
            else:
                return HealthCheckResult(HealthStatus.UNHEALTHY, latency_ms, f"HTTP {response.status_code}")
        except Exception as e:
            latency_ms = (time.monotonic() - start) * 1000
            return HealthCheckResult(HealthStatus.UNHEALTHY, latency_ms, str(e))

class GrpcHealthChecker(HealthChecker):
    """gRPC 健康检查器"""

    def __init__(self, config: HealthCheckConfig):
        self.config = config

    async def check(self, instance: ServiceInstance) -> HealthCheckResult:
        start = time.monotonic()
        try:
            import grpc
            from grpc_health.v1 import health_pb2, health_pb2_grpc

            channel = grpc.aio.insecure_channel(f"{instance.host}:{instance.port}")
            stub = health_pb2_grpc.HealthStub(channel)

            response = await asyncio.wait_for(
                stub.Check(health_pb2.HealthCheckRequest()),
                timeout=self.config.timeout_seconds
            )
            latency_ms = (time.monotonic() - start) * 1000

            if response.status == health_pb2.HealthCheckResponse.SERVING:
                return HealthCheckResult(HealthStatus.HEALTHY, latency_ms)
            else:
                return HealthCheckResult(HealthStatus.UNHEALTHY, latency_ms, f"Status: {response.status}")
        except Exception as e:
            latency_ms = (time.monotonic() - start) * 1000
            return HealthCheckResult(HealthStatus.UNHEALTHY, latency_ms, str(e))
        finally:
            await channel.close()

@dataclass
class HealthAwareServiceInstance:
    """带健康状态的服务实例"""
    instance: ServiceInstance
    status: HealthStatus = HealthStatus.UNKNOWN
    last_check: HealthCheckResult | None = None
    consecutive_failures: int = 0
    consecutive_successes: int = 0

class HealthAwareRegistry:
    """健康感知服务注册中心"""

    def __init__(
        self,
        base_registry,  # ServiceRegistry
        checker: HealthChecker,
        config: HealthCheckConfig,
    ):
        self._base_registry = base_registry
        self._checker = checker
        self._config = config
        self._health_cache: dict[str, HealthAwareServiceInstance] = {}
        self._check_task: asyncio.Task | None = None

    async def start(self) -> None:
        """启动健康检查循环"""
        self._check_task = asyncio.create_task(self._health_check_loop())

    async def stop(self) -> None:
        """停止健康检查"""
        if self._check_task:
            self._check_task.cancel()
            await asyncio.gather(self._check_task, return_exceptions=True)

    def list_healthy_instances(self, service_name: str) -> list[ServiceInstance]:
        """列出健康的服务实例"""
        all_instances = self._base_registry.list_instances(service_name)
        healthy = []

        for instance in all_instances:
            key = f"{instance.host}:{instance.port}"
            health_instance = self._health_cache.get(key)

            if health_instance is None or health_instance.status == HealthStatus.HEALTHY:
                healthy.append(instance)

        return healthy

    async def _health_check_loop(self) -> None:
        """健康检查循环"""
        while True:
            try:
                # 获取所有已注册服务
                for service_name in self._get_all_service_names():
                    instances = self._base_registry.list_instances(service_name)
                    for instance in instances:
                        await self._check_instance(instance)

                await asyncio.sleep(self._config.interval_seconds)
            except asyncio.CancelledError:
                break
            except Exception:
                # 记录错误但继续循环
                await asyncio.sleep(1.0)

    async def _check_instance(self, instance: ServiceInstance) -> None:
        """检查单个实例"""
        key = f"{instance.host}:{instance.port}"
        result = await self._checker.check(instance)

        if key not in self._health_cache:
            self._health_cache[key] = HealthAwareServiceInstance(instance=instance)

        health_instance = self._health_cache[key]
        health_instance.last_check = result

        if result.status == HealthStatus.HEALTHY:
            health_instance.consecutive_successes += 1
            health_instance.consecutive_failures = 0
            if health_instance.consecutive_successes >= self._config.healthy_threshold:
                health_instance.status = HealthStatus.HEALTHY
        else:
            health_instance.consecutive_failures += 1
            health_instance.consecutive_successes = 0
            if health_instance.consecutive_failures >= self._config.unhealthy_threshold:
                health_instance.status = HealthStatus.UNHEALTHY

    def _get_all_service_names(self) -> list[str]:
        """获取所有服务名称（需要基础注册中心支持）"""
        # 实现依赖于具体注册中心
        return []
```

---

## 第三部分：可观测性增强

### 3.1 结构化日志标准

```python
# src/aduib_rpc/observability/logging.py
from __future__ import annotations
import logging
import json
import time
from dataclasses import dataclass, asdict
from typing import Any
from contextvars import ContextVar

# 请求追踪上下文
_trace_ctx: ContextVar[dict] = ContextVar("trace_context", default={})

@dataclass
class LogContext:
    """日志上下文"""
    trace_id: str | None = None
    span_id: str | None = None
    service: str | None = None
    method: str | None = None
    user_id: str | None = None
    tenant_id: str | None = None

class StructuredLogger:
    """结构化日志记录器"""

    # 标准字段定义
    FIELD_TRACE_ID = "trace_id"
    FIELD_SPAN_ID = "span_id"
    FIELD_SERVICE = "service"
    FIELD_METHOD = "rpc.method"
    FIELD_DURATION_MS = "rpc.duration_ms"
    FIELD_STATUS = "rpc.status"
    FIELD_ERROR_CODE = "rpc.error_code"
    FIELD_ERROR_MESSAGE = "rpc.error_message"
    FIELD_USER_ID = "user_id"
    FIELD_TENANT_ID = "tenant_id"
    FIELD_REQUEST_SIZE = "rpc.request_size"
    FIELD_RESPONSE_SIZE = "rpc.response_size"

    def __init__(self, name: str):
        self._logger = logging.getLogger(name)

    def with_context(self, **extra) -> "BoundLogger":
        """创建带上下文的日志记录器"""
        return BoundLogger(self._logger, extra)

    def info(self, message: str, **extra) -> None:
        self._log(logging.INFO, message, extra)

    def warning(self, message: str, **extra) -> None:
        self._log(logging.WARNING, message, extra)

    def error(self, message: str, **extra) -> None:
        self._log(logging.ERROR, message, extra)

    def debug(self, message: str, **extra) -> None:
        self._log(logging.DEBUG, message, extra)

    def _log(self, level: int, message: str, extra: dict) -> None:
        # 合并追踪上下文
        ctx = _trace_ctx.get()
        merged = {**ctx, **extra}
        self._logger.log(level, message, extra=merged)

class BoundLogger:
    """带绑定上下文的日志记录器"""

    def __init__(self, logger: logging.Logger, context: dict):
        self._logger = logger
        self._context = context

    def info(self, message: str, **extra) -> None:
        self._log(logging.INFO, message, extra)

    def warning(self, message: str, **extra) -> None:
        self._log(logging.WARNING, message, extra)

    def error(self, message: str, **extra) -> None:
        self._log(logging.ERROR, message, extra)

    def _log(self, level: int, message: str, extra: dict) -> None:
        merged = {**self._context, **extra}
        self._logger.log(level, message, extra=merged)

class JsonFormatter(logging.Formatter):
    """JSON 格式化器"""

    def format(self, record: logging.LogRecord) -> str:
        log_data = {
            "timestamp": self.formatTime(record),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }

        # 添加额外字段
        if hasattr(record, "__dict__"):
            for key, value in record.__dict__.items():
                if key not in ("name", "msg", "args", "levelname", "levelno",
                              "pathname", "filename", "module", "exc_info",
                              "exc_text", "stack_info", "lineno", "funcName",
                              "created", "msecs", "relativeCreated", "thread",
                              "threadName", "processName", "process", "message"):
                    log_data[key] = value

        # 添加异常信息
        if record.exc_info:
            log_data["exception"] = self.formatException(record.exc_info)

        return json.dumps(log_data, ensure_ascii=False)

def configure_structured_logging(
    level: int = logging.INFO,
    json_format: bool = True,
) -> None:
    """配置结构化日志"""
    root_logger = logging.getLogger()
    root_logger.setLevel(level)

    handler = logging.StreamHandler()
    if json_format:
        handler.setFormatter(JsonFormatter())
    else:
        handler.setFormatter(logging.Formatter(
            "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
        ))

    root_logger.addHandler(handler)
```

### 3.2 指标收集

```python
# src/aduib_rpc/observability/metrics.py
from __future__ import annotations
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Dict, List
from collections import defaultdict
import threading

@dataclass
class MetricLabels:
    """指标标签"""
    service: str = ""
    method: str = ""
    status: str = ""
    error_code: str = ""

class Metric(ABC):
    """指标抽象基类"""

    @abstractmethod
    def record(self, value: float, labels: MetricLabels) -> None:
        pass

class Counter(Metric):
    """计数器"""

    def __init__(self, name: str, description: str):
        self.name = name
        self.description = description
        self._values: Dict[tuple, float] = defaultdict(float)
        self._lock = threading.Lock()

    def record(self, value: float, labels: MetricLabels) -> None:
        key = (labels.service, labels.method, labels.status, labels.error_code)
        with self._lock:
            self._values[key] += value

    def inc(self, labels: MetricLabels) -> None:
        self.record(1, labels)

    def get(self) -> Dict[tuple, float]:
        with self._lock:
            return dict(self._values)

class Histogram(Metric):
    """直方图"""

    DEFAULT_BUCKETS = (0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10)

    def __init__(self, name: str, description: str, buckets: tuple = None):
        self.name = name
        self.description = description
        self.buckets = buckets or self.DEFAULT_BUCKETS
        self._observations: Dict[tuple, List[float]] = defaultdict(list)
        self._lock = threading.Lock()

    def record(self, value: float, labels: MetricLabels) -> None:
        key = (labels.service, labels.method, labels.status)
        with self._lock:
            self._observations[key].append(value)

    def get_percentile(self, labels: MetricLabels, percentile: float) -> float:
        key = (labels.service, labels.method, labels.status)
        with self._lock:
            observations = sorted(self._observations.get(key, []))
            if not observations:
                return 0.0
            index = int(len(observations) * percentile / 100)
            return observations[min(index, len(observations) - 1)]

class Gauge(Metric):
    """仪表盘"""

    def __init__(self, name: str, description: str):
        self.name = name
        self.description = description
        self._values: Dict[tuple, float] = {}
        self._lock = threading.Lock()

    def record(self, value: float, labels: MetricLabels) -> None:
        key = (labels.service, labels.method)
        with self._lock:
            self._values[key] = value

    def set(self, value: float, labels: MetricLabels) -> None:
        self.record(value, labels)

    def inc(self, labels: MetricLabels, delta: float = 1) -> None:
        key = (labels.service, labels.method)
        with self._lock:
            self._values[key] = self._values.get(key, 0) + delta

    def dec(self, labels: MetricLabels, delta: float = 1) -> None:
        self.inc(labels, -delta)

# 预定义指标
class RpcMetrics:
    """RPC 指标集合"""

    request_total = Counter(
        "aduib_rpc_requests_total",
        "Total number of RPC requests"
    )

    request_duration = Histogram(
        "aduib_rpc_request_duration_seconds",
        "RPC request duration in seconds"
    )

    request_size = Histogram(
        "aduib_rpc_request_size_bytes",
        "RPC request size in bytes",
        buckets=(100, 1000, 10000, 100000, 1000000)
    )

    response_size = Histogram(
        "aduib_rpc_response_size_bytes",
        "RPC response size in bytes",
        buckets=(100, 1000, 10000, 100000, 1000000)
    )

    active_requests = Gauge(
        "aduib_rpc_active_requests",
        "Number of active RPC requests"
    )

    circuit_breaker_state = Gauge(
        "aduib_rpc_circuit_breaker_state",
        "Circuit breaker state (0=closed, 1=open, 2=half-open)"
    )

    @classmethod
    def record_request(
        cls,
        service: str,
        method: str,
        status: str,
        duration_seconds: float,
        request_size: int = 0,
        response_size: int = 0,
        error_code: str = "",
    ) -> None:
        """记录请求指标"""
        labels = MetricLabels(
            service=service,
            method=method,
            status=status,
            error_code=error_code,
        )

        cls.request_total.inc(labels)
        cls.request_duration.record(duration_seconds, labels)

        if request_size:
            cls.request_size.record(request_size, labels)
        if response_size:
            cls.response_size.record(response_size, labels)
```

---

## 第四部分：安全增强

### 4.1 mTLS 支持

```python
# src/aduib_rpc/security/mtls.py
from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
import ssl

@dataclass
class MtlsConfig:
    """mTLS 配置"""
    ca_cert_path: Path
    client_cert_path: Path
    client_key_path: Path
    verify_hostname: bool = True
    check_hostname: bool = True

def create_ssl_context(config: MtlsConfig) -> ssl.SSLContext:
    """创建 SSL 上下文"""
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    context.verify_mode = ssl.CERT_REQUIRED
    context.check_hostname = config.check_hostname

    # 加载 CA 证书
    context.load_verify_locations(str(config.ca_cert_path))

    # 加载客户端证书
    context.load_cert_chain(
        certfile=str(config.client_cert_path),
        keyfile=str(config.client_key_path),
    )

    return context

def create_server_ssl_context(
    cert_path: Path,
    key_path: Path,
    ca_cert_path: Path | None = None,
    require_client_cert: bool = False,
) -> ssl.SSLContext:
    """创建服务端 SSL 上下文"""
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)

    # 加载服务端证书
    context.load_cert_chain(
        certfile=str(cert_path),
        keyfile=str(key_path),
    )

    if require_client_cert and ca_cert_path:
        context.verify_mode = ssl.CERT_REQUIRED
        context.load_verify_locations(str(ca_cert_path))

    return context
```

### 4.2 RBAC 权限控制

```python
# src/aduib_rpc/security/rbac.py
from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum
from typing import Set

class Permission(Enum):
    """权限枚举"""
    READ = "read"
    WRITE = "write"
    EXECUTE = "execute"
    ADMIN = "admin"

@dataclass
class Role:
    """角色定义"""
    name: str
    permissions: Set[Permission] = field(default_factory=set)
    allowed_methods: Set[str] = field(default_factory=set)  # 通配符支持: "service.*"
    denied_methods: Set[str] = field(default_factory=set)

@dataclass
class Principal:
    """主体（用户/服务）"""
    id: str
    roles: Set[str] = field(default_factory=set)
    metadata: dict = field(default_factory=dict)

class RbacPolicy:
    """RBAC 策略"""

    def __init__(self):
        self._roles: dict[str, Role] = {}

    def add_role(self, role: Role) -> None:
        self._roles[role.name] = role

    def check_permission(
        self,
        principal: Principal,
        method: str,
        permission: Permission,
    ) -> bool:
        """检查权限"""
        for role_name in principal.roles:
            role = self._roles.get(role_name)
            if not role:
                continue

            # 检查权限
            if permission not in role.permissions:
                continue

            # 检查方法白名单
            if role.allowed_methods:
                if not self._match_method(method, role.allowed_methods):
                    continue

            # 检查方法黑名单
            if role.denied_methods:
                if self._match_method(method, role.denied_methods):
                    continue

            return True

        return False

    def _match_method(self, method: str, patterns: Set[str]) -> bool:
        """匹配方法名（支持通配符）"""
        for pattern in patterns:
            if pattern.endswith(".*"):
                prefix = pattern[:-2]
                if method.startswith(prefix):
                    return True
            elif pattern == method:
                return True
        return False

# 预定义角色
DEFAULT_ROLES = {
    "admin": Role(
        name="admin",
        permissions={Permission.READ, Permission.WRITE, Permission.EXECUTE, Permission.ADMIN},
        allowed_methods={"*"},
    ),
    "reader": Role(
        name="reader",
        permissions={Permission.READ},
        allowed_methods={"*.get*", "*.list*", "*.query*"},
    ),
    "writer": Role(
        name="writer",
        permissions={Permission.READ, Permission.WRITE},
        allowed_methods={"*"},
        denied_methods={"admin.*", "system.*"},
    ),
}
```

---

## 第五部分：实施路线图

### Phase 1: 基础设施 (2-3 周)

| 任务 | 优先级 | 预估工作量 | 依赖 |
|------|--------|------------|------|
| 统一异常体系 | P0 | 3d | 无 |
| 结构化日志 | P0 | 2d | 无 |
| 熔断器实现 | P0 | 4d | 异常体系 |
| 限流器实现 | P0 | 2d | 无 |
| Runtime 依赖注入重构 | P0 | 5d | 无 |

### Phase 2: 可靠性增强 (2-3 周)

| 任务 | 优先级 | 预估工作量 | 依赖 |
|------|--------|------------|------|
| 分布式任务管理器 | P0 | 5d | Redis 集成 |
| 健康检查机制 | P0 | 3d | 无 |
| 指标收集 | P1 | 3d | 结构化日志 |
| 重试策略增强 | P1 | 2d | 熔断器 |

### Phase 3: 安全与扩展 (3-4 周)

| 任务 | 优先级 | 预估工作量 | 依赖 |
|------|--------|------------|------|
| mTLS 支持 | P1 | 3d | 无 |
| RBAC 权限控制 | P1 | 4d | 无 |
| 配置中心集成 | P1 | 4d | 无 |
| 多注册中心支持 | P1 | 3d | 健康检查 |

### Phase 4: 开发体验 (2 周)

| 任务 | 优先级 | 预估工作量 | 依赖 |
|------|--------|------------|------|
| CLI 调试工具 | P2 | 3d | 无 |
| 代码生成器 | P2 | 4d | 无 |
| 文档完善 | P2 | 3d | 所有功能 |

---

## 第六部分：迁移策略

### 6.1 向后兼容性保证

1. **API 稳定性**：所有公共 API 保持兼容，新增功能通过可选参数启用
2. **渐进式迁移**：旧代码继续工作，新代码使用增强功能
3. **Deprecation 周期**：废弃 API 至少保留 2 个版本

### 6.2 功能开关

```python
# src/aduib_rpc/config.py
from dataclasses import dataclass

@dataclass
class FeatureFlags:
    """功能开关"""
    enable_circuit_breaker: bool = False
    enable_rate_limiting: bool = False
    enable_distributed_tasks: bool = False
    enable_health_check: bool = False
    enable_mtls: bool = False
    enable_rbac: bool = False
    enable_structured_logging: bool = True
    enable_metrics: bool = False
```

### 6.3 配置示例

```yaml
# config/aduib_rpc.yaml
aduib_rpc:
  runtime:
    tenant_id: "production"
    max_connections: 100
    request_timeout_ms: 30000

  resilience:
    circuit_breaker:
      enabled: true
      failure_threshold: 5
      timeout_seconds: 30

    rate_limiter:
      enabled: true
      rate: 1000
      burst: 1500

  observability:
    logging:
      level: INFO
      format: json

    metrics:
      enabled: true
      export_interval_seconds: 15

    tracing:
      enabled: true
      sampling_rate: 0.1

  security:
    mtls:
      enabled: false

    rbac:
      enabled: true
      default_role: reader

  discovery:
    health_check:
      enabled: true
      interval_seconds: 10
      timeout_seconds: 5
```

---

## 附录 A: 目录结构变更

```
src/aduib_rpc/
├── __init__.py
├── types.py
├── exceptions.py                    # 新增: 统一异常体系
├── config.py                        # 新增: 配置管理
│
├── core/                            # 新增: 核心抽象
│   ├── __init__.py
│   ├── context.py                   # Runtime 上下文
│   └── lifecycle.py                 # 生命周期管理
│
├── resilience/                      # 新增: 弹性模式
│   ├── __init__.py
│   ├── circuit_breaker.py
│   ├── rate_limiter.py
│   ├── retry_policy.py
│   ├── bulkhead.py
│   └── fallback.py
│
├── observability/                   # 新增: 可观测性
│   ├── __init__.py
│   ├── logging.py
│   ├── metrics.py
│   └── tracing.py
│
├── security/                        # 新增: 安全
│   ├── __init__.py
│   ├── mtls.py
│   ├── rbac.py
│   └── audit.py
│
├── client/                          # 现有: 客户端
├── server/                          # 现有: 服务端
├── discover/                        # 现有: 服务发现 (增强健康检查)
├── telemetry/                       # 现有: 遥测 (整合到 observability)
└── utils/                           # 现有: 工具
```

---

## 附录 B: 测试策略

### 单元测试覆盖目标

| 模块 | 目标覆盖率 | 关键测试场景 |
|------|-----------|-------------|
| exceptions | 100% | 所有异常类型转换 |
| resilience | 95% | 熔断器状态机、限流算法 |
| observability | 90% | 日志格式化、指标计算 |
| security | 95% | RBAC 权限判断、证书验证 |
| discover | 90% | 健康检查状态转换 |

### 集成测试场景

1. **熔断器集成**：模拟服务故障，验证熔断触发和恢复
2. **限流集成**：高并发请求，验证限流效果
3. **健康检查集成**：模拟实例上下线，验证路由更新
4. **mTLS 集成**：证书校验和握手流程
5. **端到端**：完整请求链路追踪

---

*文档版本: 1.0*
*创建日期: 2026-01-14*
*作者: Claude Code Assistant*
