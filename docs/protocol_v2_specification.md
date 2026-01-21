# Aduib RPC Protocol v2.0 Specification

> **版本**: 2.0
> **状态**: Draft
> **日期**: 2026-01-14

## 1. 执行摘要

### 1.1 现有协议问题

| 问题 | 严重程度 | 影响 |
|------|---------|------|
| Python/Protobuf 类型不一致 (`error.code` string vs int) | 🔴 高 | 跨语言互操作失败 |
| 版本硬编码 `'1.0'` | 🟡 中 | 协议演进困难 |
| 缺少链路追踪字段 | 🔴 高 | 分布式追踪不可用 |
| 缺少流式控制信号 | 🟡 中 | 流式通信不完整 |
| 错误码未标准化 | 🟡 中 | 错误处理不一致 |
| 缺少安全/认证字段 | 🔴 高 | 安全审计困难 |
| 缺少 QoS 声明 | 🟡 中 | 无法表达优先级/超时 |

### 1.2 设计目标

1. **类型一致性**: Python、Protobuf、JSON Schema 完全对齐
2. **可扩展性**: 支持版本协商和特性协商
3. **可观测性**: 内置链路追踪和指标收集支持
4. **流式完整性**: 完整的流式控制协议
5. **安全性**: 内置认证和审计字段
6. **向后兼容**: v1.0 客户端可与 v2.0 服务端通信

---

## 2. 协议版本协商

### 2.1 版本格式

```
MAJOR.MINOR
```

- **MAJOR**: 不兼容的协议变更
- **MINOR**: 向后兼容的新特性

### 2.2 协商机制

```
Client → Server: { "aduib_rpc": "2.0", "supported_versions": ["2.0", "1.0"] }
Server → Client: { "aduib_rpc": "2.0", "negotiated_version": "2.0" }
```

---

## 3. 核心数据结构

### 3.1 请求 (Request)

```python
class AduibRpcRequest(BaseModel):
    """Aduib RPC v2.0 请求"""

    # === 协议元数据 ===
    aduib_rpc: Literal["2.0"] = "2.0"
    id: str  # 必填，UUID v4 格式

    # === 路由信息 ===
    method: str  # 格式: "rpc.v2/{service}/{handler}"
    name: str | None = None  # 服务别名（可选）

    # === 负载数据 ===
    data: dict[str, Any] | None = None

    # === 链路追踪 ===
    trace_context: TraceContext | None = None

    # === 请求元数据 ===
    metadata: RequestMetadata | None = None

    # === QoS 配置 ===
    qos: QosConfig | None = None
```

### 3.2 响应 (Response)

```python
class AduibRpcResponse(BaseModel):
    """Aduib RPC v2.0 响应"""

    # === 协议元数据 ===
    aduib_rpc: Literal["2.0"] = "2.0"
    id: str  # 对应请求 ID

    # === 响应状态 ===
    status: ResponseStatus  # "success" | "error" | "partial"

    # === 负载数据（二选一）===
    result: Any | None = None
    error: RpcError | None = None

    # === 链路追踪 ===
    trace_context: TraceContext | None = None

    # === 响应元数据 ===
    metadata: ResponseMetadata | None = None
```

### 3.3 错误 (Error)

```python
class RpcError(BaseModel):
    """标准化错误结构"""

    # === 错误标识 ===
    code: int  # 标准错误码（见 Section 5）
    name: str  # 错误名称，如 "INVALID_PARAMS"

    # === 错误描述 ===
    message: str  # 人类可读消息

    # === 错误详情 ===
    details: list[ErrorDetail] | None = None

    # === 调试信息（仅开发环境）===
    debug: DebugInfo | None = None


class ErrorDetail(BaseModel):
    """错误详情项"""
    type: str  # 错误类型 URI
    field: str | None = None  # 相关字段
    reason: str  # 具体原因
    metadata: dict[str, Any] | None = None


class DebugInfo(BaseModel):
    """调试信息（生产环境不返回）"""
    stack_trace: str | None = None
    internal_message: str | None = None
    timestamp_ms: int
```

### 3.4 链路追踪 (Trace Context)

```python
class TraceContext(BaseModel):
    """W3C Trace Context 兼容"""

    trace_id: str  # 128-bit hex, 32 chars
    span_id: str  # 64-bit hex, 16 chars
    parent_span_id: str | None = None

    # === 追踪标志 ===
    sampled: bool = True

    # === 自定义 baggage ===
    baggage: dict[str, str] | None = None
```

