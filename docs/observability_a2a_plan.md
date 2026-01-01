# 可观测（OpenTelemetry）+ A2A 集成方案

本文面向 `aduib-rpc` 仓库（Python 多协议 RPC + Rust SDK），给出一套**可落地**的“可观测 + A2A”集成方案。

## 1. 目标与范围

### 目标
- 服务端/客户端具备**分布式追踪**能力：每次 RPC 请求都有 trace/span，能够跨服务串起来。
- 关键维度可查询：`rpc.method`、`rpc.request_id`、`transport`、耗时、错误码等。
- A2A 能力作为可选模块开启（extras），并在服务发现/启动侧保持一致用法。

### 非目标
- 不在本方案中强制引入复杂 metrics/日志采集；先把 tracing 跑通。

---

## 2. 依赖与启用方式

`pyproject.toml` 已提供 extras：
- `aduib-rpc[telemetry]`
- `aduib-rpc[a2a]`

建议安装：

```bash
pip install "aduib-rpc[telemetry,a2a]"
```

---

## 3. OpenTelemetry（可观测）落地设计

### 3.1 总体策略
- 核心库不硬依赖 otel：所有对 otel 的 import 都用 `try/except` 包裹。
- 通过一个统一入口 `aduib_rpc.telemetry.configure_telemetry()` 完成 SDK 配置与常见自动埋点。
- 通过**拦截器**来实现：
  - Client：注入 trace context 到 HTTP headers（REST/JSON-RPC）。
  - Server：从 headers 提取上下文，创建 span，并在请求完成时结束 span。

### 3.2 关键属性（attributes）约定
- `rpc.method`
- `rpc.request_id`
- `rpc.transport`（建议后续补）
- `rpc.status`（success/error）

这能让 traces 按 RPC 维度聚合与过滤。

### 3.3 代码位置
- `src/aduib_rpc/telemetry/`：otel 集成模块（可选依赖安全导入）
  - `setup.py`：`configure_telemetry()`
  - `interceptors.py`：`OTelClientInterceptor`
  - `server_interceptors.py`：`OTelServerInterceptor` + `end_otel_span()`

### 3.4 服务器端如何启用
- 在构建 server app 前调用 `configure_telemetry(TelemetryConfig(...))`
- 在你的 `DefaultRequestHandler(interceptors=[...])` 注入 `OTelServerInterceptor()`

示例（伪代码）：

```python
from aduib_rpc import TelemetryConfig, configure_telemetry
from aduib_rpc.telemetry.server_interceptors import OTelServerInterceptor
from aduib_rpc.server.request_handlers.default_request_handler import DefaultRequestHandler

configure_telemetry(TelemetryConfig(service_name="aduib-rpc-server"))
handler = DefaultRequestHandler(interceptors=[OTelServerInterceptor()])
```

### 3.5 客户端如何启用
- 在 `AduibRpcClientFactory.create_client(..., interceptors=[...])` 里加入 `OTelClientInterceptor()`

---

## 4. A2A 集成方案

仓库已存在 A2A 服务工厂：
- `src/aduib_rpc/discover/service/a2a_service_factory.py`
- `src/aduib_rpc/discover/service/service_factory.py`（包含 is_a2a_installed 探测）

### 4.1 建议的入口与约定
- 在 docs 里明确：
  - `aduib-rpc[a2a]` 安装后，才能使用 `A2aServiceFactory`
  - 未安装时 `is_a2a_installed=False`，应给出明确错误提示

### 4.2 可观测 + A2A 如何组合
- A2A HTTP/Starlette/FastAPI app 启动前同样调用 `configure_telemetry()`
- 如果 A2A 内部也使用 httpx/grpc，otel instrumentation 将自动覆盖

---

## 5. 推荐的下一步（增强项）

1) 统一把 `rpc.request_id`（以及 trace id）回填到响应 header / response meta

2) 为 gRPC client 增加专用 interceptor（metadata 注入 traceparent）

3) 增加 metrics：
- `rpc_server_requests_total{method,status}`
- `rpc_server_duration_ms_bucket{method}`

4) 增加一个 `examples/`：
- `examples/otel_server.py`
- `examples/otel_client.py`
