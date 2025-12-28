# Aduib RPC

## 项目简介
Aduib RPC 是一个基于 Python 的远程过程调用（RPC）框架，内置 **gRPC / JSON-RPC / REST / Thrift** 多协议适配层，并提供统一的请求/响应封装（`AduibRpcRequest` / `AduibRpcResponse`）。

它适合做“服务化的 AI 能力”对外暴露：你可以用统一的服务注册/发现、负载均衡、重试、鉴权中间件，把不同协议的调用收敛到同一套 Service / RequestExecutor 模型中。

---

## 核心特性（Feature Summary）

### 1) 多协议与多传输层
- **gRPC**：Unary + Stream
- **REST**：HTTP POST + SSE Streaming
- **JSON-RPC 2.0**：HTTP JSON-RPC + SSE Streaming
- **Thrift**：Unary（stream 暂不支持）

### 2) 统一的协议无关消息模型
- `AduibRpcRequest(method, data, meta, id)`
- `AduibRpcResponse(result, error, status, id)`
- 统一错误结构：`{code, message, data}`

### 3) 服务定义与调用（Server/Client 双端）
- 服务端：`@service(service_name=...)` 注册方法
- 客户端：`@client(app_name)` 生成强类型 service stub（同步/异步方法均可）

### 4) Server 执行器（RequestExecutor）
- 支持通过 `@request_execution(method=...)` 绑定自定义执行器
- 支持 streaming 场景（`context.stream`）

### 5) 服务发现 / 注册
- 内置 registry 抽象与工厂
- 支持 In-Memory / Nacos（以 extras 形式提供）

### 6) 负载均衡、重试与超时
- Client 侧提供负载均衡策略与连接池复用
- 支持重试（需配合 `meta` 的 retry 参数 / idempotent 标记）
- 支持超时（`timeout_ms/timeout_s` 或 transport/config 默认值）

### 7) 鉴权与中间件
- ClientRequestInterceptor / ServerInterceptor
- 可用于：鉴权、审计、注入 trace / headers / 路由信息等

### 8) 长时间任务（Long Running Task）+ 完成通知（新增）
> 适用于耗时较长的 AI 推理/批处理场景：提交任务立即返回 `task_id`，后台执行；
> 客户端可轮询查询结果，或通过流式订阅在完成时收到通知。

- `task/submit`：提交长任务，立即返回 `task_id`
- `task/status`：查询任务状态
- `task/result`：查询任务结果（成功时返回 `value`）
- `task/subscribe`（stream）：订阅任务事件，完成后自动结束

---

## 目录结构

> 注：目录名以 `src/aduib_rpc` 为准。

```
aduib_rpc/
├── src/aduib_rpc/
│   ├── client/                 # 客户端实现（transport/middleware/pool/retry 等）
│   │   ├── auth/               # 认证相关
│   │   └── transports/         # 传输层实现（grpc/jsonrpc/rest）
│   ├── discover/               # 服务发现/注册（registry/load_balance 等）
│   ├── grpc/                   # gRPC 生成代码
│   ├── proto/                  # proto / thrift 定义
│   ├── rpc/                    # 方法名解析等
│   ├── server/                 # 服务端实现
│   │   ├── protocols/          # 协议服务器实现（rest/jsonrpc/...) 
│   │   ├── request_handlers/   # 请求处理（DefaultRequestHandler 等）
│   │   ├── rpc_execution/      # service_call / request_executor / context
│   │   └── tasks/              # 长任务管理（task manager）
│   ├── thrift/                 # thrift 生成代码
│   ├── types.py                # 核心类型（Request/Response/Error/JSONRPC types）
│   └── utils/                  # 工具函数
├── scripts/                    # 辅助脚本（protos 编译等）
└── tests/                      # 测试用例
```

---

## 安装

- pip：

```bash
pip install aduib_rpc aduib_rpc[nacos]
```

- uv（推荐）：

```bash
uv add aduib_rpc aduib_rpc[nacos]
```

---

## 使用示例

### 客户端示例

> 注意：`client.completion(...)` 返回的是 AsyncIterator；即便非 streaming，也会 yield 一次。

