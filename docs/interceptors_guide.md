# Aduib RPC 拦截器使用指南

> **概述**: Aduib RPC 拦截器提供了一种声明式的方式为客户端和服务器添加横切关注点，如弹性模式、安全检查、可观测性等。

## 目录

1. [拦截器模式概述](#拦截器模式概述)
2. [客户端弹性拦截器](#客户端弹性拦截器)
3. [服务器安全拦截器](#服务器安全拦截器)
4. [可观测性拦截器](#可观测性拦截器)
5. [健康感知传输层](#健康感知传输层)
6. [配置驱动](#配置驱动)
7. [端到端示例](#端到端示例)

---

## 拦截器模式概述

Aduib RPC 使用拦截器模式来实现横切关注点（Cross-Cutting Concerns）：

```
客户端请求流程:
用户代码 → 可观测拦截器 → 弹性拦截器链 → 认证拦截器 → 传输层
           (日志+指标)    (限流→熔断→重试)   (mTLS)

服务器处理流程:
传输层 → 认证拦截器 → 授权拦截器 → 可观测拦截器 → 业务逻辑
        (mTLS)       (RBAC)        (日志+指标)
```

### 拦截器接口

```python
# 客户端拦截器
from aduib_rpc.client.midwares import ClientRequestInterceptor

class MyInterceptor(ClientRequestInterceptor):
    async def intercept_request(
        self,
        method: str,
        data: dict | None,
        meta: dict | None,
        context: ClientContext,
        next_handler: Callable,
    ) -> tuple[dict | None, dict]:
        # 前置处理
        result = await next_handler(method, data, meta, context)
        # 后置处理
        return result

# 服务器拦截器
from aduib_rpc.server.context import ServerInterceptor

class MyServerInterceptor(ServerInterceptor):
    async def intercept(
        self,
        request: AduibRpcRequest,
        context: ServerContext,
    ) -> AduibRpcError | None:
        # 返回 None 表示通过，返回错误表示拒绝
        return None
```

---

## 客户端弹性拦截器

### 功能特性

| 特性 | 说明 | 配置类 |
|------|------|--------|
| **限流** | Token Bucket 算法，防止过载 | `RateLimiterConfig` |
| **熔断** | 失败达到阈值后自动打开，防止雪崩 | `CircuitBreakerConfig` |
| **重试** | 指数退避重试策略 | `RetryPolicy` |
| **降级** | 熔断时的备用响应 | `FallbackPolicy` |

### 基础用法

```python
from aduib_rpc.client.interceptors import ResilienceMiddleware, ResilienceConfig
from aduib_rpc.resilience.circuit_breaker import CircuitBreakerConfig
from aduib_rpc.resilience.rate_limiter import RateLimiterConfig
from aduib_rpc.resilience.retry_policy import RetryPolicy

# 创建配置
config = ResilienceConfig(
    # 熔断器: 5 次失败后打开，30 秒后尝试恢复
    circuit_breaker=CircuitBreakerConfig(
        failure_threshold=5,
        timeout_seconds=30,
    ),
    # 限流: 每秒 1000 次请求，突发 1500
    rate_limiter=RateLimiterConfig(
        rate=1000,
        burst=1500,
    ),
    # 重试: 最多 3 次，初始延迟 100ms
    retry=RetryPolicy(
        max_attempts=3,
        initial_delay_ms=100,
    ),
)

# 创建拦截器
middleware = ResilienceMiddleware(config)

# 注册到客户端
from aduib_rpc.client import AduibRpcClient

client = AduibRpcClient(
    url="http://localhost:8080",
    interceptors=[middleware],
)
```

### 服务级别配置

```python
config = ResilienceConfig(
    # 默认配置
    circuit_breaker=CircuitBreakerConfig(failure_threshold=5),
    rate_limiter=RateLimiterConfig(rate=1000),
    # 为特定服务覆盖配置
    service_overrides={
        "payment-service": {
            "circuit_breaker": CircuitBreakerConfig(
                failure_threshold=3,  # 更敏感
                timeout_seconds=60,
            ),
            "rate_limiter": RateLimiterConfig(rate=100),  # 更保守
        },
    },
)
```

### 降级策略

```python
from aduib_rpc.resilience.fallback import FallbackPolicy

# 静态降级
fallback = FallbackPolicy.static(
    {"error": "service unavailable", "code": 503}
)

# 可调用降级
async def get_cached_data():
    return cache.get("default_data")

fallback = FallbackPolicy.from_callable(get_cached_data)

config = ResilienceConfig(
    circuit_breaker=CircuitBreakerConfig(failure_threshold=5),
    fallback=fallback,
)
```

---

## 服务器安全拦截器

### 功能特性

| 特性 | 说明 | 配置类 |
|------|------|--------|
| **RBAC** | 基于角色的访问控制 | `RbacPolicy` |
| **审计日志** | 记录所有授权决策 | `AuditLogger` |
| **匿名方法** | 公开 API 白名单 | `anonymous_methods` |

### 基础用法

```python
from aduib_rpc.server.interceptors.security import (
    SecurityInterceptor,
    SecurityConfig,
)
from aduib_rpc.security.rbac import RbacPolicy, Role, Permission

# 定义角色和权限
admin_role = Role(
    name="admin",
    permissions=frozenset([
        Permission(resource="*", action="*"),  # 全部权限
    ]),
    allowed_methods=frozenset(["*"]),
)

user_role = Role(
    name="user",
    permissions=frozenset([
        Permission(resource="data", action="read"),
    ]),
    allowed_methods=frozenset(["*.get", "*.list"]),
    denied_methods=frozenset(["*.delete", "admin.*"]),
)

# 创建 RBAC 策略
rbac_policy = RbacPolicy(
    roles=[admin_role, user_role],
    default_role="anonymous",
    superadmin_role="admin",
)

# 创建安全拦截器
security_config = SecurityConfig(
    rbac_enabled=True,
    audit_enabled=True,
    anonymous_methods={"health", "ping"},
)

interceptor = SecurityInterceptor(
    config=security_config,
    rbac_policy=rbac_policy,
)

# 注册到服务器
from aduib_rpc.server.request_handlers import DefaultRequestHandler

request_handler = DefaultRequestHandler(
    interceptors=[interceptor],
)
```

### 请求中携带权限信息

```python
from aduib_rpc import AduibRpcRequest

request = AduibRpcRequest(
    id="req-1",
    method="user.profile",
    name="user",
    data={"user_id": "123"},
    meta={
        # 指定主体信息
        "principal_id": "user-123",
        "principal_type": "user",
        "roles": ["user"],  # 用户角色列表
    },
)

response = await client.call(request)
```

### 审计日志

```python
from aduib_rpc.security.audit import AuditLogger, AuditEvent

# 自定义审计日志
class MyAuditLogger(AuditLogger):
    async def log_event(self, event: AuditEvent) -> None:
        # 写入数据库或发送到审计系统
        await db.audit_logs.insert({
            "timestamp": event.timestamp,
            "principal": event.principal_id,
            "action": event.action,
            "resource": event.resource,
            "result": event.result,
        })

audit_logger = MyAuditLogger()
rbac_policy.set_audit_logger(audit_logger)
```

---

## 可观测性拦截器

### 功能特性

| 特性 | 说明 | 配置类 |
|------|------|--------|
| **追踪** | W3C Trace Context 传播 | `TraceContext` |
| **日志** | 结构化请求/响应日志 | `ObservabilityConfig` |
| **指标** | Counter, Histogram, Gauge | `RpcMetrics` |

### 基础用法

```python
from aduib_rpc.observability import (
    ClientObservabilityInterceptor,
    ServerObservabilityInterceptor,
    ObservabilityConfig,
)

config = ObservabilityConfig(
    logging_enabled=True,
    metrics_enabled=True,
    include_request_body=False,  # 不记录请求体（敏感数据）
)

# 客户端拦截器
client_interceptor = ClientObservabilityInterceptor(config)

# 服务器拦截器
server_interceptor = ServerObservabilityInterceptor(config)

# 使用
client = AduibRpcClient(
    url="http://localhost:8080",
    interceptors=[client_interceptor],
)

server_handler = DefaultRequestHandler(
    interceptors=[server_interceptor],
)
```

### 自定义日志

```python
import logging

logger = logging.getLogger("myapp.rpc")

config = ObservabilityConfig(
    logging_enabled=True,
    metrics_enabled=False,
    logger=logger,  # 自定义 logger
)
```

### 访问指标

```python
from aduib_rpc.observability import RpcMetrics

metrics = RpcMetrics.get_instance()

# 获取计数器
call_count = metrics.get_counter("rpc.calls.total")
print(f"Total calls: {call_count}")

# 获取直方图
latency = metrics.get_histogram("rpc.latency.ms")
print(f"Average latency: {latency.avg}")

# 获取最新请求的指标
last_metrics = metrics.get_last_metrics("user-service")
```

---

## 健康感知传输层

### 功能特性

- 自动过滤不健康的服务实例
- 支持健康检查缓存
- 与 `HealthAwareRegistry` 集成

### 基础用法

```python
from aduib_rpc.client.transports import (
    HealthAwareClientTransport,
    wrap_transport_producer,
)
from aduib_rpc.discover import HealthAwareRegistry, HttpHealthChecker
from aduib_rpc.discover.health import HealthCheckConfig

# 创建健康检查配置
health_config = HealthCheckConfig(
    interval_seconds=10,
    timeout_seconds=5,
    healthy_threshold=2,
    unhealthy_threshold=2,
)

# 创建健康检查器
health_checker = HttpHealthChecker()

# 创建健康感知注册中心
base_registry = InMemoryServiceRegistry()
registry = HealthAwareRegistry(base_registry, health_checker, health_config)

# 创建健康感知传输
def transport_factory(url, config, interceptors):
    # 返回基础传输层
    return HttpTransport(url, interceptors)

health_transport = HealthAwareClientTransport(
    base_transport_factory=transport_factory,
    service_name="my-service",
    health_registry=registry,
    health_config=health_config,
)

# 与 client_factory 集成
from aduib_rpc.client import AduibRpcClientFactory

factory = AduibRpcClientFactory(config)
factory.register(
    "health-aware",
    wrap_transport_producer(health_transport),
)

client = factory.create(
    service_url="http://example.com",
    server_preferred="health-aware",
)
```

---

## 配置驱动

### YAML 配置文件

创建 `aduib_rpc.yaml`:

```yaml
aduib_rpc:
  # 客户端弹性配置
  client:
    resilience:
      enabled: true
      circuit_breaker:
        failure_threshold: 5
        timeout_seconds: 30
        half_open_attempts: 3
      rate_limiter:
        rate: 1000
        burst: 1500
        algorithm: token_bucket
      retry:
        max_attempts: 3
        initial_delay_ms: 100
        max_delay_ms: 10000
        backoff_multiplier: 2.0

  # 服务器安全配置
  server:
    security:
      rbac_enabled: true
      audit_enabled: true
      require_auth: true
      default_role: anonymous
      superadmin_role: admin
      anonymous_methods:
        - health
        - ping
      mtls:
        enabled: false

  # 可观测性配置
  observability:
    logging:
      enabled: true
      format: json
      level: INFO
    metrics:
      enabled: true

  # 健康检查配置
  health_check:
    interval_seconds: 10
    timeout_seconds: 5
    healthy_threshold: 2
    unhealthy_threshold: 2
    path: /health
```

### 加载配置

```python
from aduib_rpc.config import load_config
from aduib_rpc.client.interceptors import ResilienceMiddleware

# 加载配置文件
config = load_config("aduib_rpc.yaml")

# 创建拦截器
resilience = ResilienceMiddleware(config.client.resilience)

# 或使用服务器安全配置
from aduib_rpc.server.interceptors.security import SecurityInterceptor

security = SecurityInterceptor(
    config=config.server.security,
    rbac_policy=rbac_policy,
)
```

### 环境变量覆盖

```yaml
# 使用环境变量，支持默认值
aduib_rpc:
  client:
    resilience:
      rate_limiter:
        rate: ${RATE_LIMIT:-1000}  # 从环境变量读取，默认 1000
        burst: ${RATE_BURST:-1500}
```

```bash
# 启动时设置环境变量
export RATE_LIMIT=500
export RATE_BURST=1000
python app.py
```

---

## 端到端示例

### 完整的客户端配置

```python
import asyncio
from aduib_rpc.client import AduibRpcClient
from aduib_rpc.client.interceptors import ResilienceMiddleware, ResilienceConfig
from aduib_rpc.observability import ClientObservabilityInterceptor, ObservabilityConfig
from aduib_rpc.resilience.circuit_breaker import CircuitBreakerConfig
from aduib_rpc.resilience.rate_limiter import RateLimiterConfig
from aduib_rpc.resilience.retry_policy import RetryPolicy

async def main():
    # 弹性配置
    resilience_config = ResilienceConfig(
        circuit_breaker=CircuitBreakerConfig(failure_threshold=5),
        rate_limiter=RateLimiterConfig(rate=1000, burst=1500),
        retry=RetryPolicy(max_attempts=3),
    )

    # 可观测性配置
    obs_config = ObservabilityConfig(
        logging_enabled=True,
        metrics_enabled=True,
    )

    # 创建拦截器链
    interceptors = [
        ClientObservabilityInterceptor(obs_config),  # 先记录日志
        ResilienceMiddleware(resilience_config),       # 后应用弹性
    ]

    # 创建客户端
    client = AduibRpcClient(
        url="http://localhost:8080",
        interceptors=interceptors,
    )

    # 发送请求
    response = await client.call(
        method="user.get",
        data={"user_id": "123"},
    )

    print(response.result)

asyncio.run(main())
```

### 完整的服务器配置

```python
import asyncio
from aduib_rpc.server.request_handlers import DefaultRequestHandler
from aduib_rpc.server.interceptors.security import SecurityInterceptor, SecurityConfig
from aduib_rpc.observability import ServerObservabilityInterceptor, ObservabilityConfig
from aduib_rpc.security.rbac import RbacPolicy, Role, Permission
from aduib_rpc.discover.service import AduibServiceFactory

# RBAC 策略
admin_role = Role(
    name="admin",
    permissions=frozenset([Permission(resource="*", action="*")]),
    allowed_methods=frozenset(["*"]),
)

user_role = Role(
    name="user",
    permissions=frozenset([Permission(resource="data", action="read")]),
    allowed_methods=frozenset(["*.get", "*.list"]),
)

rbac_policy = RbacPolicy(
    roles=[admin_role, user_role],
    default_role="anonymous",
)

# 安全配置
security_config = SecurityConfig(
    rbac_enabled=True,
    audit_enabled=True,
    anonymous_methods={"health", "ping"},
)

# 可观测性配置
obs_config = ObservabilityConfig(
    logging_enabled=True,
    metrics_enabled=True,
)

# 拦截器链
interceptors = [
    ServerObservabilityInterceptor(obs_config),
    SecurityInterceptor(config=security_config, rbac_policy=rbac_policy),
]

# 创建请求处理器
request_handler = DefaultRequestHandler(interceptors=interceptors)

# 创建服务实例
from aduib_rpc.discover.entities import ServiceInstance

instance = ServiceInstance(
    service_name="user-service",
    host="0.0.0.0",
    port=8080,
    scheme="http",
)

# 启动服务器
factory = AduibServiceFactory(instance, interceptors=interceptors)
await factory.run_jsonrpc_server()
```

### 使用配置文件

```python
from aduib_rpc.config import load_config
from aduib_rpc.client import AduibRpcClient
from aduib_rpc.client.interceptors import ResilienceMiddleware
from aduib_rpc.observability import ClientObservabilityInterceptor

# 从文件加载配置
config = load_config("aduib_rpc.yaml")

# 构建拦截器
interceptors = [
    ClientObservabilityInterceptor(config.observability),
    ResilienceMiddleware(config.client.resilience),
]

# 创建客户端
client = AduibRpcClient(
    url="http://localhost:8080",
    interceptors=interceptors,
)
```

---

## 附录

### 配置类参考

| 配置类 | 模块 | 说明 |
|--------|------|------|
| `ResilienceConfig` | `client.interceptors.resilience` | 客户端弹性配置 |
| `SecurityConfig` | `server.interceptors.security` | 服务器安全配置 |
| `ObservabilityConfig` | `observability` | 可观测性配置 |
| `HealthCheckConfig` | `discover.health` | 健康检查配置 |

### 导入速查

```python
# 客户端拦截器
from aduib_rpc.client.interceptors import (
    ResilienceMiddleware,
    ResilienceConfig,
)
from aduib_rpc.client.midwares import (
    ClientRequestInterceptor,
    ClientContext,
)

# 服务器拦截器
from aduib_rpc.server.interceptors.security import (
    SecurityInterceptor,
    SecurityConfig,
)
from aduib_rpc.server.context import (
    ServerInterceptor,
    ServerContext,
)

# 可观测性
from aduib_rpc.observability import (
    ClientObservabilityInterceptor,
    ServerObservabilityInterceptor,
    ObservabilityConfig,
    RpcMetrics,
)

# 弹性模式
from aduib_rpc.resilience.circuit_breaker import CircuitBreakerConfig
from aduib_rpc.resilience.rate_limiter import RateLimiterConfig
from aduib_rpc.resilience.retry_policy import RetryPolicy
from aduib_rpc.resilience.fallback import FallbackPolicy

# 安全
from aduib_rpc.security.rbac import RbacPolicy, Role, Permission, Principal
from aduib_rpc.security.audit import AuditLogger

# 配置加载
from aduib_rpc.config import load_config, AduibRpcConfig
```

---

## 相关文档

- [企业级重构计划](./enterprise_refactoring_plan.md)
- [主流程集成计划](./integration_plan.md)
- [Protocol v2.0 规范](./protocol_v2_specification.md)