### 3.5 请求元数据 (Request Metadata)

```python
class RequestMetadata(BaseModel):
    """请求元数据"""

    # === 时间戳 ===
    timestamp_ms: int  # 请求发起时间

    # === 客户端信息 ===
    client_id: str | None = None
    client_version: str | None = None

    # === 认证信息 ===
    auth: AuthContext | None = None

    # === 租户隔离 ===
    tenant_id: str | None = None

    # === 序列化配置 ===
    content_type: ContentType = ContentType.JSON
    accept: list[ContentType] | None = None
    compression: Compression | None = None

    # === 自定义头 ===
    headers: dict[str, str] | None = None


class AuthContext(BaseModel):
    """认证上下文"""
    scheme: AuthScheme  # "bearer" | "api_key" | "mtls"
    credentials: str | None = None  # Token 或密钥（敏感，不记录日志）
    principal: str | None = None  # 认证后的主体标识
    roles: list[str] | None = None  # 角色列表


class ContentType(StrEnum):
    JSON = "application/json"
    MSGPACK = "application/msgpack"
    PROTOBUF = "application/protobuf"
    AVRO = "application/avro"


class Compression(StrEnum):
    NONE = "none"
    GZIP = "gzip"
    ZSTD = "zstd"
    LZ4 = "lz4"
```

### 3.6 响应元数据 (Response Metadata)

```python
class ResponseMetadata(BaseModel):
    """响应元数据"""

    # === 时间戳 ===
    timestamp_ms: int  # 响应生成时间
    duration_ms: int  # 处理耗时

    # === 服务端信息 ===
    server_id: str | None = None
    server_version: str | None = None

    # === 分页（可选）===
    pagination: Pagination | None = None

    # === 限流信息 ===
    rate_limit: RateLimitInfo | None = None

    # === 自定义头 ===
    headers: dict[str, str] | None = None


class Pagination(BaseModel):
    """分页信息"""
    total: int
    page: int
    page_size: int
    has_next: bool
    cursor: str | None = None


class RateLimitInfo(BaseModel):
    """限流信息"""
    limit: int
    remaining: int
    reset_at_ms: int
```

### 3.7 QoS 配置

```python
class QosConfig(BaseModel):
    """服务质量配置"""

    # === 优先级 ===
    priority: Priority = Priority.NORMAL

    # === 超时 ===
    timeout_ms: int | None = None

    # === 重试策略 ===
    retry: RetryConfig | None = None

    # === 幂等性 ===
    idempotency_key: str | None = None


class Priority(IntEnum):
    LOW = 0
    NORMAL = 1
    HIGH = 2
    CRITICAL = 3


class RetryConfig(BaseModel):
    """重试配置"""
    max_attempts: int = 3
    initial_delay_ms: int = 100
    max_delay_ms: int = 10000
    backoff_multiplier: float = 2.0
    retryable_codes: list[int] | None = None
```

---

## 4. 流式协议

### 4.1 流式消息类型

```python
class StreamMessageType(StrEnum):
    """流式消息类型"""
    DATA = "data"           # 数据帧
    HEARTBEAT = "heartbeat" # 心跳
    ERROR = "error"         # 错误
    END = "end"             # 流结束
    CANCEL = "cancel"       # 取消请求
    ACK = "ack"             # 确认


class StreamMessage(BaseModel):
    """流式消息包装"""
    type: StreamMessageType
    sequence: int  # 序列号
    payload: StreamPayload | None = None
    timestamp_ms: int


class StreamPayload(BaseModel):
    """流式负载"""
    # 数据帧
    data: Any | None = None

    # 错误帧
    error: RpcError | None = None

    # 控制帧
    control: StreamControl | None = None


class StreamControl(BaseModel):
    """流控制信息"""
    # 流结束
    final: bool = False
    total_count: int | None = None

    # 心跳
    ping_id: str | None = None

    # 取消
    reason: str | None = None

    # 确认
    ack_sequence: int | None = None
```

### 4.2 流式状态机

```
                    ┌─────────────┐
                    │   CREATED   │
                    └──────┬──────┘
                           │ open()
                           ▼
                    ┌─────────────┐
              ┌─────│   ACTIVE    │─────┐
              │     └──────┬──────┘     │
              │            │            │
         error│       data │       cancel
              │            │            │
              ▼            ▼            ▼
       ┌──────────┐  ┌──────────┐  ┌──────────┐
       │  ERRORED │  │ COMPLETED│  │ CANCELLED│
       └──────────┘  └──────────┘  └──────────┘
```

