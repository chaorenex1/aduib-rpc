# Aduib RPC

## 项目简介
Aduib RPC 是一个基于 Python 的远程过程调用（RPC）框架，支持 gRPC、JSON-RPC 和 REST 协议。该框架提供了客户端和服务端的完整实现，支持服务发现、负载均衡和认证等功能，特别适用于 AI 服务集成场景。

## 核心功能

- **多协议支持**：支持 gRPC、JSON-RPC 和 REST API
- **服务发现**：集成服务注册与发现机制
- **负载均衡**：支持多种负载均衡策略
- **认证机制**：提供客户端认证拦截器
- **中间件支持**：可扩展的中间件架构
- **错误处理**：统一的错误处理机制

## 目录结构

```
aduib_rpc/
├── src/aduib_rpc/
│   ├── client/            # 客户端实现
│   │   ├── auth/          # 认证相关
│   │   └── transports/    # 传输层实现
│   ├── discover/          # 服务发现
│   │   ├── entities/      # 实体定义
│   │   ├── load_balance/  # 负载均衡
│   │   ├── registry/      # 服务注册
│   │   └── service/       # 服务工厂
│   ├── grpc/              # gRPC proto 相关
│   ├── proto/             # 协议定义文件
│   ├── server/            # 服务端实现
│   │   ├── protocols/     # 协议实现
│   │   └── rpc_execution/ # rpc 执行
│   │   └── request_handler/ # 请求处理
│   ├── thrift/            # Thrift 相关
│   ├── types/             # 数据类型定义
│   └── utils/             # 工具函数
├── scripts/               # 辅助脚本
└── tests/                 # 测试用例
```

## 使用方法
- 安装依赖：
   ```bash
    pip install aduib_rpc aduib_rpc[nacos]
   ```
- 或者使用 `uv` 安装（推荐）：

    ```bash
    uv add aduib_rpc aduib_rpc[nacos]
    ```

## 使用示例

### 客户端示例

```python
import asyncio
import logging

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

async def main():
    registry = NacosServiceRegistry(server_addresses='10.0.0.96:8848',
                                         namespace='eeb6433f-d68c-4b3b-a4a7-eeff19110e4d', group_name='DEFAULT_GROUP',
                                         username='nacos', password='nacos11.')
    service_name = 'test_grpc_app'
    discover_service = await registry.discover_service(service_name)
    logging.debug(f'Service: {discover_service}')
    logging.debug(f'Service URL: {discover_service.url}')
    def create_channel(url: str) -> grpc.aio.Channel:
        logging.debug(f'Channel URL: {url}')
        return grpc.aio.insecure_channel(url)

    client_factory = AduibRpcClientFactory(
        config=ClientConfig(streaming=True,grpc_channel_factory=create_channel, supported_transports=[TransportSchemes.GRPC]))
    aduib_rpc_client:AduibRpcClient = client_factory.create(discover_service.url, server_preferred=TransportSchemes.GRPC,interceptors=[AuthInterceptor(credentialProvider=InMemoryCredentialsProvider())])
    resp = aduib_rpc_client.completion(method="chat.completions",
                                       data={"model": "gpt-3.5-turbo", "messages": [{"role": "user", "content": "Hello!"}]},
                                       meta={"model": "gpt-3.5-turbo",
                                            "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/139.0.0.0 Safari/537.36 Edg/139.0.0.0"} | discover_service.get_service_info())
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

    def add2(self, data:test_add):
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
        "server_addresses": "10.0.0.96:8848",
        "namespace": "eeb6433f-d68c-4b3b-a4a7-eeff19110e4d",
        "group_name": "DEFAULT_GROUP",
        "username": "nacos",
        "password": "nacos11.",
        "max_retry": 3,
        "DISCOVERY_SERVICE_ENABLED": True,
        "DISCOVERY_SERVICE_TYPE": "nacos"
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
    # client_caller = ClientCaller.from_client_caller("caculService")
    # res1 = await client_caller.call("add", 1, 2)
    # res3 = await client_caller.call("add2", test_add())
    # res2 = await client_caller.call("async_mul", 3, 4)
    # res4 = await client_caller.call("fail", 123)

    # print("add:", res1)
    # print("add2:", res3)
    # print("async_mul:", res2)
    # print("fail:", res4)


if __name__ == '__main__':
    asyncio.run(client_call())
```

