# Protocol v2 集成审计报告（深读代码库版｜按 Phase 全覆盖｜不跑测试）

日期：2026-01-23  
覆盖范围：`src/aduib_rpc/**` + `docs/protocol_v2_*` + `tests/**`（仅静态阅读，不执行）

> 本报告不是“接口 spec 复述”，而是回答两类问题：
> 1) **文件级**：仓库里每个与 v2/enterprise 相关的业务文件，在 v2 主链路里扮演什么角色？
> 2) **阶段级**：Phase 1–11（以及 implementation_plan 的 enterprise P0/P1）哪些是“实现存在但未接入默认链路”，哪些是真的闭环？
>
> 判定维度（必须同时给出结论）：
> - **Implementation exists**：代码/类型/函数存在。
> - **Wired by default**：不用额外注入（interceptor/context_builder/config/secure context），按默认构造 server/app 就会走到。
> - **Spec/Plan semantics complete**：不仅字段存在，还能产生规定的运行时行为与错误语义。

---

## A. 执行总览：所有 transport 的“真实调用链”与默认 wiring

### A1. 共享业务执行内核：`DefaultRequestHandler`

- 文件：`src/aduib_rpc/server/request_handlers/default_request_handler.py`
- 角色：**所有 transport 最终都要落到这个 `RequestHandler` 接口（或调用方自定义实现）**。
- 关键点：
  - `DefaultRequestHandler` 支持 **server interceptors**（tenant/security/resilience/observability…）。
  - 因而 enterprise 能力的落地首先取决于：构造 `DefaultRequestHandler(interceptors=[...])` 是否发生。
- 结论：
  - **interceptor 体系是 v2 “生产化能力”真正的挂载点**。
  - 当前 repo 大量 enterprise 能力实现为 interceptor，但默认 server 构造并不会自动注入（见各 transport 的默认 wiring）。

### A2. REST FastAPI

入口 builder：`src/aduib_rpc/server/protocols/rest/fastapi_app.py::AduibRpcRestFastAPIApp`

- v2 unary：`POST /aduib_rpc/v2/rpc`
  - `AduibRpcRestFastAPIApp._handle_requests()` → `RESTV2Handler.on_message()` → `RequestHandler.on_message()`
- v2 streaming：`POST /aduib_rpc/v2/rpc/stream`（SSE）
  - `_handle_streaming_requests_v2()` → `RESTV2Handler.on_stream_message()` → `RequestHandler.on_stream_message()`
- legacy v1 REST（protobuf body）：
  - `RESTHandler.on_message/on_stream_message`（`src/aduib_rpc/server/request_handlers/rest_handler.py`）
  - 受 `ProtocolConfig.enable_legacy_v1_rest` 控制（默认不启用）

**默认 wiring 关键点**
- `AduibRpcRestFastAPIApp` 的 `context_builder` 默认值来自 JSON-RPC 领域：`src/aduib_rpc/server/protocols/rpc/jsonrpc_app.py::DefaultServerContextBuilder`
  - 该 builder 只收集 headers + stream header，不做 v2 trace/tenant/auth 提取。

### A3. JSON-RPC（Starlette/FastAPI）

入口：`src/aduib_rpc/server/protocols/rpc/jsonrpc_app.py::JsonRpcApp`

- v2-only gating：当 `ProtocolConfig.enable_legacy_jsonrpc_methods=False`，强制 JSON-RPC `method` 必须是 `rpc.v2/...`
- 适配层：`src/aduib_rpc/server/request_handlers/jsonrpc_handler.py::JSONRPCHandler`
  - 将 `request.params` 作为“内部 request”转发给 `RequestHandler`。

### A4. gRPC

- legacy gRPC：`src/aduib_rpc/server/request_handlers/grpc_handler.py::GrpcHandler`
  - inbound/outbound 通过 protobuf `RpcTask`/`RpcTaskResponse`
- gRPC v2：`src/aduib_rpc/server/request_handlers/grpc_v2_handler.py::GrpcV2Handler`
  - inbound/outbound 使用 `aduib_rpc_v2_pb2` 的 v2 message

### A5. Thrift

- legacy thrift：`src/aduib_rpc/server/request_handlers/thrift_handler.py::ThriftHandler`
- thrift v2：`src/aduib_rpc/server/request_handlers/thrift_v2_handler.py::ThriftV2Handler`