---

## 5. 标准错误码

### 5.1 错误码分类

| 范围 | 类别 | 说明 |
|------|------|------|
| 1000-1999 | 协议错误 | 协议层面的错误 |
| 2000-2999 | 客户端错误 | 请求格式或参数错误 |
| 3000-3999 | 认证授权错误 | 认证和权限相关 |
| 4000-4999 | 资源错误 | 资源不存在或冲突 |
| 5000-5999 | 服务端错误 | 服务端内部错误 |
| 6000-6999 | 外部依赖错误 | 下游服务错误 |

### 5.2 错误码定义

```python
class ErrorCode(IntEnum):
    """标准错误码"""

    # === 协议错误 (1xxx) ===
    PROTOCOL_ERROR = 1000
    UNSUPPORTED_VERSION = 1001
    INVALID_MESSAGE = 1002
    SERIALIZATION_ERROR = 1003
    COMPRESSION_ERROR = 1004

    # === 客户端错误 (2xxx) ===
    BAD_REQUEST = 2000
    INVALID_PARAMS = 2001
    MISSING_REQUIRED_FIELD = 2002
    INVALID_FIELD_VALUE = 2003
    REQUEST_TOO_LARGE = 2004

    # === 认证授权错误 (3xxx) ===
    UNAUTHENTICATED = 3000
    INVALID_TOKEN = 3001
    TOKEN_EXPIRED = 3002
    UNAUTHORIZED = 3010
    PERMISSION_DENIED = 3011
    INSUFFICIENT_SCOPE = 3012

    # === 资源错误 (4xxx) ===
    NOT_FOUND = 4000
    METHOD_NOT_FOUND = 4001
    SERVICE_NOT_FOUND = 4002
    ALREADY_EXISTS = 4010
    CONFLICT = 4011
    GONE = 4020

    # === 服务端错误 (5xxx) ===
    INTERNAL_ERROR = 5000
    NOT_IMPLEMENTED = 5001
    SERVICE_UNAVAILABLE = 5002
    TIMEOUT = 5003
    CIRCUIT_BREAKER_OPEN = 5010
    RATE_LIMITED = 5020
    RESOURCE_EXHAUSTED = 5021

    # === 外部依赖错误 (6xxx) ===
    DEPENDENCY_ERROR = 6000
    UPSTREAM_TIMEOUT = 6001
    UPSTREAM_UNAVAILABLE = 6002


# 错误码到名称映射
ERROR_CODE_NAMES: dict[int, str] = {
    1000: "PROTOCOL_ERROR",
    1001: "UNSUPPORTED_VERSION",
    1002: "INVALID_MESSAGE",
    1003: "SERIALIZATION_ERROR",
    1004: "COMPRESSION_ERROR",

    2000: "BAD_REQUEST",
    2001: "INVALID_PARAMS",
    2002: "MISSING_REQUIRED_FIELD",
    2003: "INVALID_FIELD_VALUE",
    2004: "REQUEST_TOO_LARGE",

    3000: "UNAUTHENTICATED",
    3001: "INVALID_TOKEN",
    3002: "TOKEN_EXPIRED",
    3010: "UNAUTHORIZED",
    3011: "PERMISSION_DENIED",
    3012: "INSUFFICIENT_SCOPE",

    4000: "NOT_FOUND",
    4001: "METHOD_NOT_FOUND",
    4002: "SERVICE_NOT_FOUND",
    4010: "ALREADY_EXISTS",
    4011: "CONFLICT",
    4020: "GONE",

    5000: "INTERNAL_ERROR",
    5001: "NOT_IMPLEMENTED",
    5002: "SERVICE_UNAVAILABLE",
    5003: "TIMEOUT",
    5010: "CIRCUIT_BREAKER_OPEN",
    5020: "RATE_LIMITED",
    5021: "RESOURCE_EXHAUSTED",

    6000: "DEPENDENCY_ERROR",
    6001: "UPSTREAM_TIMEOUT",
    6002: "UPSTREAM_UNAVAILABLE",
}
```

### 5.3 HTTP 状态码映射

