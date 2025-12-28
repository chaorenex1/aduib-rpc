//! gRPC client bindings and helpers (tonic).

#[allow(clippy::all)]
pub mod pb {
    tonic::include_proto!("src.aduib_rpc.proto");
}