### A6. 默认 wiring 总结

- REST v2：默认启用；默认 context_builder **不具备 v2 trace/tenant/auth 执行语义**。
- JSON-RPC：默认启用；是否允许 legacy methods 取决于 `ProtocolConfig`。
- gRPC / Thrift：属于“库提供 handler/servicer，但需要调用方显式启动 server 并注册”，因此默认链路属于 **optional wiring**。
- enterprise interceptors：默认不注入（需要调用方手工传给 `DefaultRequestHandler`）。

---

## B. 文件到角色索引（v2/enterprise 相关业务文件“在 v2 的作用”）

> 这一节解决你指出的“没有涵盖所有文件、它们在 v2 的作用”。
> 不是罗列目录，而是给每类文件一个“v2 角色定义”。

### B1. v2 协议模型层（wire contract）

- `src/aduib_rpc/protocol/v2/types.py`
  - v2 envelope：`AduibRpcRequest/AduibRpcResponse`
  - trace：`TraceContext`
  - error：`RpcError/ErrorDetail/DebugInfo`
  - negotiated fields：`supported_versions/negotiated_version`
- `src/aduib_rpc/protocol/v2/errors.py`
  - error codes（ErrorCode）
  - exception→error code / error payload
  - `error_code_to_http_status` / http↔grpc 映射
- `src/aduib_rpc/protocol/v2/stream.py`
  - `StreamMessage/StreamMessageType`：v2 streaming 控制面
- `src/aduib_rpc/protocol/v2/qos.py`
  - `QosConfig`：timeout/idempotency/priority 等
- `src/aduib_rpc/protocol/v2/metadata.py`
  - content-type/compression/auth/tenant 等元信息结构（计划/企业能力映射常在此层定义）
- `src/aduib_rpc/protocol/v2/negotiation.py`
  - content-type/serializer/compression negotiator（注意：模块存在 ≠ REST server 已接入）

### B2. v2/legacy 协议适配层（transport adapters）

- REST v2：`src/aduib_rpc/server/request_handlers/rest_v2_handler.py`
  - v2 JSON envelope 解析
  - v2 method 前缀约束（`rpc.v2/`）
  - 将业务 response→HTTP JSON/SSE StreamMessage
- REST legacy：`src/aduib_rpc/server/request_handlers/rest_handler.py`
  - protobuf body 的旧 REST（与 v2 不是同一 wire contract）
- JSON-RPC：`src/aduib_rpc/server/request_handlers/jsonrpc_handler.py`
  - JSON-RPC envelope 与内部 RequestHandler 之间的桥
- gRPC legacy：`src/aduib_rpc/server/request_handlers/grpc_handler.py`
- gRPC v2：`src/aduib_rpc/server/request_handlers/grpc_v2_handler.py`
- Thrift legacy：`src/aduib_rpc/server/request_handlers/thrift_handler.py`
- Thrift v2：`src/aduib_rpc/server/request_handlers/thrift_v2_handler.py`

### B3. ServerContext / 中间件（把 wire 字段转为执行语义的关键层）

- `src/aduib_rpc/server/context.py`
  - `ServerContext` + `ServerInterceptor` 抽象
  - 所有 server-side 可观测/安全/租户等语义的挂载点
- `src/aduib_rpc/server/middleware/context_builder.py`
  - `V2ServerContextBuilder`：从 headers/body 提取 trace/tenant/auth 等写入 `ServerContext`
- `src/aduib_rpc/server/middleware/version_negotiation.py`
  - `negotiate_client_version()` / normalize_* / `VersionNegotiationInterceptor`
  - 注意：该实现存在，但默认 REST v2 入口未使用

### B4. enterprise（server-side interceptors）

- `src/aduib_rpc/server/interceptors/tenant.py`
  - TenantInterceptor：将 tenant_id 写入 context.state；并提供 TenantScope（与 core/context 的 runtime tenant 绑定呼应）
- `src/aduib_rpc/server/interceptors/security.py`
  - SecurityInterceptor：RBAC + audit + principal extraction（注意：返回的是 v1 风格 `AduibRpcError(code=403, ...)`，与 v2 ErrorCode 体系未完全统一）
- `src/aduib_rpc/server/interceptors/resilience.py`
  - ServerResilienceInterceptor：入站 rate-limit/bulkhead 守卫
  - ResilienceHandler：对执行应用 circuit breaker/fallback，并释放 bulkhead permit