| RPC 错误码 | HTTP 状态码 | gRPC 状态码 |
|-----------|------------|------------|
| 2xxx | 400 | INVALID_ARGUMENT |
| 3000-3002 | 401 | UNAUTHENTICATED |
| 3010-3012 | 403 | PERMISSION_DENIED |
| 4000-4002 | 404 | NOT_FOUND |
| 4010-4011 | 409 | ALREADY_EXISTS |
| 5000 | 500 | INTERNAL |
| 5001 | 501 | UNIMPLEMENTED |
| 5002 | 503 | UNAVAILABLE |
| 5003 | 504 | DEADLINE_EXCEEDED |
| 5020-5021 | 429 | RESOURCE_EXHAUSTED |

---

## 6. 服务发现协议

### 6.1 服务实例

```python
class ServiceInstance(BaseModel):
    """服务实例"""

    # === 标识 ===
    instance_id: str  # 全局唯一
    service_name: str
    version: str  # 语义化版本

    # === 网络 ===
    host: str
    port: int
    scheme: TransportScheme

    # === 健康状态 ===
    health: HealthStatus
    last_health_check_ms: int | None = None

    # === 负载均衡 ===
    weight: int = 100
    zone: str | None = None
    region: str | None = None

    # === 能力声明 ===
    capabilities: ServiceCapabilities | None = None

    # === 元数据 ===
    metadata: dict[str, str] | None = None
    tags: list[str] | None = None

    # === 生命周期 ===
    registered_at_ms: int
    ttl_seconds: int = 30


class HealthStatus(StrEnum):
    HEALTHY = "healthy"
    UNHEALTHY = "unhealthy"
    DEGRADED = "degraded"
    UNKNOWN = "unknown"


class TransportScheme(StrEnum):
    HTTP = "http"
    HTTPS = "https"
    GRPC = "grpc"
    GRPCS = "grpcs"
    JSONRPC = "jsonrpc"
    THRIFT = "thrift"


class ServiceCapabilities(BaseModel):
    """服务能力声明"""

    # === 协议支持 ===
    protocol_versions: list[str] = ["2.0"]
    content_types: list[ContentType] = [ContentType.JSON]
    compressions: list[Compression] = [Compression.NONE]

    # === 特性支持 ===
    streaming: bool = False
    bidirectional: bool = False

    # === 方法列表 ===
    methods: list[MethodDescriptor] | None = None


class MethodDescriptor(BaseModel):
    """方法描述"""
    name: str
    input_type: str | None = None
    output_type: str | None = None
    streaming_input: bool = False
    streaming_output: bool = False
    idempotent: bool = False
    deprecated: bool = False
```

---

## 7. 任务协议

### 7.1 任务状态

```python
class TaskStatus(StrEnum):
    """任务状态"""
    PENDING = "pending"       # 等待执行
    SCHEDULED = "scheduled"   # 已调度
    RUNNING = "running"       # 执行中
    SUCCEEDED = "succeeded"   # 成功
    FAILED = "failed"         # 失败
    CANCELED = "canceled"     # 已取消
    RETRYING = "retrying"     # 重试中
```

### 7.2 任务记录

```python
class TaskRecord(BaseModel):
    """任务记录"""

    # === 标识 ===
    task_id: str
    parent_task_id: str | None = None  # 父任务（用于子任务）

    # === 状态 ===
    status: TaskStatus

    # === 优先级 ===
    priority: Priority = Priority.NORMAL

    # === 时间戳 ===
    created_at_ms: int
    scheduled_at_ms: int | None = None
    started_at_ms: int | None = None
    completed_at_ms: int | None = None

    # === 重试信息 ===
    attempt: int = 1
    max_attempts: int = 3
    next_retry_at_ms: int | None = None

    # === 结果 ===
    result: Any | None = None
    error: RpcError | None = None

    # === 进度（可选）===
    progress: TaskProgress | None = None

    # === 元数据 ===
    metadata: dict[str, Any] | None = None
    tags: list[str] | None = None


class TaskProgress(BaseModel):
    """任务进度"""
    current: int
    total: int
    message: str | None = None
    percentage: float | None = None
```

### 7.3 任务操作

