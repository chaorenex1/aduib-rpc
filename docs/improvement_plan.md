# Aduib RPC 仓库改进方案（Roadmap）

> 目标：在不破坏现有 API 的前提下，提升**可维护性、可测试性、发布一致性与文档可读性**，并让 Python + Rust SDK 的开发体验更顺滑。

## 0. 当前仓库识别（基于现状的简要画像）

- 这是一个 **Python RPC 框架**（`src/aduib_rpc/`），支持多协议：**gRPC / JSON-RPC / REST / Thrift**。
- Python 端核心形态：
  - 统一请求/响应模型（`AduibRpcRequest` / `AduibRpcResponse` 等，见 `src/aduib_rpc/types.py`）
  - 通过装饰器注册服务/客户端（`@service` / `@client`，见 `src/aduib_rpc/server/rpc_execution/service_call.py`）
  - 服务发现与注册（`src/aduib_rpc/discover/`，`ServiceRegistryFactory` 等）
- 测试覆盖较丰富（`tests/`），包含协议处理、重试/超时、runtime 注入/重置、流式行为等。
- 同仓包含一个 **Rust SDK（Preview）**：`rust-sdk/`（workspace + `crates/aduib-rpc`），面向调用端，支持 JSON-RPC/REST/gRPC（`rust-sdk/README.md`）。
- 构建/依赖：
  - Python：`pyproject.toml` + `uv.lock`，pytest/pytest-asyncio 已配置；版本动态来自 `uv-dynamic-versioning`。
  - Rust：workspace（`rust-sdk/Cargo.toml`），依赖 reqwest/tokio/tonic/prost。
- `docs/` 目前为空：适合放置“架构 + 贡献指南 + 协议说明 + 发布流程”等长期文档。

---

## 1. 改进目标（Goals）与非目标（Non-goals）

### Goals
1. **开发体验**：一条命令完成 lint/typecheck/test/proto 生成；Windows/Linux 都好用（仓库已有 `.ps1` 和 `.sh`）。
2. **质量门禁**：最小化“测试通过但发布后才发现问题”的概率（CI + 测试分层 + 静态检查）。
3. **可演进架构**：把“运行时全局状态 + 兼容层”从隐式约定变成显式文档与推荐用法。
4. **发布一致性**：Python 包 + Rust crate 的版本/兼容策略清晰，有 checklist。
5. **文档可读**：把 README 中的长示例与细节拆到 docs，README 只保留入口与 quickstart。

### Non-goals
- 不在此方案中直接重构/替换传输层实现（gRPC/REST/JSON-RPC/Thrift），除非有明确 bug 或测试缺口。
- 不强制 Python 与 Rust 版本完全锁步（但要有兼容策略）。

---

## 2. 架构与目录边界建议（让“哪里该改，哪里别碰”更清晰）

### 2.1 建议定义“公共 API / 内部 API”边界
**建议作为公共 API（稳定，变更需走 deprecation）**：
- `src/aduib_rpc/__init__.py`（如存在 re-export）
- `src/aduib_rpc/types.py`
- 装饰器与核心调用入口：`src/aduib_rpc/server/rpc_execution/service_call.py`（`@service/@client`、`ServiceCaller/ClientCaller`）
- 客户端构建：`src/aduib_rpc/client/*` 中对外暴露的工厂/配置

**建议作为内部 API（允许调整目录/参数/实现）**：
- `src/aduib_rpc/server/protocols/`、`src/aduib_rpc/server/request_handlers/`
- `src/aduib_rpc/grpc/` 与 `src/aduib_rpc/thrift/`（通常是生成代码或协议绑定层）
- `src/aduib_rpc/utils/`

### 2.2 Runtime/全局状态的“推荐用法”文档化
代码里已经有兼容层与 deprecation view（`service_call.py` 的 `service_funcs/service_instances/...` 视图），并且提到了 reset 的测试场景。

建议在 docs 写清楚：
- 推荐使用 `RpcRuntime` 显式注入（`get_runtime()` / `default_runtime()`）
- `FuncCallContext.reset()` 仅用于测试/隔离，不建议线上使用
- 插件/装饰器自动加载：`load_service_plugins()` 的适用场景和风险

---

## 3. 文档体系建设（docs/ 的内容规划）

建议在 `docs/` 增加以下文档（按优先级）：

### P0（马上加）
1. `docs/quickstart.md`
   - 5 分钟跑通：启动 server + 调 client（分别给 JSON-RPC/REST/gRPC）
   - streaming 的最小示例（说明 `completion()` 返回 AsyncIterator）
2. `docs/architecture.md`
   - 画出调用链：Client → Transport → Server Handler → ServiceFunc → Response
   - 说明 `method` 命名规则（例如 README 中的 `chat.completions`、以及 `MethodName.format_v2`）
3. `docs/dev_workflow.md`
   - 本地开发常用命令（uv、pytest、proto 生成、interop）
   - Windows/Linux 双脚本入口

### P1（1~2 周内）
4. `docs/testing.md`
   - 约定：unit vs integration；哪些测试会启动 server；如何标记/跳过
   - 建议引入 markers：`@pytest.mark.integration`、`@pytest.mark.slow`
5. `docs/release.md`
   - Python：版本来源（`uv-dynamic-versioning`）、打 tag、build、发布检查项
   - Rust：crate 发布前 checklist（README、features、msrv、examples）

### P2（后续）
6. `docs/protocols/` 子目录
   - `jsonrpc.md` / `rest.md` / `grpc.md` / `thrift.md`
   - 统一错误结构 `{code,message,data}` 与不同协议映射关系（你的 tests 里已有形状校验）

---

## 4. 开发体验（DX）改进：把散落脚本变成统一入口