### 服务端示例

```python
import asyncio
import logging
from typing import Any

from pydantic import BaseModel

from aduib_rpc.discover.registry.registry_factory import ServiceRegistryFactory
from aduib_rpc.discover.service import AduibServiceFactory
from aduib_rpc.server.rpc_execution import RequestExecutor, RequestContext
from aduib_rpc.server.rpc_execution.request_executor import request_execution
from aduib_rpc.server.rpc_execution.service_call import service
from aduib_rpc.types import ChatCompletionResponse

logging.basicConfig(level=logging.DEBUG)

@request_execution(method="chat.completions")
class TestRequestExecutor(RequestExecutor):
    def execute(self, context: RequestContext) -> Any:
        print(f"Received prompt: {context}")
        response = ChatCompletionResponse(id="chatcmpl-123", object="chat.completion", created=1677652288,
                                              model="gpt-3.5-turbo-0301", choices=[
                    {"index": 0, "message": {"role": "assistant", "content": "Hello! How can I assist you today?"},
                     "finish_reason": "stop"}], usage={"prompt_tokens": 9, "completion_tokens": 12, "total_tokens": 21})
        if context.stream:
            async def stream_response():
                for i in range(1, 4):
                    chunk = response
                    yield chunk
            return stream_response()
        else:
            return response

class test_add(BaseModel):
    x: int = 1
    y: int = 2

@service(service_name='CaculService')
class CaculService:
    def add(self, x, y):
        """同步加法"""
        return x + y

    def add2(self, data:test_add):
        """同步加法"""
        return data.x + data.y

    async def async_mul(self, x, y):
        """异步乘法"""
        await asyncio.sleep(0.1)
        return x * y

    def fail(self, x):
        """会失败的函数"""
        raise RuntimeError("Oops!")

async def main():
    registry_config = {
        "server_addresses": "10.0.0.96:8848",
        "namespace": "eeb6433f-d68c-4b3b-a4a7-eeff19110e4d",
        "group_name": "DEFAULT_GROUP",
        "username": "nacos",
        "password": "nacos11.",
        "max_retry": 3,
        "DISCOVERY_SERVICE_ENABLED": True,
        "DISCOVERY_SERVICE_TYPE": "nacos",
        "APP_NAME": "CaculServiceApp"
    }
    service = await ServiceRegistryFactory.start_service_registry(registry_config)
    # ip,port = NetUtils.get_ip_and_free_port()
    # service = ServiceInstance(service_name='test_grpc', host=ip, port=port,
    #                                protocol=AIProtocols.AduibRpc, weight=1, scheme=TransportSchemes.GRPC)
    # registry = NacosServiceRegistry(server_addresses='10.0.0.96:8848',
    #                                      namespace='eeb6433f-d68c-4b3b-a4a7-eeff19110e4d', group_name='DEFAULT_GROUP',
    #                                      username='nacos', password='nacos11.')
    factory = AduibServiceFactory(service_instance=service)
    # await registry.register_service(service)
    await factory.run_server()

if __name__ == '__main__':
    asyncio.run(main())
```

## 开发

1. 克隆仓库：
   ```
   git clone https://github.com/chaorenex1/aduib_rpc.git
   cd aduib_rpc
   ```

2. 安装开发依赖：
   ```
   uv sync  --all-extras --dev
   ```

3. 运行测试：
   ```
   pytest tests/
   ```
4. 编译 proto 文件（如需更新）：
   ```
   python scripts/compile_protos.py
   ```

## 协议支持

框架支持以下协议与数据格式：
- gRPC (Protocol Buffers)
- JSON-RPC
- REST API

## 许可证

Apache License 2.0
