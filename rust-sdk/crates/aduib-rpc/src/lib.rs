//! Aduib RPC Rust SDK (preview)
//!
//! This crate provides a small, transport-agnostic client for calling an Aduib RPC server.
//!
//! Currently supported:
//! - JSON-RPC over HTTP (+ optional SSE streaming)
//! - REST over HTTP (+ optional SSE streaming)

pub mod error;
pub mod types;

pub mod client;
pub mod transport;

#[cfg(feature = "grpc")]
pub mod grpc;

pub use client::{AduibRpcClient, AduibRpcClientBuilder, TransportKind};
pub use error::{AduibRpcClientError, RemoteError};
pub use types::{AduibRpcError, AduibRpcRequest, AduibRpcResponse};
