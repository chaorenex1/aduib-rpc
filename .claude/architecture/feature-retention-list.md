# 功能保留与删除列表

**生成时间**: 2026-02-04
**评估依据**: 代码分析、协议规范、企业级需求

---

## 一、保留功能列表 (KEEP)

### 核心功能 (Critical - 必须保留)

| 序号 | 功能模块 | 路径 | 保留理由 |
|------|---------|------|---------|
| K1 | **v2 协议类型** | `protocol/v2/types.py` | 协议核心，所有通信基础 |
| K2 | **统一消息模型** | `types.py` | 跨协议统一的请求/响应封装 |
| K3 | **DefaultRequestHandler** | `server/request_handlers/default_request_handler.py` | 请求分发核心逻辑 |
| K4 | **ServiceCaller** | `server/rpc_execution/service_call.py` | 服务方法调用引擎 |
| K5 | **RpcRuntime** | `server/rpc_execution/runtime.py` | 服务/客户端注册中心 |
| K6 | **@service/@client 装饰器** | `server/rpc_execution/service_call.py` | 用户友好 API |
| K7 | **AduibServiceFactory** | `discover/service/aduibrpc_service_factory.py` | 服务启动工厂 |
| K8 | **ClientTransport 抽象** | `client/transports/base.py` | 传输层抽象 |

### 协议实现 (Transport - 保留主流协议)

| 序号 | 功能模块 | 路径 | 保留理由 |
|------|---------|------|---------|
| K9 | **gRPC 传输 (v2)** | `client/transports/grpc.py`, `server/request_handlers/grpc_v2_handler.py` | 高性能协议，企业首选 |
| K10 | **REST 传输 (v2)** | `client/transports/rest.py`, `server/request_handlers/rest_v2_handler.py` | 通用性最强 |
| K11 | **JSON-RPC 传输 (v2)** | `client/transports/jsonrpc.py`, `server/protocols/rpc/` | JSON-RPC 2.0 标准 |
| K12 | **Proto 定义** | `proto/`, `grpc/` | gRPC 基础 |

### 服务发现 (Discovery - 保留核心能力)

| 序号 | 功能模块 | 路径 | 保留理由 |
|------|---------|------|---------|
| K13 | **ServiceRegistry 抽象** | `discover/registry/service_registry.py` | 可插拔注册中心基础 |
| K14 | **InMemoryRegistry** | `discover/registry/in_memory.py` | 开发/测试必备 |
| K15 | **NacosRegistry** | `discover/registry/nacos/` | 生产环境主流方案 |
| K16 | **ServiceResolver** | `client/service_resolver.py` | 服务解析核心 |
| K17 | **LoadBalancer** | `discover/load_balance/` | 负载均衡策略 |
| K18 | **HealthChecker** | `discover/health/` | 健康检查必备 |

### 弹性模式 (Resilience - 全部保留)

| 序号 | 功能模块 | 路径 | 保留理由 |
|------|---------|------|---------|
| K19 | **CircuitBreaker** | `resilience/circuit_breaker.py` | 熔断防雪崩 |
| K20 | **RateLimiter** | `resilience/rate_limiter.py` | 限流保护 |
| K21 | **RetryExecutor** | `resilience/retry_policy.py` | 自动重试 |
| K22 | **Bulkhead** | `resilience/bulkhead.py` | 资源隔离 |
| K23 | **FallbackExecutor** | `resilience/fallback.py` | 降级策略 |

### 安全与可观测 (Security & Observability)

| 序号 | 功能模块 | 路径 | 保留理由 |
|------|---------|------|---------|
| K24 | **TlsConfig/TlsVerifier** | `security/mtls.py` | 传输加密 |
| K25 | **RBAC** | `security/rbac.py` | 权限控制 |
| K26 | **AuditLogger** | `security/audit.py`, `observability/audit.py` | 审计合规 |
| K27 | **StructuredLogger** | `observability/logging.py` | 结构化日志 |
| K28 | **RpcMetrics** | `observability/metrics.py` | 指标采集 |
| K29 | **Telemetry (可选)** | `telemetry/` | OpenTelemetry 集成 |

### 任务管理 (Task Management)

