# 流式协议支持矩阵（按传输/方向/实现状态）

> 目的：统一说明 v2 流式协议（`StreamMessage`/控制面）在各传输协议上的支持情况，并明确区分：
> - ✅ **支持（Supported）**：实现完整，测试覆盖，具备稳定契约
> - 🟡 **部分支持（Partial）**：能工作但缺少关键语义/控制帧/一致性
> - ❌ **不支持（Not supported）**：协议/传输天然不具备或项目明确不提供
> - 🚧 **未实现（Not implemented yet）**：接口定义存在，但代码明确返回 UNIMPLEMENTED/NotImplemented
>
> 注：本文件描述的是**服务端实现能力**（server-side），客户端能力以对应 SDK 为准。

---

## 1. 现状矩阵（当前代码仓库）

### 1.1 按传输与流向（server / client / bidi）

| 传输 | Server-stream（服务端推送） | Client-stream（客户端推送） | Bidi（双向） | 载体/说明 |
|---|---|---|---|---|
| **REST v2 (FastAPI)** | 🟡 Partial | ❌ Not supported | ❌ Not supported | SSE `POST /aduib_rpc/v2/rpc/stream`；当前只把 `AduibRpcResponse` 逐条塞进 SSE `data:`，未统一为 v2 `StreamMessage` |
| **JSON-RPC (Starlette/FastAPI)** | 🟡 Partial | ❌ Not supported | ❌ Not supported | SSE；通过 header `DEFAULT_STREAM_HEADER=true` 开启；返回的是 JSON-RPC streaming shape，不是 v2 `StreamMessage` |
| **gRPC v2** | 🟡 Partial | 🟡 Partial | 🟡 Partial | `CallServerStream` 已实现并发送 DATA+END；`CallClientStream/CallBidirectional` 现支持但仍为简化语义 |
| **Thrift v2** | 🟡 Partial（伪流） | ❌ Not supported | ❌ Not supported | Thrift IDL 侧没有真正 streaming，本仓库用“单次返回 list[StreamMessage]”模拟（会聚合所有帧后一次性返回） |

---

## 2. 细化：v2 StreamMessage 关键能力对齐情况

> v2 spec（`docs/protocol_v2_specification.md`）中，stream 关键字段/语义包括：
> - `type`: data / heartbeat / error / end / cancel / ack
> - `sequence`: 单调递增
> - `timestamp_ms`: 事件时间戳
> - `payload`: data/error/control

### 2.1 关键字段与控制帧支持

| 传输 | DATA | END | ERROR frame | HEARTBEAT | CANCEL | ACK | sequence | timestamp_ms |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| REST v2 (SSE) | 🟡（以 response dict 形式） | ❌ | 🟡（以 response error 形式） | ❌ | ❌ | ❌ | ❌ | ❌ |
| JSON-RPC (SSE) | 🟡（JSON-RPC streaming msg） | 🟡（依赖实现，未标准化） | 🟡 | ❌ | ❌ | ❌ | ❌ | ❌ |
| gRPC v2 | ✅ | ✅ | 🟡（异常时发 ERROR frame） | ❌ | ❌ | ❌ | ✅ | ✅ |
| Thrift v2（伪流） | ✅ | ✅ | ✅ | ❌ | ❌ | ❌ | ✅ | ❌（目前固定 0） |

---

## 3. 状态定义（团队约定）

### ✅ Supported
满足：
- 数据帧与控制帧均按 spec 输出
- sequence/timestamp_ms 正确
- 可取消/可结束语义明确
- 有自动化测试覆盖（至少：data 序列、error->end、end 必达、取消语义）

### 🟡 Partial
满足部分能力，但至少存在以下一种缺失：
- 未使用标准 `StreamMessage` envelope
- 缺少 end/heartbeat/cancel/ack 等控制面
- sequence/timestamp_ms 不完整
- 缺测试护栏

### 🚧 Not implemented yet
- proto/接口定义存在，但实现明确返回 UNIMPLEMENTED/NotImplementedError

### ❌ Not supported
- 传输层/IDL 天然不支持（例如 Thrift 真双工流），且项目没有模拟方案或明确不提供

---

## 4. 目标状态（建议：以 gRPC StreamMessage 为协议标杆）

> 推荐将 **v2 StreamMessage** 作为跨传输的统一“流式消息语义层”，不同传输只负责承载：
> - gRPC：原生 stream StreamMessage
> - REST/JSON-RPC：SSE data 中承载 JSON 序列化后的 StreamMessage
> - Thrift：继续用 list[StreamMessage] 作为兼容承载（明确“伪流”的语义限制）

目标矩阵（达到 "Supported" 的最小集合）：
- REST v2：DATA/END/ERROR + sequence + timestamp_ms + heartbeat（可配置）
- JSON-RPC：同上（并逐步废弃 JSON-RPC 自己的 streaming shape，统一输出 StreamMessage JSON）
- gRPC v2：补 timestamp_ms、补 error frame（不只 abort）、补 cancel/ack（如果 spec 要求）
- Thrift v2：补 timestamp_ms；明确不支持真正流式与双向

---

## 5. 代码定位（便于追踪）
- REST v2 SSE：`src/aduib_rpc/server/protocols/rest/fastapi_app.py`、`src/aduib_rpc/server/request_handlers/rest_v2_handler.py`
- JSON-RPC SSE：`src/aduib_rpc/server/protocols/rpc/jsonrpc_app.py`
- gRPC v2：`src/aduib_rpc/server/request_handlers/grpc_v2_handler.py`
- Thrift v2：`src/aduib_rpc/server/request_handlers/thrift_v2_handler.py`