仓库已有 `scripts/compile_protos.py`、`scripts/interop.ps1`、`scripts/interop.sh`。

### 4.1 建议新增一个统一任务入口
优先方案（跨平台、对 Python 项目友好）：
- 增加 `scripts/tasks.py`（或 `scripts/tasks.ps1` + `scripts/tasks.sh`），提供：
  - `fmt` / `lint` / `typecheck` / `test` / `gen-proto` / `interop`

并在 `README.md` 顶部替换为简短入口：
- “开发者：看 `docs/dev_workflow.md`”

### 4.2 依赖与锁定策略
- 既然已经使用 `uv.lock`，建议在 docs 明确：
  - 开发依赖走 `[dependency-groups].dev`
  - CI 上使用 uv 同步安装（或保留 pip，但要说明差异）

---

## 5. 测试与 CI（质量门禁）

### 5.1 测试分层与标记
现有 `tests/` 里既有纯逻辑，也有启动 server/客户端的场景。建议：
- 为会启动 server/占用端口的用例加 `@pytest.mark.integration`
- 为耗时用例加 `@pytest.mark.slow`
- 默认 CI 跑 unit；每日/每次合并跑 integration（按你们节奏选）

### 5.2 CI 建议（GitHub Actions）
建议建立矩阵：
- OS：Ubuntu + Windows（仓库已有 PowerShell 脚本）
- Python：3.10/3.11/3.12（与 `requires-python = ">=3.10,<3.13"` 对齐）
- Rust：stable（仅针对 `rust-sdk/`）

Job 切分（低风险）：
1. `python-lint-type-test`：pytest + pyright（或 mypy）
2. `rust-test`：`cargo test` in `rust-sdk/`
3. `interop-smoke`：调用现有 `scripts/interop.*` 做最小互通冒烟

---

## 6. Proto/生成代码治理

当前 README 指向 proto：`src/aduib_rpc/proto/aduib_rpc.proto`，并且存在生成目录：`src/aduib_rpc/grpc/`、`src/aduib_rpc/thrift/`。

建议明确一个策略并写进 docs：
- **策略 A（推荐）**：生成代码提交进 git（对使用者友好），同时提供 `scripts/compile_protos.py` 以便更新。
- **策略 B**：不提交生成物，CI/安装时生成（对贡献者更麻烦，且发布要谨慎）。

无论选哪种，都建议：
- 将生成目录在 typecheck 中排除（你已在 pyright exclude 里排除 `src/aduib_rpc/grpc/`，很好）
- 在 `docs/dev_workflow.md` 里说明“改 proto 后必须执行的命令”

---

## 7. 代码质量与可维护性（小步快跑，不大重构）

### 7.1 统一日志与观测字段
你们已在一些地方用 `extra={"rpc.*": ...}`。建议：
- 在 `src/aduib_rpc/utils/` 下定义统一的 logging keys 常量（例如 `rpc.method`, `rpc.duration_ms`）
- 文档说明：服务端/客户端都尽量输出这些字段，方便接入 observability

### 7.2 更明确的异常分类
建议建立一组稳定异常类型（例如 `RpcError`, `ServiceNotFound`, `InvalidRequest`），并在不同协议映射到统一错误结构。

这能直接提升：
- tests 的可读性（断言 error code）
- 使用者的错误处理体验

### 7.3 deprecation 政策落地
`service_call.py` 已有 deprecated 视图警告。建议在 `docs/architecture.md` 附录写：
- Deprecated API 列表
- 预计移除版本/替代方案

---

## 8. Python 包发布与 Rust SDK 发布（流程化）

### 8.1 Python（`pyproject.toml`）
现状要点：
- hatchling 构建，版本由 `uv-dynamic-versioning` 从 git 派生。

建议在 `docs/release.md` 写清楚：
- 打 tag 的规则（例如 `v0.1.0`）
- 构建产物检查：`pip install dist/*.whl` 后跑一个最小示例
- 发布到 PyPI/TestPyPI 的步骤

### 8.2 Rust（`rust-sdk/`）
建议补齐：
- `crates/aduib-rpc` 的 crates.io metadata（description, repository, documentation, keywords, categories）
- examples：至少 1 个 JSON-RPC + 1 个 gRPC
- feature flags：`streaming` 已有，建议补 `grpc`/`jsonrpc`/`rest` 可选化（如果当前实现允许）

---

## 9. 分阶段里程碑（Milestones）

### Milestone 1（1~2 天）：docs 起步 + 运行路径明确
- [ ] 填充 `docs/quickstart.md`
- [ ] 填充 `docs/dev_workflow.md`
- [ ] 填充 `docs/architecture.md`（含 runtime/装饰器/方法命名约定）

### Milestone 2（3~5 天）：质量门禁最小闭环
- [ ] 添加 pytest markers + 文档
- [ ] 建立 CI：pytest + pyright + `cargo test`

### Milestone 3（1~2 周）：发布流程与互通冒烟
- [ ] `docs/release.md` + release checklist
- [ ] interop smoke job（复用 `scripts/interop.*`）

### Milestone 4（持续）：协议一致性与可观测性
- [ ] 统一错误码/异常类型
- [ ] 统一 logging keys + 文档

---

## 10. 建议的“下一步”提交清单（低风险、价值高）

1. 把本文件作为总纲：`docs/improvement_plan.md`（已创建）。
2. 新增 `docs/dev_workflow.md` 和 `docs/quickstart.md`，把 README 里的长示例挪过去。
3. 给 tests 做 marker 分层，并在 `pyproject.toml` 的 `markers` 里补充 `integration/slow`。
4. 新增 CI（如果仓库在 GitHub 上）：先只跑 unit tests + pyright，跑通后再加 interop。


