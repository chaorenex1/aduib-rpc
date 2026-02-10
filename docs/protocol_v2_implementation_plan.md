# Protocol v2 实现修补计划（面向完整功能落地）

> 目标：把当前 v2（尤其是 REST FastAPI 路径）从“能跑通”提升到与 `docs/protocol_v2_specification.md` 对齐的**完整实现**。
> 原则：不接受“最小改动但不实现完整功能”的修补方式；每个阶段都要有明确验收标准与测试护栏。

---

## 0. 范围与现状（基线）

### 0.1 当前已具备（摘录）
- REST v2 端点：`POST /aduib_rpc/v2/rpc` 与 `POST /aduib_rpc/v2/rpc/stream`（SSE）。
- v2 envelope：`AduibRpcRequest/AduibRpcResponse`（Pydantic v2 模型）可解析/序列化。
- v2 method 前缀约束：`rpc.v2/`。
- 基础错误 envelope：`status=error` + `error.code/name/message`。

### 0.2 主要缺口（摘录）
- HTTP 状态码映射（spec 5.3）目前几乎全部返回 200。
- 版本协商（spec 2.2）未落地。
- Streaming 控制协议（spec 4.x）未落地：缺少 `StreamMessage.type/sequence/timestamp_ms`，缺少 `heartbeat/end/cancel/ack` 等。
- `trace_context/metadata/qos` 字段“存在但未产生执行语义”。
- content-type / accept / compression 协商未实现。
- 错误码标准化体系（spec 5.x）与 debug/details 策略不完整。

---

## 1. 交付策略（强约束）

### 1.1 开发流程
- **测试先行**：每个阶段先加测试，再实现（红->绿）。
- **不做半实现**：字段存在但不生效（例如 qos/trace）视为未完成。
- **变更可回滚**：API 变更（如 HTTP status）需要更新现有测试与文档，且明确兼容策略。

### 1.2 验收定义（Definition of Done）
每个阶段交付必须满足：
1) 单测/集成测试覆盖主路径 + 关键边界；
2) 与 spec 对齐（或在本计划中明确记录“偏离点/原因/替代方案”）；
3) CI/本地全量测试通过。

---

## 2. 阶段计划与任务列表

> 建议按顺序推进：先补强“语义与可观测性”（HTTP/错误/版本），再补“流式协议控制面”，再补“执行语义”（trace/metadata/qos），最后补“序列化与压缩”。

### Phase 1 — REST v2 HTTP 语义完整化（对应 spec 5.3）
**目标**：REST v2 不再“所有错误都 200”。按错误码段/语义返回正确 HTTP status，同时保持 v2 envelope。

任务：
- [ ] 设计并实现 `RpcError.code -> HTTP status` 映射（严格对齐 spec 5.3）。
- [ ] 调整 REST v2 返回值通路：
  - `RESTV2Handler.on_message()` 返回（body, http_status）或返回一个带 status 的结构。
  - `fastapi_app.py::_handle_requests()` 读取并设置 `JSONResponse(status_code=...)`。
- [ ] SSE 建链阶段的错误（请求不合法/版本不支持/content-type 不支持）必须返回非 200（直接 HTTP 失败），不能只在 SSE data 中塞错误。
- [ ] 增加测试：
  - invalid envelope -> 400
  - method 非 v2 -> 400（或按 spec）
  - handler 抛内部异常 -> 500
  - 限流/过载 -> 429（需要可触发路径或 mock）

交付物：
- 新的测试文件：`tests/test_rest_v2_http_status_mapping.py`
- 文档更新：说明 HTTP status 与 envelope 的对应关系

---

### Phase 2 — 版本协商（对应 spec 2.2）
**目标**：支持 `supported_versions`，返回 `negotiated_version`；不支持版本时返回标准错误 + 正确 HTTP status。