### B5. runtime / 依赖注入（enterprise P0-1）

- `src/aduib_rpc/core/context.py`
  - 通过 `contextvars` 实现 per-request/per-tenant runtime 隔离（`ScopedRuntime`/`with_tenant`）
  - 与 server tenant interceptor 的闭环：tenant_id 需要被绑定成 runtime scope 才能真正隔离（目前是否接入主链路：需看 DefaultRequestHandler 是否在调用链里 enter scope）

### B6. 可观测（enterprise P1-3/Phase 9）

- `src/aduib_rpc/observability/interceptor.py`
  - ServerObservabilityInterceptor：log context 绑定 + metrics + duration_ms + audit
- `src/aduib_rpc/observability/metrics.py`
  - RpcMetrics：请求总数/耗时/错误/限流/重试等
- `src/aduib_rpc/observability/audit.py`
  - AuditLogger + sanitize_for_audit
- `src/aduib_rpc/telemetry/*`
  - OTEL setup + grpc interceptors + server interceptors

### B7. 配置系统（Phase 8）

- `src/aduib_rpc/config/dynamic.py` / `src/aduib_rpc/config/v2_config.py`
  - 动态配置来源 + ProtocolV2Config/ResilienceDynamicConfig/SecurityDynamicConfig/ObservabilityDynamicConfig
  - 注意：配置模块存在 ≠ 默认 server 链路会消费它（是否 wired 取决于 server 构造/拦截器是否读取 singleton）

### B8. 方法治理（Phase 10）

- `src/aduib_rpc/server/method_registry.py`
  - MethodRegistry/MethodInfo/VersionAwareMethodFilter
  - 与 Phase2 negotiated_version 的“联动”只有在默认链路读取 negotiated_version 并调用 filter 时才成立
- `src/aduib_rpc/rpc/methods.py`
  - MethodName.parse_compat：DefaultRequestHandler/RESTV2Handler 实际解析入口

### B9. 任务系统（enterprise P0-3 与 v2 tasks）

- `src/aduib_rpc/server/tasks/task_manager.py`
  - InMemoryTaskManager 等（DefaultRequestHandler 内置 task RPC）
- `src/aduib_rpc/server/tasks/distributed.py`
  - DistributedTaskManager + RedisTaskStore（priority queue / subscriber 等）
- `src/aduib_rpc/server/tasks/v2.py`
  - v2 task API 适配/实现（需检查 DefaultRequestHandler 是否走到）

### B10. 服务发现/负载均衡/健康检查（enterprise P0-5）

- `src/aduib_rpc/discover/health/*`：health checker + health status
- `src/aduib_rpc/discover/multi_registry.py`：MultiRegistry 聚合
- `src/aduib_rpc/discover/load_balance/*`：LB 策略
- `src/aduib_rpc/discover/entities/v2.py`：v2 service/method descriptor（与 Phase10 方法治理相关）

---

## C. Phase-by-Phase 审计（按 checklist/plan，全覆盖到“任务点→代码落点→调用链→wiring→测试证据”）

> 注：以下每个 Phase 都会给出：
> - 任务点（来自 `docs/protocol_v2_checklist.md` / `docs/protocol_v2_implementation_plan.md`）
> - 代码落点（关键文件/符号）
> - 覆盖到哪些 transport（REST/JSON-RPC/gRPC/Thrift）
> - 默认 wiring 结论
> - 测试证据是否真的证明“主链路接入”
> - 文档偏差点（如果 checklist 声称完成但代码/测试不支持）

### Phase 1 — REST v2 HTTP 语义（spec 5.3）
- 任务：error→HTTP status；SSE 建链错误必须非 200
- 代码落点：
  - `protocol/v2/errors.py::error_code_to_http_status`
  - `server/protocols/rest/fastapi_app.py`（v2 handler 出站 status_code）
  - `server/request_handlers/rest_v2_handler.py`（错误映射/返回体结构）
- transport 覆盖：REST v2（为主）
- 默认 wiring：✅（REST v2 默认生效）
- 测试证据：`tests/test_rest_v2_http_status_mapping.py`（Wiring）

