use aduib_rpc::{AduibRpcClientBuilder, TransportKind};
use serde_json::json;

// This is an opt-in integration test:
// - It expects a running Aduib RPC gRPC server at 127.0.0.1:50051.
// - Run with: cargo test -p aduib-rpc --test grpc_smoke -- --ignored
#[tokio::test]
#[ignore]
async fn grpc_completion_smoke() {
    let client = AduibRpcClientBuilder::new("127.0.0.1:50051")
        .transport(TransportKind::Grpc)
        .build()
        .expect("build client");

    let resp = client
        .completion("CaculService.add", Some(json!({"x": 1, "y": 2})), None)
        .await
        .expect("grpc completion");

    // The test server may return different shapes; we only assert success and presence.
    assert!(resp.is_success());
}

