# Aduib RPC Rust SDK (Preview)

This is a small Rust client for calling an **Aduib RPC** server.

## Install

Add to your `Cargo.toml` (path dependency for this repo):

- `aduib-rpc = { path = "../rust-sdk/crates/aduib-rpc" }`

## Usage

### JSON-RPC (recommended)

```rust
use aduib_rpc::{AduibRpcClientBuilder, TransportKind};
use serde_json::json;

#[tokio::main]
async fn main() -> Result<(), Box<dyn std::error::Error>> {
    let client = AduibRpcClientBuilder::new("http://127.0.0.1:8000")
        .transport(TransportKind::JsonRpc)
        .build()?;

    let resp = client
        .completion(
            "chat.completions",
            Some(json!({"model":"gpt-3.5-turbo","messages":[{"role":"user","content":"Hello"}]})),
            Some(json!({"model":"gpt-3.5-turbo"})),
        )
        .await?;

    println!("{:#?}", resp.result);
    Ok(())
}
```

### REST (proto-json compatible)

REST endpoints expect a `RpcTask` proto-json payload, and return `RpcTaskResponse` proto-json.
This crate builds/parses that format internally so you can still call it with `method/data/meta`.

### gRPC (tonic)

This repo's gRPC service is defined in `src/aduib_rpc/proto/aduib_rpc.proto`.

```rust
use aduib_rpc::{AduibRpcClientBuilder, TransportKind};
use serde_json::json;

#[tokio::main]
async fn main() -> Result<(), Box<dyn std::error::Error>> {
    // gRPC endpoint is host:port (or http://host:port)
    let client = AduibRpcClientBuilder::new("127.0.0.1:50051")
        .transport(TransportKind::Grpc)
        .build()?;

    let resp = client
        .completion("CaculService.add", Some(json!({"x": 1, "y": 2})), None)
        .await?;

    println!("{:#?}", resp.result);
    Ok(())
}
```

## Streaming

Enable the feature:
- `aduib-rpc = { path = "../rust-sdk/crates/aduib-rpc", features = ["streaming"] }`

Then use `completion_stream(...)`.
