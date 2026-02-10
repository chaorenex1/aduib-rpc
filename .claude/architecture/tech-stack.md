# 技术栈清单

**生成时间**: 2026-02-04

---

## 编程语言

| 语言 | 版本要求 | 用途 |
|-----|---------|------|
| Python | >=3.10, <3.13 | 主要开发语言 |
| Protobuf | 3.x | gRPC 接口定义 |
| Thrift | latest | Thrift IDL 定义 |

---

## 核心框架与库

| 名称 | 版本 | 用途 | 选型理由 |
|-----|------|------|---------|
| **Pydantic** | >=2.11.0 | 数据验证与类型定义 | Python 生态标准，与 FastAPI 深度集成 |
| **FastAPI** | >=0.115.2 | REST API 服务端 | 高性能异步框架，自动文档生成 |
| **Starlette** | >=0.48.0 | JSON-RPC ASGI 应用 | 轻量 ASGI 框架，FastAPI 底层 |
| **grpcio** | >=1.66.1 | gRPC 服务端/客户端 | Google 官方实现，性能优异 |
| **grpcio-tools** | >=1.66.1 | Proto 编译 | 生成 Python gRPC 桩代码 |
| **grpcio-reflection** | >=1.66.1 | gRPC 反射服务 | 支持 grpcurl 等工具 |
| **protobuf** | >=4.24.3 | Protobuf 序列化 | gRPC 消息格式 |
| **thrift** | latest | Thrift 序列化 | 多语言互操作 |
| **httpx** | >=0.28.1 | HTTP 客户端 | 异步支持，类 requests API |
| **httpx-sse** | >=0.4.0 | SSE 客户端 | Server-Sent Events 支持 |
| **sse-starlette** | latest | SSE 服务端 | Starlette SSE 响应 |
| **cryptography** | >=43.0.0 | 加密/TLS | 标准密码学库 |

---

## 可选依赖 (extras)

### telemetry
| 名称 | 版本 | 用途 |
|-----|------|------|
| opentelemetry-api | >=1.33.0 | OTel API |
| opentelemetry-sdk | >=1.33.0 | OTel SDK |
| opentelemetry-exporter-otlp | >=1.33.0 | OTLP 导出 |
| opentelemetry-instrumentation-fastapi | >=0.54b0 | FastAPI 自动埋点 |
| opentelemetry-instrumentation-asgi | >=0.54b0 | ASGI 自动埋点 |
| opentelemetry-instrumentation-httpx | >=0.54b0 | httpx 自动埋点 |
| opentelemetry-instrumentation-grpc | >=0.54b0 | gRPC 自动埋点 |

### nacos
| 名称 | 版本 | 用途 |
|-----|------|------|
| nacos-sdk-python | >2.0.1 | Nacos 服务发现 |

### serialization
| 名称 | 版本 | 用途 |
|-----|------|------|
| msgpack | >=1.0.0 | MessagePack 序列化 |
| fastavro | >=1.9.0 | Avro 序列化 |

### uvicorn
| 名称 | 版本 | 用途 |
|-----|------|------|
| uvicorn | >=0.1.5 | ASGI 服务器 |

### a2a
| 名称 | 版本 | 用途 |
|-----|------|------|
| a2a-sdk | >=0.2.4 | A2A 协议支持 |

### redis
| 名称 | 版本 | 用途 |
|-----|------|------|
| redis | >=5.0.0 | Redis 客户端 (任务持久化) |

---

## 开发依赖

| 名称 | 版本 | 用途 |
|-----|------|------|
| pytest | 8.4.1 | 单元测试框架 |
| pytest-asyncio | >=0.23.0 | 异步测试支持 |
| fakeredis | >=2.20.0 | Redis 模拟 |
| alembic | 1.16.4 | 数据库迁移 (预留) |

---

## 构建与发布

| 工具 | 用途 |
|-----|------|
| hatchling | 构建后端 |
| uv-dynamic-versioning | Git 版本号自动提取 |
| uv | 包管理器 (推荐) |

---

## 代码质量

| 工具 | 配置文件 | 用途 |
|-----|---------|------|
| mypy | pyproject.toml | 类型检查 |
| pyright | pyproject.toml | 类型检查 (IDE) |
| pydantic.mypy | plugin | Pydantic mypy 插件 |

---

## 基础设施 (生产推荐)

| 类别 | 推荐方案 | 备注 |
|-----|---------|------|
| 服务注册中心 | Nacos | 已有原生支持 |
| 分布式缓存 | Redis | 任务持久化后端 |
| 可观测性后端 | Jaeger / Tempo | OTLP 导出目标 |
| 日志聚合 | ELK / Loki | 结构化 JSON 日志 |
| 容器运行时 | Docker / Kubernetes | 标准部署 |
| TLS 证书管理 | cert-manager / Vault | mTLS 证书自动化 |

---

## 版本矩阵

| Python 版本 | 支持状态 |
|------------|---------|
| 3.10 | 支持 |
| 3.11 | 支持 |
| 3.12 | 支持 (主测试版本) |
| 3.13+ | 暂不支持 |