```python
# 提交任务
class TaskSubmitRequest(BaseModel):
    target_method: str
    params: dict[str, Any] | None = None
    priority: Priority = Priority.NORMAL
    max_attempts: int = 3
    timeout_ms: int | None = None
    scheduled_at_ms: int | None = None  # 延迟执行
    idempotency_key: str | None = None
    metadata: dict[str, Any] | None = None

class TaskSubmitResponse(BaseModel):
    task_id: str
    status: TaskStatus
    created_at_ms: int


# 查询任务
class TaskQueryRequest(BaseModel):
    task_id: str

class TaskQueryResponse(BaseModel):
    task: TaskRecord


# 取消任务
class TaskCancelRequest(BaseModel):
    task_id: str
    reason: str | None = None

class TaskCancelResponse(BaseModel):
    task_id: str
    status: TaskStatus
    canceled: bool


# 订阅任务
class TaskSubscribeRequest(BaseModel):
    task_id: str
    events: list[str] | None = None  # 订阅的事件类型

class TaskEvent(BaseModel):
    event: str  # "started" | "progress" | "completed" | "failed"
    task: TaskRecord
    timestamp_ms: int
```

---

## 8. Protobuf 定义

```protobuf
syntax = "proto3";

package aduib.rpc.v2;

import "google/protobuf/any.proto";
import "google/protobuf/struct.proto";
import "google/protobuf/timestamp.proto";

option go_package = "github.com/aduib/rpc/v2;rpcv2";
option java_package = "com.aduib.rpc.v2";
option java_multiple_files = true;

// ============================================================
// 核心消息
// ============================================================

message Request {
  // 协议版本
  string aduib_rpc = 1;  // "2.0"

  // 请求标识
  string id = 2;

  // 路由
  string method = 3;
  optional string name = 4;

  // 负载
  google.protobuf.Struct data = 5;

  // 链路追踪
  optional TraceContext trace_context = 6;

  // 元数据
  optional RequestMetadata metadata = 7;

  // QoS
  optional QosConfig qos = 8;
}

message Response {
  // 协议版本
  string aduib_rpc = 1;

  // 请求标识
  string id = 2;

  // 状态
  ResponseStatus status = 3;

  // 结果（二选一）
  oneof payload {
    google.protobuf.Value result = 4;
    RpcError error = 5;
  }

  // 链路追踪
  optional TraceContext trace_context = 6;

  // 元数据
  optional ResponseMetadata metadata = 7;
}

enum ResponseStatus {
  RESPONSE_STATUS_UNSPECIFIED = 0;
  RESPONSE_STATUS_SUCCESS = 1;
  RESPONSE_STATUS_ERROR = 2;
  RESPONSE_STATUS_PARTIAL = 3;
}

// ============================================================
// 错误
// ============================================================

message RpcError {
  int32 code = 1;
  string name = 2;
  string message = 3;
  repeated ErrorDetail details = 4;
  optional DebugInfo debug = 5;
}

message ErrorDetail {
  string type = 1;
  optional string field = 2;
  string reason = 3;
  map<string, string> metadata = 4;
}

message DebugInfo {
  optional string stack_trace = 1;
  optional string internal_message = 2;
  int64 timestamp_ms = 3;
}

// ============================================================
// 链路追踪
// ============================================================

message TraceContext {
  string trace_id = 1;
  string span_id = 2;
  optional string parent_span_id = 3;
  bool sampled = 4;
  map<string, string> baggage = 5;
}

// ============================================================
// 元数据
// ============================================================

message RequestMetadata {
  int64 timestamp_ms = 1;
  optional string client_id = 2;
  optional string client_version = 3;
  optional AuthContext auth = 4;
  optional string tenant_id = 5;
  ContentType content_type = 6;
  repeated ContentType accept = 7;
  optional Compression compression = 8;
  map<string, string> headers = 9;
}

message ResponseMetadata {
  int64 timestamp_ms = 1;
  int64 duration_ms = 2;
  optional string server_id = 3;
  optional string server_version = 4;
  optional Pagination pagination = 5;
  optional RateLimitInfo rate_limit = 6;
  map<string, string> headers = 7;
}

message AuthContext {
  AuthScheme scheme = 1;
  optional string credentials = 2;
  optional string principal = 3;
  repeated string roles = 4;
}

enum AuthScheme {
  AUTH_SCHEME_UNSPECIFIED = 0;
  AUTH_SCHEME_BEARER = 1;
  AUTH_SCHEME_API_KEY = 2;
  AUTH_SCHEME_MTLS = 3;
}

enum ContentType {
  CONTENT_TYPE_UNSPECIFIED = 0;
  CONTENT_TYPE_JSON = 1;
  CONTENT_TYPE_MSGPACK = 2;
  CONTENT_TYPE_PROTOBUF = 3;
  CONTENT_TYPE_AVRO = 4;
}

enum Compression {
  COMPRESSION_UNSPECIFIED = 0;
  COMPRESSION_NONE = 1;
  COMPRESSION_GZIP = 2;
  COMPRESSION_ZSTD = 3;
  COMPRESSION_LZ4 = 4;
}

message Pagination {
  int64 total = 1;
  int32 page = 2;
  int32 page_size = 3;
  bool has_next = 4;
  optional string cursor = 5;
}

message RateLimitInfo {
  int32 limit = 1;
  int32 remaining = 2;
  int64 reset_at_ms = 3;
}

// ============================================================
// QoS
// ============================================================

message QosConfig {
  Priority priority = 1;
  optional int64 timeout_ms = 2;
  optional RetryConfig retry = 3;
  optional string idempotency_key = 4;
}

enum Priority {
  PRIORITY_UNSPECIFIED = 0;
  PRIORITY_LOW = 1;
  PRIORITY_NORMAL = 2;
  PRIORITY_HIGH = 3;
  PRIORITY_CRITICAL = 4;
}

message RetryConfig {
  int32 max_attempts = 1;
  int64 initial_delay_ms = 2;
  int64 max_delay_ms = 3;
  double backoff_multiplier = 4;
  repeated int32 retryable_codes = 5;
}

// ============================================================
// 流式消息
// ============================================================

message StreamMessage {
  StreamMessageType type = 1;
  int64 sequence = 2;
  optional StreamPayload payload = 3;
  int64 timestamp_ms = 4;
}

enum StreamMessageType {
  STREAM_MESSAGE_TYPE_UNSPECIFIED = 0;
  STREAM_MESSAGE_TYPE_DATA = 1;
  STREAM_MESSAGE_TYPE_HEARTBEAT = 2;
  STREAM_MESSAGE_TYPE_ERROR = 3;
  STREAM_MESSAGE_TYPE_END = 4;
  STREAM_MESSAGE_TYPE_CANCEL = 5;
  STREAM_MESSAGE_TYPE_ACK = 6;
}

message StreamPayload {
  oneof content {
    google.protobuf.Value data = 1;
    RpcError error = 2;
    StreamControl control = 3;
  }
}

message StreamControl {
  bool final = 1;
  optional int64 total_count = 2;
  optional string ping_id = 3;
  optional string reason = 4;
  optional int64 ack_sequence = 5;
}

// ============================================================
// 服务发现
// ============================================================

message ServiceInstance {
  string instance_id = 1;
  string service_name = 2;
  string version = 3;
  string host = 4;
  int32 port = 5;
  TransportScheme scheme = 6;
  HealthStatus health = 7;
  optional int64 last_health_check_ms = 8;
  int32 weight = 9;
  optional string zone = 10;
  optional string region = 11;
  optional ServiceCapabilities capabilities = 12;
  map<string, string> metadata = 13;
  repeated string tags = 14;
  int64 registered_at_ms = 15;
  int32 ttl_seconds = 16;
}

enum TransportScheme {
  TRANSPORT_SCHEME_UNSPECIFIED = 0;
  TRANSPORT_SCHEME_HTTP = 1;
  TRANSPORT_SCHEME_HTTPS = 2;
  TRANSPORT_SCHEME_GRPC = 3;
  TRANSPORT_SCHEME_GRPCS = 4;
  TRANSPORT_SCHEME_JSONRPC = 5;
  TRANSPORT_SCHEME_THRIFT = 6;
}

enum HealthStatus {
  HEALTH_STATUS_UNSPECIFIED = 0;
  HEALTH_STATUS_HEALTHY = 1;
  HEALTH_STATUS_UNHEALTHY = 2;
  HEALTH_STATUS_DEGRADED = 3;
  HEALTH_STATUS_UNKNOWN = 4;
}

message ServiceCapabilities {
  repeated string protocol_versions = 1;
  repeated ContentType content_types = 2;
  repeated Compression compressions = 3;
  bool streaming = 4;
  bool bidirectional = 5;
  repeated MethodDescriptor methods = 6;
}

message MethodDescriptor {
  string name = 1;
  optional string input_type = 2;
  optional string output_type = 3;
  bool streaming_input = 4;
  bool streaming_output = 5;
  bool idempotent = 6;
  bool deprecated = 7;
}

// ============================================================
// 任务
// ============================================================

message TaskRecord {
  string task_id = 1;
  optional string parent_task_id = 2;
  TaskStatus status = 3;
  Priority priority = 4;
  int64 created_at_ms = 5;
  optional int64 scheduled_at_ms = 6;
  optional int64 started_at_ms = 7;
  optional int64 completed_at_ms = 8;
  int32 attempt = 9;
  int32 max_attempts = 10;
  optional int64 next_retry_at_ms = 11;
  optional google.protobuf.Value result = 12;
  optional RpcError error = 13;
  optional TaskProgress progress = 14;
  map<string, string> metadata = 15;
  repeated string tags = 16;
}

enum TaskStatus {
  TASK_STATUS_UNSPECIFIED = 0;
  TASK_STATUS_PENDING = 1;
  TASK_STATUS_SCHEDULED = 2;
  TASK_STATUS_RUNNING = 3;
  TASK_STATUS_SUCCEEDED = 4;
  TASK_STATUS_FAILED = 5;
  TASK_STATUS_CANCELED = 6;
  TASK_STATUS_RETRYING = 7;
}

message TaskProgress {
  int64 current = 1;
  int64 total = 2;
  optional string message = 3;
  optional double percentage = 4;
}

// ============================================================
// 服务定义
// ============================================================

service AduibRpcService {
  // 一元调用
  rpc Call(Request) returns (Response);

  // 服务端流式
  rpc CallServerStream(Request) returns (stream StreamMessage);

  // 客户端流式
  rpc CallClientStream(stream StreamMessage) returns (Response);

  // 双向流式
  rpc CallBidirectional(stream StreamMessage) returns (stream StreamMessage);
}

service TaskService {
  // 提交任务
  rpc Submit(TaskSubmitRequest) returns (TaskSubmitResponse);

  // 查询任务
  rpc Query(TaskQueryRequest) returns (TaskQueryResponse);

  // 取消任务
  rpc Cancel(TaskCancelRequest) returns (TaskCancelResponse);

  // 订阅任务事件
  rpc Subscribe(TaskSubscribeRequest) returns (stream TaskEvent);
}

message TaskSubmitRequest {
  string target_method = 1;
  optional google.protobuf.Struct params = 2;
  Priority priority = 3;
  int32 max_attempts = 4;
  optional int64 timeout_ms = 5;
  optional int64 scheduled_at_ms = 6;
  optional string idempotency_key = 7;
  map<string, string> metadata = 8;
}

message TaskSubmitResponse {
  string task_id = 1;
  TaskStatus status = 2;
  int64 created_at_ms = 3;
}

message TaskQueryRequest {
  string task_id = 1;
}

message TaskQueryResponse {
  TaskRecord task = 1;
}

message TaskCancelRequest {
  string task_id = 1;
  optional string reason = 2;
}

message TaskCancelResponse {
  string task_id = 1;
  TaskStatus status = 2;
  bool canceled = 3;
}

message TaskSubscribeRequest {
  string task_id = 1;
  repeated string events = 2;
}

message TaskEvent {
  string event = 1;
  TaskRecord task = 2;
  int64 timestamp_ms = 3;
}

service HealthService {
  rpc Check(HealthCheckRequest) returns (HealthCheckResponse);
  rpc Watch(HealthCheckRequest) returns (stream HealthCheckResponse);
}

message HealthCheckRequest {
  optional string service = 1;
}

message HealthCheckResponse {
  HealthStatus status = 1;
  map<string, HealthStatus> services = 2;
}
```