### Phase 2 — 版本协商（spec 2.2）
- 任务：supported_versions→negotiated_version；无交集→UNSUPPORTED_VERSION
- 代码落点：
  - `protocol/v2/types.py`（字段）
  - `protocol/compatibility.py::negotiate_version`（算法）
  - `server/middleware/version_negotiation.py`（interceptor 与 normalize_*）
  - `config/v2_config.py::ProtocolV2Config.supported_versions`（server supported versions 的潜在来源）
- transport 覆盖：理论上可用于所有 transport，但必须在入站处执行
- 默认 wiring：❌（REST v2 默认不会协商；JSON-RPC/gRPC/Thrift 也未见自动协商）
- 测试证据审计：
  - `tests/test_rest_v2_version_negotiation.py` 的 E2E 是 handler 人工回填 negotiated_version，证明的是“透传”而非“协商闭环”。
- checklist 偏差点：`docs/protocol_v2_checklist.md` 声称存在 `VersionNegotiator.negotiate()`，但代码中无 `VersionNegotiator` 符号；实际实现是 `negotiate_client_version`/`negotiate_version`。

### Phase 3 — Streaming 控制面（spec 4.x）
- 任务：StreamMessage(type/seq/timestamp/payload)；error→end；heartbeat；cancel/ack 决策
- 代码落点：
  - `protocol/v2/stream.py`
  - REST：`server/request_handlers/rest_v2_handler.py` + `server/protocols/rest/fastapi_app.py`
  - gRPC v2：`server/request_handlers/grpc_v2_handler.py`（但 timestamp_ms=0、错误走 abort）
  - Thrift v2：`server/request_handlers/thrift_v2_handler.py`（伪流、timestamp_ms=0）
- 默认 wiring：REST ✅；gRPC/Thrift optional；语义完整度 🟡
- 测试证据：
  - REST：`tests/test_rest_v2_stream_protocol.py`（shape/Wiring）
  - gRPC：`tests/test_grpc_v2_smoke.py` 仅 unary；streaming 语义未证明

### Phase 4 — trace_context/metadata 执行语义（spec 3.4/3.5）
- 任务：解析 trace_context 并注入 OTEL；metadata→ServerContext；响应回填 trace
- 代码落点：
  - `server/middleware/context_builder.py::V2ServerContextBuilder`
  - `telemetry/server_interceptors.py`（OTEL server side）
  - `server/interceptors/tenant.py`（tenant_id→context.state）
  - `core/context.py`（with_tenant runtime 隔离）
- 默认 wiring：❌（REST v2 默认 builder 不是 V2ServerContextBuilder；interceptors 也默认不注入）
- 测试证据审计：
  - checklist 引用 `tests/test_phase4.py` 作为 Phase4 证据，但该文件是 CLI/代码生成/DX，不是 trace/metadata。
  - 真正的“REST v2 入站 trace/metadata” wiring tests 在 repo 中未见（Not present）。

### Phase 5 — QoS（spec 3.1）
- 任务：timeout_ms 硬超时；idempotency_key 去重缓存；priority；（retry 是否 server-side）
- 代码落点：
  - `protocol/v2/qos.py::QosConfig`
  - `server/qos/handler.py::QosHandler/IdempotencyCache`
- 默认 wiring：❌（DefaultRequestHandler 未调用 QosHandler；所有 transport 都不会自动生效）
- 测试证据：`tests/test_qos_handler.py` 是 module test，不是 server 主链路接入证明。

### Phase 6 — content-type/accept/compression（spec 3.5）
- 任务：serializer/compression negotiation；响应回写
- 代码落点：
  - `protocol/v2/negotiation.py`（negotiator）
  - `protocol/v2/metadata.py`（content/compression 字段）
  - client：`client/transports/rest.py`（header 发送）
- 默认 wiring：🟡（模块存在；但 REST v2 server 入口仍固定 JSON 解析，未看到 “按 negotiated serializer 解码 bytes body” 的闭环）
- 测试证据：`tests/test_negotiation.py`（module）

### Phase 7 — 错误码体系 + debug gating（spec 5.x）
- 任务：exception 映射到 ErrorCode；debug 仅在 dev/test
- 代码落点：
  - `protocol/v2/errors.py`（mapping + gating）
  - `exceptions.py`（RpcException hierarchy）
  - `utils/error_handlers.py::exception_to_error`（REST v1/v2 与 legacy 兼容）
