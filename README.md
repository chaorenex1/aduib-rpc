```
# aduib_rpc

## 项目简介
aduib_rpc 是一个基于 Python 的远程过程调用（RPC）服务，支持 gRPC、JSON-RPC 和 REST 接口，适用于多种 AI 相关的服务场景。

## 目录结构
```
aduib_rpc/
├── main.py
├── pyproject.toml
├── README.md
├── uv.lock
├── scripts/
│   ├── compile_protos.py
│   └── json_to_proto.py
├── src/
│   └── aduib_rpc/
│       ├── types.py
│       ├── grpc/
│       │   ├── chat_completion_pb2_grpc.py
│       │   ├── chat_completion_pb2.py
│       │   └── ...（更多 gRPC 相关文件）
│       ├── protos/
│       │   ├── chat_completion.proto
│       │   └── ...（更多 proto 文件）
│       ├── server/
│       │   ├── context.py
│       │   └── request_handlers/
│       │       ├── grpc_handler.py
│       │       ├── jsonrpc_handler.py
│       │       ├── request_handler.py
│       │       └── rest_handler.py
│       └── utils/
│           ├── jsonrpc_helper.py
│           └── proto_utils.py
└── tests/
```

## 安装方法

1. 克隆仓库：
   ```
   git clone <your-repo-url>
   cd aduib_rpc
   ```

2. 安装依赖：
   ```
   pip install -r requirements.txt
   ```

3. 编译 proto 文件（如有需要）：
   ```
   python scripts/compile_protos.py
   ```

## 使用方法

1. 启动主服务：
   ```
   python main.py
   ```

2. 可通过 gRPC、JSON-RPC 或 REST 接口进行调用，具体接口定义见 `src/aduib_rpc/protos/` 及 `src/aduib_rpc/grpc/`。

## 测试

项目测试文件位于 `tests/` 目录，可使用 pytest 运行：
```
pytest tests/
```

## 许可证

本项目采用 MIT 许可证，详情见 LICENSE 文件。

```

你可以直接复制以上内容到你的 `README.md` 文件中。