任务：
- [ ] 落地协商字段：
  - request 支持 `supported_versions: list[str] | None`
  - response 支持 `negotiated_version: str | None`
- [ ] 协商策略实现：
  - client 提供 supported_versions：与 server 支持集取交集，选择最高；
  - client 未提供：以 `aduib_rpc` 为准或走默认策略（需与 spec 一致）；
  - 无可用版本：`UNSUPPORTED_VERSION`。
- [ ] 增加测试：`tests/test_rest_v2_version_negotiation.py`

---

### Phase 3 — Streaming 协议“完整控制面”（对应 spec 4.x）
**目标**：SSE 返回不再是任意 dict，而是严格的 `StreamMessage` 序列，并实现控制帧语义。

任务：
- [ ] 定义并实现 `StreamMessage` 输出格式：
  - `type`: data|partial|heartbeat|error|end|cancel|ack
  - `sequence`: 单调递增
  - `timestamp_ms`: 毫秒时间戳
  - `payload`: data/error/control
- [ ] 正常结束：必须发送 `end` 帧。
- [ ] 异常：发送 `error` 帧后必须发送 `end` 帧。
- [ ] heartbeat：连接空闲时按配置发送（若 spec 强制则必须实现）。
- [ ] cancel/ack 语义：根据 spec 明确客户端如何发送。
  - 若维持单向 SSE：需要实现“断连即 cancel”并在 handler 层可感知。
  - 若 spec 需要显式 cancel：新增控制端点或切换到 WebSocket（需要在计划中二选一落地）。
- [ ] 增加测试：`tests/test_rest_v2_stream_protocol.py`
  - 至少验证：sequence、end 帧、error->end、heartbeat（若启用）

---

### Phase 4 — trace_context / metadata 的执行语义（对应 spec 3.4/3.5）
**目标**：链路追踪/上下文/鉴权信息不再只是字段，而是进入服务端上下文与观测系统。

任务：
- [ ] trace_context 传播：
  - 从 envelope 解析并注入 OTEL span context
  - 在响应中回填 trace_context（最少 trace_id/span_id）
- [ ] metadata 注入 ServerContext：
  - tenant_id/principal/roles/headers（敏感信息脱敏）
  - auth（scheme/credentials）实现可插拔鉴权接口（默认 no-op）
- [ ] 增加测试：
  - `tests/test_rest_v2_trace_propagation.py`
  - `tests/test_rest_v2_metadata_to_context.py`

---

### Phase 5 — QoS 完整落地（对应 spec 3.1 qos + 运行语义）
**目标**：timeout/retry/priority/idempotency_key 等影响实际执行路径。

任务：
- [ ] timeout_ms：服务端执行必须硬超时（`asyncio.wait_for` 或等价机制），并返回标准超时错误 + HTTP status。
- [ ] retry：明确是否 server-side retry；若 spec 要求则实现，仅对幂等请求启用。
- [ ] idempotency_key：实现请求去重缓存（内存实现 + 可插拔后端接口），包含 TTL。
- [ ] priority：如果存在 worker/队列/并发池，进行优先级调度；否则至少在上下文中暴露并预留 hook。
- [ ] 增加测试：timeout、idempotency、retry（若实现）

---

### Phase 6 — content-type / accept / compression（对应 spec 3.5）
**目标**：支持多种序列化与压缩协商，REST v2 不仅能 JSON。

任务：
- [ ] content_type/accept 协商：JSON/MSGPACK/PROTOBUF/AVRO（按 spec 优先级规则）。
- [ ] chosen content-type 回写到响应 metadata 或 header。
- [ ] compression：gzip/zstd/lz4 支持（按 spec）；请求/响应协商与 header 设置。
- [ ] 增加测试：msgpack roundtrip、gzip response 可解压、协商失败返回标准错误。

---

### Phase 7 — 标准错误码体系与 debug/details 策略（对应 spec 5.x）
**目标**：错误码/错误名/HTTP status/可重试语义统一；debug 不泄漏生产信息。

