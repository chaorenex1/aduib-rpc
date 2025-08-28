# aduib_rpc

## 项目简介
aduib_rpc 是一个基于 Python 的远程过程调用（RPC）框架，支持 gRPC、JSON-RPC 和 REST 协议。该框架提供了客户端和服务端的完整实现，支持服务发现、负载均衡和认证等功能，特别适用于 AI 服务集成场景。

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
│   ├── grpc/              # gRPC 协议相关
│   ├── proto/             # 协议定义文件
│   ├── server/            # 服务端实现
│   └── utils/             # 工具函数
├── scripts/               # 辅助脚本
└── tests/                 # 测试用例
```

## 安装方法

1. 克隆仓库：
   ```
   git clone <repository-url>
   cd aduib_rpc
   ```

2. 安装依赖：
   ```
   uv sync
   ```

3. 编译 proto 文件（如需更新）：
   ```
   python scripts/compile_protos.py
   ```

## 使用示例

### 客户端示例

```python
service = ServiceInstance(service_name='test_jsonrpc_app', host='localhost', port=5001,
                                   protocol=AIProtocols.AduibRpc, weight=1, scheme=TransportSchemes.GRPC)
    registry = NacosServiceRegistry(server_addresses='localhost:8848',
                                         namespace='eeb6433f-d68c-4b3b-a4a7-eeff19110e', group_name='DEFAULT_GROUP',
                                         username='nacos', password='localhost')
    factory = AduibServiceFactory(service_instance=service)
    discover_service = await registry.discover_service(service.service_name)
    logging.debug(f'Service: {discover_service}')
    logging.debug(f'Service URL: {discover_service.url}')
    def create_channel(url: str) -> grpc.Channel:
        return grpc.insecure_channel(discover_service.url)

    client_factory = AduibRpcClientFactory(
        config=ClientConfig(grpc_channel_factory=create_channel, supported_transports=[TransportSchemes.GRPC]))
    aduib_rpc_client:AduibRpcClient = client_factory.create(service.url, server_preferred=TransportSchemes.GRPC,interceptors=[AuthInterceptor(credentialProvider=InMemoryCredentialsProvider())])
    resp = aduib_rpc_client.completion(method="chat.completions",
                                       data={"model": "gpt-3.5-turbo", "messages": [{"role": "user", "content": "Hello!"}]},
                                       meta={"stream": "true",
                                             "model": "gpt-3.5-turbo",
                                            "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/139.0.0.0 Safari/537.36 Edg/139.0.0.0"} | service.get_service_info())
    async for r in resp:
        logging.debug(f'Response: {r}')
```

### 服务端示例

```python
async def main():
    service = ServiceInstance(service_name='test_jsonrpc_app', host='localhost', port=5000,
                                   protocol=AIProtocols.AduibRpc, weight=1, scheme=TransportSchemes.GRPC)
    registry = NacosServiceRegistry(server_addresses='localhost:8848',
                                         namespace='eeb6433f-d68c-4b3b-a4a7-eeff19110e4d', group_name='DEFAULT_GROUP',
                                         username='nacos', password='localhost')
    factory = AduibServiceFactory(service_instance=service)
    await registry.register_service(service)
    await factory.run_server()

if __name__ == '__main__':
    asyncio.run(main())
```

## 开发

1. 安装开发依赖：
   ```
   uv sync  --all-extras --dev
   ```

2. 运行测试：
   ```
   pytest tests/
   ```

## 协议支持

框架支持以下协议与数据格式：
- gRPC (Protocol Buffers)
- JSON-RPC
- REST API

## 许可证

Apache License 2.0