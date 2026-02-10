# Aduib RPC 代码清理与重构开发计划

**创建时间**: 2026-02-04
**基于**: 架构分析与功能评估结果

---

## 执行概览

| Phase | 名称 | 风险 | 预估文件数 |
|-------|-----|------|-----------|
| 1 | 安全删除废弃测试文件 | 无 | 4 |
| 2 | 清理 v1 Handler | 低 | 5 |
| 3 | 更新 __init__.py 导出 | 低 | 2 |
| 4 | 移除废弃 Runtime View 代码 | 中 | 1 |

---

## Phase 1: 安全删除废弃测试文件

### 任务描述
删除已被 v2 测试覆盖的废弃测试文件。

### 文件列表
```
DELETE: tests/test_deprecated_runtime_views.py
DELETE: tests/test_jsonrpc_handler_error_shape.py  (git 已标记删除)
DELETE: tests/test_rest_handler_error_shape.py     (git 已标记删除)
DELETE: tests/legacy/__init__.py                   (git 已标记删除)
```

### 验证
- 运行 `pytest tests/` 确保无测试引用这些文件

---

## Phase 2: 清理 v1 Handler

### 任务描述
删除已被 v2 handler 完全覆盖的 v1 handler 文件。

### 文件列表
```
DELETE: src/aduib_rpc/server/request_handlers/grpc_handler.py
DELETE: src/aduib_rpc/server/request_handlers/rest_handler.py
DELETE: src/aduib_rpc/server/request_handlers/jsonrpc_handler.py
DELETE: src/aduib_rpc/server/request_handlers/thrift_handler.py
```

### 依赖检查
确认以下文件不再导入 v1 handler:
- `src/aduib_rpc/server/request_handlers/__init__.py`
- `src/aduib_rpc/discover/service/aduibrpc_service_factory.py`

---

## Phase 3: 更新 __init__.py 导出

### 任务描述
更新 request_handlers 模块的 __init__.py，移除 v1 handler 导出。

### 文件
```
EDIT: src/aduib_rpc/server/request_handlers/__init__.py
```

### 修改内容
保留:
- DefaultRequestHandler
- RequestHandler (抽象基类)
- GrpcV2Handler
- RESTV2Handler
- ThriftV2Handler

移除:
- GrpcHandler
- RESTHandler
- JsonRpcHandler
- ThriftHandler

---

## Phase 4: 移除废弃 Runtime View 代码

### 任务描述
清理 service_call.py 中已标记为废弃的 _DeprecatedRuntimeView 相关代码。

### 文件
```
EDIT: src/aduib_rpc/server/rpc_execution/service_call.py
```

### 移除范围 (约 lines 49-163)
- `_DeprecatedRuntimeView` 类
- `_RuntimeMappingView` 类
- `_RuntimeListView` 类
- `_RuntimeAttrView` 类
- 模块级别的废弃视图变量:
  - `service_instances`
  - `client_instances`
  - `service_funcs`
  - `client_funcs`
  - `interceptors`
  - `credentials_provider`

### 保留
- `FuncCallContext` 类 (兼容层，仍在使用)
- `_SERVICE_CATALOG` / `_SERVICE_FUNC_CATALOG` (持久化目录)

---

## 执行顺序与依赖

```
Phase 1 (独立)
    ↓
Phase 2 (依赖 Phase 1 通过)
    ↓
Phase 3 (依赖 Phase 2)
    ↓
Phase 4 (独立，可与 Phase 2-3 并行)
```

---

## 验证清单

### 每个 Phase 完成后
1. [ ] `pytest tests/` 全部通过
2. [ ] `python -c "import aduib_rpc"` 无导入错误
3. [ ] `pyright src/` 无新增类型错误

### 全部完成后
1. [ ] 运行集成测试 `pytest tests/test_integration.py`
2. [ ] 运行 v2 端到端测试 `pytest tests/test_*_v2_*.py`
3. [ ] 确认无循环导入

---

## 回滚策略

所有删除操作前确保:
1. 当前工作已提交到 git
2. 可通过 `git checkout -- <file>` 恢复

如遇测试失败:
1. 立即停止后续 Phase
2. 分析失败原因
3. 必要时回滚当前 Phase 所有修改