任务：
- [ ] 建立统一错误码表（1000-6999 分段）：
  - code/name/default_message/http_status/retryable/log_level
- [ ] `exception_to_error()` 全面对齐：
  - ValidationError -> INVALID_MESSAGE/INVALID_PARAMS（可区分字段/原因）
  - method 不合法 -> INVALID_METHOD
  - service/method 不存在 -> NOT_FOUND
  - auth -> UNAUTHORIZED/FORBIDDEN
  - timeout -> TIMEOUT
  - internal -> INTERNAL
- [ ] debug 字段 gating：dev 环境返回 stack_trace；prod 环境不返回。
- [ ] 增加测试：覆盖关键异常到标准错误的映射。

---

## 3. 里程碑与时间盒（建议）
- M1：Phase 1 + Phase 7（HTTP + 错误体系）
- M2：Phase 2（版本协商）
- M3：Phase 3（Streaming 控制面）
- M4：Phase 4（trace/metadata 执行语义）
- M5：Phase 5（QoS）
- M6：Phase 6（序列化/压缩）

---

## 4. 风险与决策点

### 4.1 SSE 与 cancel/ack 的协议承载
- 若 spec 强依赖双向控制（ack/cancel），SSE 可能不足，需要：
  1) 新增控制端点；或
  2) 引入 WebSocket 作为 v2 stream 的推荐承载。
- 本计划要求在 Phase 3 明确二选一并落地，不接受“先留着以后再说”。

### 4.2 兼容性
- 当前测试断言 REST 错误也 200。Phase 1 会改变该行为，需要同步更新测试与文档。

---

## 5. 追踪
- Spec：`docs/protocol_v2_specification.md`
- Streaming support matrix（现状与目标定义）：`docs/streaming_support_matrix.md`
- 主要实现入口：
  - `src/aduib_rpc/server/protocols/rest/fastapi_app.py`
  - `src/aduib_rpc/server/request_handlers/rest_v2_handler.py`
- 相关测试：`tests/test_rest_v2_*`

---

## 6. Enterprise 集成叠加（将未实现内容合并到 v2 路线图）

> 本节以 `docs/enterprise_refactoring_plan.md` 为输入，抽取其中**尚未在当前代码里完整落地**且会影响 v2 协议“生产可用”的能力，叠加到本计划中。
>
> 说明：enterprise 方案涵盖面很大（可靠性/观测/安全/扩展/开发体验），其中一部分在仓库中**已经有实现雏形**（例如 `core/context.py`、`resilience/*`、`server/interceptors/security.py`、`discover/health/*`、`observability/logging.py`），但多数仍缺少：
> - 与 v2 协议字段（metadata/qos/trace）的一致性映射
> - 服务端实际执行语义（并发、限流、熔断、审计、健康检查、任务持久化）
> - 测试与行为契约（DoD）

### 6.1 对照清单：enterprise P0/P1/P2 与当前实现状态

#### P0（必须在 v2 生产化前完成）
- **P0-1 Runtime 依赖注入/多租户隔离**
  - enterprise 诉求：消除全局 runtime 单例，支持 per-tenant/per-request 隔离。
  - 当前实现：已存在 `src/aduib_rpc/core/context.py`（contextvars + ScopedRuntime + with_tenant）。
  - 缺口（需要补齐）：
    - [ ] 将 v2 `metadata.tenant_id` 与运行时 `RuntimeConfig.tenant_id` 打通（server-side 请求入口绑定 tenant scope）。
    - [ ] 将 ServerContext 与运行时 scope 打通（请求处理链路中可获取 current runtime，避免全局污染）。
    - [ ] 增加测试：并发两租户请求互不污染（服务注册、拦截器、credentials_provider 等）。