```python
import asyncio
import logging
import os

import grpc
from pydantic import BaseModel

from aduib_rpc.client.auth import InMemoryCredentialsProvider
from aduib_rpc.client.auth.interceptor import AuthInterceptor
from aduib_rpc.client.base_client import ClientConfig, AduibRpcClient
from aduib_rpc.client.client_factory import AduibRpcClientFactory
from aduib_rpc.discover.registry.nacos.nacos import NacosServiceRegistry
from aduib_rpc.discover.registry.registry_factory import ServiceRegistryFactory
from aduib_rpc.server.rpc_execution.service_call import client, FuncCallContext
from aduib_rpc.utils.constant import TransportSchemes

logging.basicConfig(level=logging.DEBUG)

# SECURITY NOTE:
# Never hardcode real service addresses, namespaces, usernames, or passwords in code or README files.
# Use environment variables or a secrets manager instead.

async def main():
    registry = NacosServiceRegistry(
        server_addresses=os.getenv('NACOS_SERVER_ADDRESSES', '127.0.0.1:8848'),
        namespace=os.getenv('NACOS_NAMESPACE', 'your-namespace'),
        group_name=os.getenv('NACOS_GROUP_NAME', 'DEFAULT_GROUP'),
        username=os.getenv('NACOS_USERNAME', 'nacos'),
        password=os.getenv('NACOS_PASSWORD', 'nacos'),
    )
    service_name = 'test_grpc_app'
    discover_service = await registry.discover_service(service_name)
    logging.debug(f'Service: {discover_service}')
    logging.debug(f'Service URL: {discover_service.url}')

    def create_channel(url):
        logging.debug(f'Channel URL: {url}')
        # For production, prefer TLS (secure_channel) instead of insecure_channel.
        return grpc.aio.insecure_channel(url)

    client_factory = AduibRpcClientFactory(
        config=ClientConfig(
            streaming=True,
            grpc_channel_factory=create_channel,
            supported_transports=[TransportSchemes.GRPC],
        )
    )
    aduib_rpc_client: AduibRpcClient = client_factory.create(
        discover_service.url,
        server_preferred=TransportSchemes.GRPC,
        interceptors=[AuthInterceptor(credentialProvider=InMemoryCredentialsProvider())],
    )

    resp = aduib_rpc_client.completion(
        method="chat.completions",
        data={"model": "gpt-3.5-turbo", "messages": [{"role": "user", "content": "Hello!"}]},
        meta={
            "model": "gpt-3.5-turbo",
            "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) ...",
        } | discover_service.get_service_info(),
    )

    async for r in resp:
        logging.debug(f'Response: {r}')


class test_add(BaseModel):
    x: int = 1
    y: int = 2

@client("CaculServiceApp")
class CaculService:
    def add(self, x, y):
        """同步加法"""
        ...

    def add2(self, data: test_add):
        """同步加法"""
        ...

    async def async_mul(self, x, y):
        """异步乘法"""
        ...

    def fail(self, x):
        """会失败的函数"""
        ...

async def client_call():
    registry_config = {
        "server_addresses": os.getenv('NACOS_SERVER_ADDRESSES', '127.0.0.1:8848'),
        "namespace": os.getenv('NACOS_NAMESPACE', 'your-namespace'),
        "group_name": os.getenv('NACOS_GROUP_NAME', 'DEFAULT_GROUP'),
        "username": os.getenv('NACOS_USERNAME', 'nacos'),
        "password": os.getenv('NACOS_PASSWORD', 'nacos'),
        "max_retry": 3,
        "DISCOVERY_SERVICE_ENABLED": True,
        "DISCOVERY_SERVICE_TYPE": "nacos",
    }
    ServiceRegistryFactory.start_service_discovery(registry_config)
    FuncCallContext.enable_auth()

    caculService = CaculService()
    result = caculService.add(1, 2)
    logging.debug(f'1 + 2 = {result}')

    result = caculService.add2(test_add(x=3, y=4))
    logging.debug(f'3 + 4 = {result}')

    result = await caculService.async_mul(3, 5)
    logging.debug(f'3 * 5 = {result}')


if __name__ == '__main__':
    asyncio.run(client_call())
```

### 服务端示例