- 默认 wiring：REST v2 ✅（RESTV2Handler 使用 exception_to_error）；其他 transport 的错误路径要分别审计
- 测试证据：`tests/test_phase7_error_mapping.py`（module + mapping）；`tests/test_rest_v2_error_shape.py`（若涉及 ASGI 则为 wiring）

### Phase 8 — 动态配置（enterprise P1-2）
- 任务：动态 config source；ProtocolV2Config/Resilience/Security/Observability hot reload
- 代码落点：
  - `config/dynamic.py`、`config/v2_config.py`
- 默认 wiring：🟡（配置系统存在，但是否被 server interceptors/handlers 读取取决于 wiring；目前未见默认注入）
- 测试证据：`tests/test_phase8_dynamic_config.py`（module/hot reload 行为）

### Phase 9 — 可观测性全链路（enterprise P0/P1）
- 任务：log context(tenant/trace/request)；metrics；duration_ms；audit
- 代码落点：
  - `observability/interceptor.py::ServerObservabilityInterceptor`
  - `observability/metrics.py` / `observability/audit.py`
- 默认 wiring：🟡 optional（需要注入到 DefaultRequestHandler.interceptors 才生效）
- 测试证据：`tests/test_phase9_observability.py` 多为手工构造 interceptor+context 的行为验证，不等价“REST v2 默认接入”。

### Phase 10 — 方法治理/版本化（enterprise P1-4）
- 任务：rpc.v2/{service}/{handler} 解析；MethodRegistry；按 negotiated_version 过滤
- 代码落点：
  - `server/method_registry.py`
  - `rpc/methods.py::MethodName.parse_compat`
- 默认 wiring：🟡 partial
  - 方法解析在 DefaultRequestHandler 中真实使用
  - 但“按 negotiated_version 联动过滤”的闭环依赖 Phase2 negotiated_version 的默认接入，目前缺失
- 测试证据：`tests/test_phase10_method_registry.py`（module）

### Phase 11 — TLS/mTLS + 身份闭环
- 任务：server-side TLS config；principal 从 peer cert 提取并写入 ServerContext；scheme=mtls 强校验
- 代码落点：
  - `security/mtls.py`（ServerTlsConfig / principal extraction / verify_mtls_connection / sanitize_cert_for_audit）
  - server transport 是否启用 secure port：需要检查 `discover/service/*_service_factory.py`（计划中指出当前多为 insecure）
- 默认 wiring：🟡（能力模块存在；transport 默认未启用 mTLS）
- 测试证据：`tests/test_phase11_mtls.py`（module）

---

## D. 最高优先级“闭环缺口”清单（从主链路可用角度排序）

> 你关心的是“是否真正接入主链路”。按现在代码现实，闭环缺口主要集中在：Phase2/4/5/6/9/11 的 wiring。

1) Phase 4：REST v2 默认 context_builder 不解析 trace/tenant/auth（应切到 V2ServerContextBuilder 或等价机制）
2) Phase 2：版本协商没有在任一默认 transport 入站处执行（interceptor 存在但没接）
3) Phase 5：QoS 未被 DefaultRequestHandler 包装（模块存在但无调用点）
4) Phase 6：serializer/compression negotiator 存在，但 REST v2 server 没走 bytes body decode/encode 的闭环
5) Phase 9：observability interceptor 未默认注入（导致“全链路闭环”仅在 module test 层成立）
6) Phase 11：mTLS server-side 启用与 principal 注入未形成默认闭环（多停留在能力模块与单测）

---

## E. 文档偏差（checklist/plan 与代码现实的冲突点）

- checklist Phase2 指向 `VersionNegotiator.negotiate()`，代码层无该符号；实际实现分散在 `protocol/compatibility.py` 与 `server/middleware/version_negotiation.py`。
- checklist Phase4 将 `tests/test_phase4.py` 作为 trace/metadata 证据，但文件内容是 CLI/代码生成/DX。
- 多个 Phase 的“完成证明”主要依赖 module tests：这些证明不了默认主链路接入。

---

## F. 建议你把报告当作后续改造的验收基线

后续如果要“真正完成 Phase 1–11”，建议每个 Phase 至少补一条 **REST v2 E2E wiring test**（ASGITransport 即可），用来证明默认构造 `AduibRpcRestFastAPIApp(DefaultRequestHandler()).build()` 真的走到了该 phase 的执行语义。