- **P0-2 熔断/限流/弹性模式**
  - enterprise 诉求：避免级联故障（熔断、限流、重试、舱壁、降级）。
  - 当前实现：`src/aduib_rpc/resilience/*` 已具备（RateLimiter/CircuitBreaker/RetryExecutor/Bulkhead/Fallback）。
  - 缺口（需要补齐）：
    - [ ] 服务端入站路径缺少 resilience 执行（目前主要是 client middleware）；需要在 server handler 侧执行 rate limit / bulkhead / circuit breaker（按 service/method/tenant 维度）。
    - [ ] 与 v2 spec 对齐：把限流/熔断/资源耗尽映射到 v2 标准错误码（Phase 7）与 HTTP status（Phase 1），并回填 `ResponseMetadata.rate_limit`（spec 3.6）。
    - [ ] 增加测试：触发 RateLimitedError -> HTTP 429 + v2 error + rate_limit metadata。

- **P0-3 分布式任务管理器**
  - enterprise 诉求：任务持久化、多 worker、订阅、重试、优先级。
  - 当前实现：服务端存在 `InMemoryTaskManager`，并在 `DefaultRequestHandler` 内置 `task/submit/status/result/subscribe`。
  - 缺口（需要补齐）：
    - [ ] 引入可插拔 TaskStore（InMemory/Redis）与 `DistributedTaskManager`（或等价实现），并替换/扩展现有 task_manager。
    - [ ] 与 v2 proto/spec 对齐：TaskService（Submit/Query/Cancel/Subscribe）行为一致（尤其 Subscribe 的流式事件格式，应与 Phase 3 的 StreamMessage 对齐）。
    - [ ] 增加测试：任务重启恢复（针对 Redis store 可用“可选集成测试”方式实现）、任务并发与取消、订阅事件序列。

- **P0-4 统一异常体系**
  - enterprise 诉求：标准错误码 + 统一转换工具。
  - 当前实现：已有 `src/aduib_rpc/exceptions.py`（RpcException + 多类错误码段），并且 `exception_to_error()` 已在 RESTV2Handler 使用。
  - 缺口（需要补齐）：
    - [ ] 将 enterprise 错误码段与 v2 spec 5.x 彻底对齐（Phase 7 的“统一错误码表”应以 `exceptions.py` 为唯一来源，避免重复体系）。
    - [ ] 统一 server/client 的异常映射与可重试语义（配合 QoS retryable_codes）。

- **P0-5 服务发现健康检查**
  - enterprise 诉求：不把流量路由到不健康实例。
  - 当前实现：`src/aduib_rpc/discover/health/*` 已存在 health checker + health-aware registry。
  - 缺口（需要补齐）：
    - [ ] 将健康状态写入 v2 `ServiceInstance.health/last_health_check_ms`（proto 中已有字段）。
    - [ ] registry 的负载均衡选择必须只选 healthy（或 degraded 策略可配置）。
    - [ ] 增加测试：实例变为 unhealthy 后不会被选中；恢复后可重新选中。

- **P0-6 mTLS（传输层身份与加密）**
  - enterprise 诉求：mTLS + RBAC + 审计日志，形成可信身份链路。
  - 当前实现（已有雏形）：
    - `src/aduib_rpc/security/mtls.py` 提供了 client-side `TlsConfig/create_ssl_context` 与 `TlsVerifier`（证书 CN/SAN/Issuer 校验）。
    - v2 模型/Proto 已有 `AuthScheme.MTLS` 与 `RequestMetadata.auth.scheme`。
  - 缺口（需要补齐）：
    - [ ] **服务端传输层**：
      - gRPC server 目前在 `discover/service/*_service_factory.py` 使用 `add_insecure_port`，未提供 `add_secure_port` + server cert + client cert verification（mTLS）。
      - REST/JSONRPC（uvicorn）未提供 TLS/mTLS 的 ssl context 注入与强制 client cert 校验。
    - [ ] **身份提取**：从 peer certificate 提取 principal（CN/SAN/URI）并写入 `ServerContext.state`，与 `SecurityInterceptor` 的 principal/roles 体系打通。
    - [ ] **协议一致性**：
      - 在 v2 `RequestMetadata.auth.scheme=mtls` 时，服务端必须校验连接确实是 mTLS（否则返回 UNAUTHENTICATED）。
      - 响应/审计日志中记录证书指纹/subject（脱敏策略明确）。
    - [ ] **测试**：至少覆盖 gRPC mTLS 的互通测试（证书齐全成功/缺少客户端证书失败/证书不被信任失败）。