---

## 9. JSON 示例

### 9.1 请求示例

```json
{
  "aduib_rpc": "2.0",
  "id": "550e8400-e29b-41d4-a716-446655440000",
  "method": "rpc.v2/UserService/GetUser",
  "data": {
    "user_id": "12345"
  },
  "trace_context": {
    "trace_id": "0af7651916cd43dd8448eb211c80319c",
    "span_id": "b7ad6b7169203331",
    "sampled": true
  },
  "metadata": {
    "timestamp_ms": 1705234567890,
    "client_id": "web-client-1",
    "tenant_id": "tenant-abc",
    "auth": {
      "scheme": "bearer",
      "principal": "user-123"
    },
    "content_type": "application/json"
  },
  "qos": {
    "priority": 2,
    "timeout_ms": 5000,
    "idempotency_key": "get-user-12345-v1"
  }
}
```

### 9.2 成功响应示例

```json
{
  "aduib_rpc": "2.0",
  "id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "success",
  "result": {
    "user_id": "12345",
    "name": "Alice",
    "email": "alice@example.com"
  },
  "trace_context": {
    "trace_id": "0af7651916cd43dd8448eb211c80319c",
    "span_id": "c8be6b8279314442"
  },
  "metadata": {
    "timestamp_ms": 1705234567920,
    "duration_ms": 30,
    "server_id": "server-001"
  }
}
```