```python
import asyncio
import logging
import os
from typing import Any

from pydantic import BaseModel

from aduib_rpc.discover.registry.registry_factory import ServiceRegistryFactory
from aduib_rpc.discover.service import AduibServiceFactory
from aduib_rpc.server.rpc_execution import RequestExecutor, RequestContext
from aduib_rpc.server.rpc_execution.request_executor import request_execution
from aduib_rpc.server.rpc_execution.service_call import service

logging.basicConfig(level=logging.DEBUG)

@request_execution(method="chat.completions")
class TestRequestExecutor(RequestExecutor):
    def execute(self, context: RequestContext) -> Any:
        print(f"Received prompt: {context}")
        # 这里的返回值可以是任意可序列化对象（dict / pydantic model / 基础类型等）。
        response = {
            "id": "chatcmpl-123",
            "object": "chat.completion",
            "created": 1677652288,
            "model": "gpt-3.5-turbo-0301",
            "choices": [
                {
                    "index": 0,
                    "message": {"role": "assistant", "content": "Hello! How can I assist you today?"},
                    "finish_reason": "stop",
                }
            ],
            "usage": {"prompt_tokens": 9, "completion_tokens": 12, "total_tokens": 21},
        }
        if context.stream:
            async def stream_response():
                for _ in range(1, 4):
                    yield response
            return stream_response()
        else:
            return response

class test_add(BaseModel):
    x: int = 1
    y: int = 2

@service(service_name='CaculService')
class CaculService:
    def add(self, x, y):
        return x + y

    def add2(self, data: test_add):
        return data.x + data.y

    async def async_mul(self, x, y):
        await asyncio.sleep(0.1)
        return x * y

    def fail(self, x):
        raise RuntimeError("Oops!")

async def main():
    registry_config = {
        "server_addresses": os.getenv('NACOS_SERVER_ADDRESSES', '127.0.0.1:8848'),
        "namespace": os.getenv('NACOS_NAMESPACE', 'your-namespace'),
        "group_name": os.getenv('NACOS_GROUP_NAME', 'DEFAULT_GROUP'),
        "username": os.getenv('NACOS_USERNAME', 'nacos'),
        "password": os.getenv('NACOS_PASSWORD', 'nacos'),
        "max_retry": 3,
        "DISCOVERY_SERVICE_ENABLED": True,
        "DISCOVERY_SERVICE_TYPE": "nacos",
        "APP_NAME": "CaculServiceApp",
    }
    service_instance = await ServiceRegistryFactory.start_service_registry(registry_config)
    factory = AduibServiceFactory(service_instance=service_instance)
    await factory.run_server()

if __name__ == '__main__':
    asyncio.run(main())
```

---

## 长时间任务（Long Running Task）与通知

### API（method）一览

- `task/submit`：提交任务（返回 task_id）
- `task/status`：查询状态
- `task/result`：查询结果
- `task/subscribe`：订阅任务事件（stream，完成后会结束）

### 示例：提交 + 轮询 + 订阅

> 说明：下面示例假设你已经按上面的方式拿到了 `aduib_rpc_client`（任意 transport 均可）。

```python
import asyncio

async def run_long_task(aduib_rpc_client):
    # 1) 提交一个后台执行的 RPC 调用
    submit_req = {
        "target_method": "CaculService.async_mul",
        "params": {"x": 3, "y": 5},
        "options": {"ttl_seconds": 3600},
    }

    task_id = None
    async for r in aduib_rpc_client.completion(method="task/submit", data=submit_req):
        task_id = r.result["task_id"]

    assert task_id is not None

    # 2) 轮询结果（所有 transport 都能用）
    while True:
        async for r in aduib_rpc_client.completion(method="task/result", data={"task_id": task_id}):
            status = r.result["status"]
            if status == "succeeded":
                print("value=", r.result["value"])
                return
            if status == "failed":
                print("error=", r.result["error"])
                return
        await asyncio.sleep(0.2)


async def subscribe_until_done(aduib_rpc_client, task_id: str):
    # 3) 订阅通知（stream）
    # - REST/JSON-RPC：通过 SSE
    # - gRPC：通过 stream_completion
    async for r in aduib_rpc_client.completion(method="task/subscribe", data={"task_id": task_id}):
        print(r.result)
```

> 提示：Thrift 目前没有 stream，所以建议使用轮询（task/result）。

---

## 开发

1. 克隆仓库：

```bash
git clone https://github.com/chaorenex1/aduib_rpc.git
cd aduib_rpc
```

2. 安装开发依赖：

```bash
uv sync --all-extras --dev
```

3. 运行测试：

```bash
pytest tests/
```

4. 编译 proto 文件（如需更新）：

```bash
python scripts/compile_protos.py
```

---

## 协议支持

- gRPC (Protocol Buffers)
- JSON-RPC 2.0
- REST API (+ SSE streaming)
- Thrift

---

## 许可证

Apache License 2.0

## 使用示例

### Rust SDK（新增）

仓库内提供一个 Rust SDK（预览版），位于 `rust-sdk/`：

- 文档：`rust-sdk/README.md`
- crate：`rust-sdk/crates/aduib-rpc`