| 序号 | 功能模块 | 路径 | 保留理由 |
|------|---------|------|---------|
| K30 | **InMemoryTaskManager** | `server/tasks/task_manager.py` | 长任务基础能力 |
| K31 | **task/* 内置方法** | `default_request_handler.py:73-90` | 长任务 API |

### 配置与工具 (Config & Utils)

| 序号 | 功能模块 | 路径 | 保留理由 |
|------|---------|------|---------|
| K32 | **ConfigLoader** | `config/loader.py` | 配置管理 |
| K33 | **TransportConfig** | `config/transport.py` | 传输配置 |
| K34 | **serialization** | `utils/serialization.py` | 多格式序列化 |
| K35 | **error_handlers** | `utils/error_handlers.py` | 异常转换 |
| K36 | **MethodName 解析** | `rpc/methods.py` | 方法路由核心 |

---

## 二、删除功能列表 (REMOVE)

### 废弃/重复代码 (Deprecated/Duplicate)

| 序号 | 功能模块 | 路径 | 删除理由 |
|------|---------|------|---------|
| R1 | **v1 grpc_handler** | `server/request_handlers/grpc_handler.py` | v2 handler 已覆盖 |
| R2 | **v1 rest_handler** | `server/request_handlers/rest_handler.py` | v2 handler 已覆盖 |
| R3 | **v1 jsonrpc_handler** | `server/request_handlers/jsonrpc_handler.py` | v2 handler 已覆盖 |
| R4 | **v1 thrift_handler** | `server/request_handlers/thrift_handler.py` | v2 handler 已覆盖 |
| R5 | **_DeprecatedRuntimeView** | `service_call.py:49-163` | 仅为向后兼容，已标记废弃 |
| R6 | **test_deprecated_runtime_views.py** | `tests/` | 测试废弃代码 |

### 可选/外部依赖功能 (Optional - 建议移至独立包)

| 序号 | 功能模块 | 路径 | 处理建议 |
|------|---------|------|---------|
| R7 | **A2aServiceFactory** | `discover/service/a2a_service_factory.py` | 移至 `aduib-rpc-a2a` 独立包 |
| R8 | **codegen (Proto 解析)** | `codegen/` | 移至 `aduib-rpc-codegen` CLI 工具 |

### 测试中的遗留文件

| 序号 | 功能模块 | 路径 | 删除理由 |
|------|---------|------|---------|
| R9 | **test_jsonrpc_handler_error_shape.py** | `tests/` | 已被 v2 测试覆盖，git 已标记删除 |
| R10 | **test_rest_handler_error_shape.py** | `tests/` | 已被 v2 测试覆盖，git 已标记删除 |
| R11 | **tests/legacy/__init__.py** | `tests/legacy/` | 空目录，已标记删除 |

---

## 三、待合并/重构功能 (MERGE/REFACTOR)

| 序号 | 现状 | 目标 | 重构建议 |
|------|-----|------|---------|
| M1 | `security/audit.py` + `observability/audit.py` | 统一审计模块 | 保留 `observability/audit.py`，移除重复 |
| M2 | v1 Protocol Types + v2 Protocol Types | 仅保留 v2 | 在 `types.py` 标记 v1 为 deprecated |
| M3 | 多处 `exception_to_error()` 实现 | 统一错误转换 | 在 `utils/error_handlers.py` 统一 |
| M4 | REST/JSONRPC Protocol Server | 统一 ASGI 入口 | 合并为单一 `AduibRpcASGIApp` |

---

## 四、功能保留/删除比例统计

```
保留功能: 36 项 (83%)
删除功能: 11 项 (17%)
- 废弃代码: 6 项
- 建议独立包: 2 项
- 测试遗留: 3 项
```

---

## 五、删除执行计划

### Phase 1: 安全删除 (无风险)
1. 删除 `tests/test_deprecated_runtime_views.py`
2. 删除 `tests/test_jsonrpc_handler_error_shape.py`
3. 删除 `tests/test_rest_handler_error_shape.py`
4. 清理 `tests/legacy/` 空目录

### Phase 2: 废弃代码清理 (需验证测试通过)
1. 删除 `server/request_handlers/grpc_handler.py`
2. 删除 `server/request_handlers/rest_handler.py`
3. 删除 `server/request_handlers/jsonrpc_handler.py`
4. 删除 `server/request_handlers/thrift_handler.py`
5. 更新 `__init__.py` 导出

### Phase 3: 模块拆分 (需要版本发布)
1. 将 `a2a_service_factory.py` 移至独立包
2. 将 `codegen/` 移至独立 CLI 工具

### Phase 4: 废弃 API 移除 (需要主版本号升级)
1. 删除 `_DeprecatedRuntimeView` 相关代码
2. 移除 v1 Protocol Types 兼容别名
