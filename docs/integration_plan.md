# Aduib RPC 主流程集成计划

> **目标**: 将已实现的企业级模块集成到主流程中，实现从"模块可用"到"开箱即用"的转变。

## 1. 当前状态总结

### 1.1 已实现模块 (100% 定义完成)

```
✅ src/aduib_rpc/resilience/       - 弹性模式模块
   ├── circuit_breaker.py          - 熔断器 (CLOSED/OPEN/HALF_OPEN)
   ├── rate_limiter.py             - 限流器 (Token Bucket 算法)
   ├── retry_policy.py             - 重试策略 (指数退避)
   ├── bulkhead.py                 - 舱壁隔离 (并发限制)
   └── fallback.py                 - 降级策略 (静态/可调用/链式)

✅ src/aduib_rpc/security/          - 安全模块
   ├── mtls.py                     - mTLS 支持 (TlsConfig, SSL context)
   ├── rbac.py                     - RBAC 权限控制 (Role, Permission, Principal)
   └── audit.py                    - 审计日志 (AuditEvent, AuditLogger)

✅ src/aduib_rpc/observability/     - 可观测性模块
   ├── logging.py                  - 结构化日志 (JSON/Console 格式化)
   └── metrics.py                  - 指标收集 (Counter, Histogram, Gauge)

✅ src/aduib_rpc/discover/health/   - 健康检查模块
   ├── health_status.py            - 健康状态枚举
   ├── health_checker.py           - HTTP/gRPC 健康检查器
   └── health_aware_registry.py    - 健康感知注册中心

✅ src/aduib_rpc/config/dynamic.py  - 动态配置模块
✅ src/aduib_rpc/discover/multi_registry.py - 多注册中心支持
```

### 1.2 主流程集成现状 (0% 集成)

```
❌ 客户端主流程 (client/)          - 未使用弹性模块
❌ 服务器主流程 (server/)          - 未使用安全模块
❌ 传输层 (transports/)            - 未使用健康检查
❌ 请求处理 (request_handlers/)    - 未使用可观测性
```

### 1.3 现有拦截器系统

```
client/midwares/
├── __init__.py                    - ClientRequestInterceptor 定义
└── ...                            - 现有拦截器

server/context.py
├── ServerInterceptor 定义          - 服务器拦截器接口
└── ...                            - 现有拦截器
```

## 2. 集成策略

### 2.1 拦截器模式

```
┌─────────────────────────────────────────────────────────────────┐
│                        客户端请求流程                              │
├─────────────────────────────────────────────────────────────────┤
│  用户代码 → 可观测拦截器 → 弹性拦截器链 → 认证拦截器 → 传输层  │
│             (日志+指标)    (限流→熔断→重试)   (mTLS)            │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│                        服务器处理流程                            │
├─────────────────────────────────────────────────────────────────┤
│  传输层 → 认证拦截器 → 授权拦截器 → 可观测拦截器 → 业务逻辑     │
│          (mTLS)       (RBAC)        (日志+指标)                  │
└─────────────────────────────────────────────────────────────────┘
```

### 2.2 配置驱动

```yaml
# aduib_rpc.yaml
aduib_rpc:
  client:
    resilience:
      enabled: true
      circuit_breaker:
        failure_threshold: 5
        timeout_seconds: 30
      rate_limiter:
        rate: 1000
        burst: 1500
      retry:
        max_attempts: 3
        initial_delay_ms: 100

    observability:
      logging:
        enabled: true
        format: json
      metrics:
        enabled: true

  server:
    security:
      rbac:
        enabled: true
        default_role: reader
      mtls:
        enabled: false

    observability:
      logging:
        enabled: true
      metrics:
        enabled: true

    discovery:
      health_check:
        enabled: true
        interval_seconds: 10
```

## 3. 实施任务

### Task 1: 客户端弹性拦截器 (P0)

**文件**: `src/aduib_rpc/client/midwares/resilience_middleware.py`

**功能**:
- 请求前: 检查熔断器状态、获取限流令牌
- 请求失败: 执行重试策略
- 降级处理: 当熔断器打开时返回降级值

**接口**:
```python
class ResilienceMiddleware(ClientRequestInterceptor):
    def __init__(self, config: ResilienceConfig)
    async def intercept(self, request, context) -> AduibRPCError | None
```

### Task 2: 服务器安全拦截器 (P0)

**文件**: `src/aduib_rpc/server/interceptors/security_middleware.py`

**功能**:
- mTLS 证书验证
- RBAC 权限检查
- 审计日志记录

**接口**:
```python
class SecurityMiddleware(ServerInterceptor):
    def __init__(self, rbac_policy: RbacPolicy, audit_logger: AuditLogger)
    async def intercept(self, request, context) -> AduibRPCError | None
```

### Task 3: 可观测性拦截器 (P1)

**文件**: `src/aduib_rpc/observability/interceptor.py`

**功能**:
- 记录请求日志 (trace_id, span_id, duration)
- 收集请求指标 (计数、延迟、错误率)

**接口**:
```python
class ObservabilityInterceptor:
    def __init__(self, logger: StructuredLogger)
    async def wrap_client(self, completion_fn)
    async def wrap_server(self, handler_fn)
```

### Task 4: 健康检查集成 (P1)

**文件**: `src/aduib_rpc/client/transports/health_aware_transport.py`

**功能**:
- 在传输层集成健康检查
- 自动过滤不健康的实例

**接口**:
```python
class HealthAwareClientTransport(ClientTransport):
    def __init__(self, base_transport: ClientTransport, checker: HealthChecker)
    async def completion(self, request, context) -> AduibRpcResponse
```

## 4. 实施顺序

```
Week 1: 核心拦截器
├── Day 1-2: 客户端弹性拦截器
├── Day 3-4: 服务器安全拦截器
└── Day 5: 可观测性拦截器

Week 2: 集成与测试
├── Day 1-2: 健康检查集成
├── Day 3-4: 集成测试
└── Day 5: 文档和示例
```

## 5. 向后兼容性

- 所有新功能通过**可选参数**启用
- 默认配置下保持现有行为
- 拦截器通过**装饰器模式**添加，不修改现有代码

## 6. 验收标准

- [ ] 客户端可以配置熔断器、限流、重试
- [ ] 服务器可以配置 RBAC、审计
- [ ] 请求自动记录日志和指标
- [ ] 健康检查自动过滤不健康实例
- [ ] 所有现有测试通过
- [ ] 新增集成测试覆盖