#### P1（建议与 v2 Phase 同步推进，避免后补造成破坏性变更）
- **P1-1 协议版本硬编码**：已在 v2 计划 Phase 2（版本协商）覆盖。
- **P1-2 配置中心集成**：当前 v2 计划未覆盖（见新增 Phase 8）。
- **P1-3 日志结构化不完整**：当前仓库已有 `observability/logging.py`，但需要和 v2 trace/tenant/request_id 打通（Phase 4 + 新增 Phase 9）。
- **P1-4 API 版本管理**：需要把 `MethodName`/methods registry 增强为“版本化方法定义”，并与 v2 method 规范/协商绑定（新增 Phase 10）。
- **P1-5 Thrift 客户端未实现**：属于“传输对称性”，不直接阻塞 REST v2，但会影响 enterprise 互操作（可作为扩展里程碑）。

#### P2（开发体验类）
- CLI/文档/代码生成器：与 v2 协议落地相关，但不阻塞核心协议正确性；建议放入后续 Roadmap。

---

### 6.2 在现有 Phase 1-7 上的叠加点（需要把 enterprise 诉求落到协议语义）

- **映射到 Phase 1（HTTP 语义）**
  - [ ] 资源耗尽/限流/熔断必须返回正确 HTTP status（429/503 等）并携带 v2 error。
  - [ ] SSE 建链错误必须在 HTTP 层失败（同 Phase 1 要求）。

- **映射到 Phase 3（Streaming 协议）**
  - [ ] Task subscribe / long task / server stream 必须使用统一 StreamMessage（data/error/end/heartbeat）。
  - [ ] cancel/ack 的承载决策必须覆盖“任务订阅取消”“客户端断连”场景。

- **映射到 Phase 4（trace/metadata 执行语义）**
  - [ ] `metadata.tenant_id/auth` 必须进入 ServerContext + Runtime scope，并驱动 RBAC/audit。
  - [ ] `trace_context` 必须驱动 structured logging 的 trace_id/span_id，并和 OTEL 一致。

- **映射到 Phase 5（QoS）**
  - [ ] `qos.timeout_ms` 必须与任务执行、普通请求执行一致。
  - [ ] `qos.retry` 的 retryable_codes 必须与 Phase 7 的“标准错误码表”一致。
  - [ ] `qos.priority` 与任务优先级/worker 调度一致。

- **映射到 Phase 7（错误码体系）**
  - [ ] enterprise resilience/security/discovery/task 的异常都必须映射为 v2 标准 RpcError（code/name/message/details/debug）。

---

### 6.3 新增 Phase（enterprise 未覆盖到 v2 计划但必须补齐的能力）

#### Phase 8 — 配置中心与动态配置（enterprise P1-2）
**目标**：关键协议/韧性/安全/观测配置可动态更新，避免重启与硬编码。

任务：
- [ ] 设计 ConfigProvider 接口（本地文件/环境变量/Nacos 等可插拔）。
- [ ] 将以下配置接入动态配置：
  - v2 支持版本列表、content-type/压缩开关
  - resilience（rate limit/circuit breaker/bulkhead/retry）参数
  - security（rbac_enabled/audit_enabled/anonymous_methods/require_auth）
  - observability（log format、采样率、指标开关）
- [ ] 增加测试：配置热更新能改变行为（至少 1-2 个代表性开关）。

