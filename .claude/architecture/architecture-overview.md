# Aduib RPC 项目架构总览

**生成时间**: 2026-02-04
**扫描范围**: src/aduib_rpc/**, tests/**

---

## 基本信息

| 属性 | 值 |
|------|---|
| 项目名称 | aduib-rpc |
| 项目类型 | RPC 框架库 (Multi-Protocol RPC Framework) |
| 主要语言 | Python 3.10+ |
| 架构风格 | 分层架构 + 插件式协议适配 |
| 协议版本 | v2.0 (主推) / v1.0 (兼容) |

---

## 系统架构图

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                              CLIENT LAYER                                        │
├─────────────────────────────────────────────────────────────────────────────────┤
│  @client decorator  →  ClientFactory  →  BaseAduibRpcClient                     │
│        ↓                    ↓                   ↓                                │
│  ServiceResolver  ←  RegistryFactory     ClientTransport (Abstract)             │
│        ↓                                        ↓                                │
│  LoadBalancer                    ┌──────────────┼──────────────┐                │
│                                  ↓              ↓              ↓                │
│                           GrpcTransport   JsonRpcTransport  RestTransport       │
└─────────────────────────────────────────────────────────────────────────────────┘
                                         │ Network │
┌─────────────────────────────────────────────────────────────────────────────────┐
│                              SERVER LAYER                                        │
├─────────────────────────────────────────────────────────────────────────────────┤
│  AduibServiceFactory  →  Protocol Server (gRPC/REST/JSONRPC/Thrift)             │
│        ↓                       ↓                                                 │
│  ServiceInstance        Protocol Handler                                         │
│        ↓                       ↓                                                 │
│  Registry (Nacos/InMem)  DefaultRequestHandler                                   │
│                                ↓                                                 │
│                    ┌───────────┼───────────┐                                    │
│                    ↓           ↓           ↓                                    │
│              ServiceCaller  RequestExecutor  TaskManager                        │
│                    ↓                                                             │
│              @service decorator → RpcRuntime                                     │
└─────────────────────────────────────────────────────────────────────────────────┘
                                         │
┌─────────────────────────────────────────────────────────────────────────────────┐
│                           CROSS-CUTTING CONCERNS                                 │
├─────────────────────────────────────────────────────────────────────────────────┤
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐            │
│  │ Resilience  │  │  Security   │  │Observability│  │   Config    │            │
│  ├─────────────┤  ├─────────────┤  ├─────────────┤  ├─────────────┤            │
│  │CircuitBreaker│ │    mTLS     │  │   Metrics   │  │  Dynamic    │            │
│  │ RateLimiter │  │    RBAC     │  │   Logging   │  │   Loader    │            │
│  │   Retry     │  │   Audit     │  │  Telemetry  │  │   Models    │            │
│  │  Bulkhead   │  │             │  │             │  │             │            │
│  │  Fallback   │  │             │  │             │  │             │            │
│  └─────────────┘  └─────────────┘  └─────────────┘  └─────────────┘            │
└─────────────────────────────────────────────────────────────────────────────────┘
```

---

## 核心组件

### 1. 协议层 (Protocol Layer)
- **v2 Protocol Types**: `AduibRpcRequest/AduibRpcResponse` - 统一请求/响应信封
- **兼容层**: `V1Request/V1Response` - v1.0 协议兼容
- **版本协商**: `negotiate_version()` - 客户端/服务端版本协商

### 2. 传输层 (Transport Layer)
- **gRPC**: Protobuf 序列化，支持 Unary + Stream
- **REST**: HTTP POST + SSE Streaming (FastAPI)
- **JSON-RPC 2.0**: HTTP JSON-RPC + SSE (Starlette)
- **Thrift**: TBinaryProtocol，仅 Unary

### 3. 服务发现 (Service Discovery)
- **Registry 抽象**: `ServiceRegistry` 接口
- **实现**: InMemoryRegistry, NacosServiceRegistry
- **健康检查**: `HealthChecker`, `HealthAwareRegistry`
- **负载均衡**: RoundRobin, WeightedRoundRobin, ConsistentHash

### 4. 弹性模式 (Resilience)
- **熔断器**: `CircuitBreaker` - 状态机 (Closed/Open/HalfOpen)
- **限流器**: `RateLimiter` - 令牌桶/滑动窗口
- **重试策略**: `RetryExecutor` - 指数退避
- **舱壁隔离**: `Bulkhead` - 并发隔离
- **降级**: `FallbackExecutor` - 链式降级

### 5. 安全层 (Security)
- **mTLS**: 客户端证书验证
- **RBAC**: 角色权限控制
- **审计日志**: `AuditLogger`

### 6. 可观测性 (Observability)
- **日志**: 结构化日志 (JSON/Console)
- **指标**: `RpcMetrics` - 请求计数/延迟/错误率
- **追踪**: OpenTelemetry 集成 (可选)

---

## 技术栈概览

| 类别 | 技术 | 版本 | 用途 |
|-----|------|-----|------|
| Web 框架 | FastAPI | >=0.115.2 | REST 服务端 |
| ASGI | Starlette | >=0.48.0 | JSON-RPC 服务端 |
| gRPC | grpcio | >=1.66.1 | gRPC 传输 |
| 序列化 | Protobuf | >=4.24.3 | gRPC 消息 |
| 序列化 | Thrift | latest | Thrift 传输 |
| HTTP 客户端 | httpx | >=0.28.1 | REST/JSONRPC 客户端 |
| 数据验证 | Pydantic | >=2.11.0 | 类型定义/验证 |
| 加密 | cryptography | >=43.0.0 | TLS/mTLS |
| 可观测性 | OpenTelemetry | >=1.33.0 | 追踪 (可选) |

---

## 主要能力

### 已实现 (Implemented)
- 多协议支持 (gRPC/REST/JSON-RPC/Thrift)
- 统一消息模型 (v2 Protocol)
- 服务注册/发现 (InMemory/Nacos)
- 负载均衡策略
- 弹性模式完整实现
- 长任务管理 (task/submit/status/result/subscribe)
- v1/v2 协议兼容层
- 代码生成器 (Proto 解析)

### 部分实现 (Partial)
- mTLS (客户端完成，服务端需增强)
- 版本协商 (模型存在，执行语义待完善)
- QoS 配置 (字段存在，执行语义待落地)
- 审计日志 (结构存在，脱敏策略待完善)

### 待实现 (TODO per docs)
- HTTP 状态码映射 (当前全返回 200)
- Streaming 控制帧 (heartbeat/end/cancel/ack)
- 动态配置中心集成
- 分布式任务持久化 (Redis)

---

## 关键数据流

### 服务端请求处理流程
```
1. Protocol Server 接收请求 (gRPC/REST/JSONRPC)
2. Protocol Handler 解析协议特定格式 → AduibRpcRequest
3. ServerInterceptor 链执行 (认证/限流/审计)
4. DefaultRequestHandler.on_message() 分发
5. ServiceCaller 或 RequestExecutor 执行业务逻辑
6. 响应封装为 AduibRpcResponse
7. Protocol Handler 序列化返回
```

### 客户端调用流程
```
1. @client 装饰的 stub 方法被调用
2. ServiceResolver 通过 Registry 解析服务地址
3. LoadBalancer 选择实例
4. ClientFactory 创建/复用 ClientTransport
5. ClientRequestInterceptor 链执行 (认证/追踪)
6. Transport 发送请求 → 接收响应
7. 解析 AduibRpcResponse 返回结果
```