### 9.3 错误响应示例

```json
{
  "aduib_rpc": "2.0",
  "id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "error",
  "error": {
    "code": 4000,
    "name": "NOT_FOUND",
    "message": "User not found",
    "details": [
      {
        "type": "aduib.rpc/ResourceNotFound",
        "field": "user_id",
        "reason": "No user exists with ID '12345'"
      }
    ]
  },
  "trace_context": {
    "trace_id": "0af7651916cd43dd8448eb211c80319c",
    "span_id": "c8be6b8279314442"
  },
  "metadata": {
    "timestamp_ms": 1705234567920,
    "duration_ms": 5
  }
}
```

### 9.4 流式消息示例

```json
// 数据帧
{
  "type": "data",
  "sequence": 1,
  "payload": {
    "data": {
      "chunk": "Hello, "
    }
  },
  "timestamp_ms": 1705234567890
}

// 心跳帧
{
  "type": "heartbeat",
  "sequence": 2,
  "payload": {
    "control": {
      "ping_id": "ping-001"
    }
  },
  "timestamp_ms": 1705234567900
}

// 结束帧
{
  "type": "end",
  "sequence": 10,
  "payload": {
    "control": {
      "final": true,
      "total_count": 10
    }
  },
  "timestamp_ms": 1705234568000
}
```