#### Phase 9 — 可观测性“全链路闭环”（enterprise P0/P1：日志+指标+追踪一致）
**目标**：structured logging + metrics + tracing 在 v2 协议字段驱动下形成闭环，可用于生产排障。

任务：
- [ ] 统一 log context keys：tenant_id / trace_id / request_id（已有实现，但需在 server 请求入口注入）。
- [ ] 指标：补齐 server-side RPC 指标（请求总数、耗时、错误码、限流/熔断状态等），并与 ResponseMetadata.duration_ms 对齐。
- [ ] 审计日志：security interceptor 的 AuditEvent 必须包含 request_id/method/tenant/principal，并确保敏感字段脱敏。
- [ ] 增加测试：至少验证 1 条请求会写入 log context + metrics 计数 + trace 回填。

#### Phase 10 — API 版本管理与方法注册治理（enterprise P1-4）
**目标**：方法定义可版本化、可废弃、可发现，避免 method 解析规则与文档分裂。

任务：
- [ ] 统一 method 规范：`rpc.v2/{service}/{handler}` 的解析/规范化、别名策略、deprecated 标记。
- [ ] 方法注册中心增加“版本/弃用/幂等/流式能力”描述（可复用 proto 中 `MethodDescriptor`）。
- [ ] 与版本协商联动：不同 negotiated_version 下允许的方法集合不同。
- [ ] 增加测试：
  - deprecated 方法返回明确错误/警告（按 spec）
  - method 解析与注册一致（跨 transport 一致）

#### Phase 11 — 传输安全（TLS/mTLS）与身份链路闭环（enterprise：安全性 P1）
**目标**：让“加密 + 双向认证 + 身份抽取 + RBAC + 审计”成为可配置、可测试、跨传输一致的能力。

任务：
- [ ] 统一 TLS 配置模型：
  - 复用/扩展 `security/mtls.py::TlsConfig`，补充 server-side（server cert/key、client_ca、require_client_cert）。
  - 支持按 TransportScheme 分别配置（HTTP/HTTPS、gRPC/GRPCS）。
- [ ] gRPC server 改造：
  - 支持 `add_secure_port`，加载 server cert/key，开启 client cert 验证（mTLS）。
  - 将 peer cert 信息注入 `ServerContext`（用于 SecurityInterceptor/RBAC）。
- [ ] REST/JSONRPC server 改造：
  - uvicorn 启动支持 ssl context（HTTPS）
  - 若启用 mTLS：强制客户端证书，且在请求上下文中可读取证书信息（用于 principal extraction）。
- [ ] 协议层对齐：
  - 当 `RequestMetadata.auth.scheme == mtls`：必须校验当前传输为 mTLS，否则返回 UNAUTHENTICATED。
  - 定义“证书 -> Principal”的映射规则（CN/SAN/URI -> principal.id/type/roles），并可配置。
- [ ] 审计与脱敏：
  - 审计日志记录证书 subject/issuer/serial/sha256 指纹（脱敏或哈希）。
  - 严禁记录私钥、完整证书链等敏感材料。
- [ ] 测试：
  - `tests/test_grpc_mtls_handshake.py`：mTLS 成功/失败矩阵
  - `tests/test_rest_https_mtls.py`（可选集成）

---

## 7. 更新后的里程碑建议（叠加 enterprise 后）
- M1：Phase 1 + Phase 7（HTTP + 错误体系）
- M2：Phase 2 + Phase 10（版本协商 + 方法版本治理）
- M3：Phase 3（Streaming 控制面，包含 task subscribe 统一）
- M4：Phase 4 + Phase 9（trace/metadata 执行语义 + 观测闭环）
- M5：Phase 5 + Phase 8（QoS 语义 + 动态配置）
- M6：Phase 6（序列化/压缩）
- M7：Phase 11（TLS/mTLS + 身份链路闭环）