---

## 10. 向后兼容性

### 10.1 v1.0 → v2.0 映射

| v1.0 字段 | v2.0 字段 | 说明 |
|-----------|-----------|------|
| `aduib_rpc: "1.0"` | `aduib_rpc: "2.0"` | 版本升级 |
| `method` | `method` | 保持不变 |
| `name` | `name` | 保持不变 |
| `data` | `data` | 保持不变 |
| `meta` | `metadata.headers` | 迁移到 headers |
| `meta.stream` | `qos.streaming` | 移到 QoS |
| `id` | `id` | 保持不变 |
| - | `trace_context` | 新增 |
| - | `metadata` | 新增结构化元数据 |
| - | `qos` | 新增 QoS |

### 10.2 兼容层实现

```python
def upgrade_v1_to_v2(v1_request: dict) -> dict:
    """将 v1 请求升级为 v2 格式"""
    v2_request = {
        "aduib_rpc": "2.0",
        "id": v1_request.get("id") or str(uuid.uuid4()),
        "method": v1_request["method"],
        "name": v1_request.get("name"),
        "data": v1_request.get("data"),
    }

    # 迁移 meta
    if meta := v1_request.get("meta"):
        v2_request["metadata"] = {
            "timestamp_ms": int(time.time() * 1000),
            "headers": {k: v for k, v in meta.items() if k not in ("stream",)},
        }
        if meta.get("stream"):
            v2_request["qos"] = {"streaming": True}

    return v2_request


def downgrade_v2_to_v1(v2_response: dict) -> dict:
    """将 v2 响应降级为 v1 格式"""
    v1_response = {
        "aduib_rpc": "1.0",
        "id": v2_response.get("id"),
        "status": "success" if v2_response.get("status") == "success" else "error",
    }

    if v2_response.get("result"):
        v1_response["result"] = v2_response["result"]

    if error := v2_response.get("error"):
        v1_response["error"] = {
            "code": error["code"],
            "message": error["message"],
            "data": error.get("details"),
        }

    return v1_response
```

---

## 11. 实施计划

### Phase 1: 核心类型 (1 周)

- [ ] 创建 `src/aduib_rpc/protocol/v2/types.py`
- [ ] 创建 `src/aduib_rpc/protocol/v2/errors.py`
- [ ] 创建 `src/aduib_rpc/protocol/v2/trace.py`
- [ ] 更新 Protobuf 定义

### Phase 2: 流式协议 (1 周)

- [ ] 创建 `src/aduib_rpc/protocol/v2/stream.py`
- [ ] 实现流式状态机
- [ ] 更新各传输层适配

### Phase 3: 兼容层 (1 周)

- [ ] 实现 v1 ↔ v2 转换
- [ ] 版本协商中间件
- [ ] 测试兼容性

### Phase 4: 迁移 (2 周)

- [ ] 更新服务端处理器
- [ ] 更新客户端传输
- [ ] 更新服务发现
- [ ] 全面测试

---

*文档版本: 1.0*
*创建日期: 2026-01-14*
