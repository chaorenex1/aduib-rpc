use async_trait::async_trait;

#[cfg(feature = "streaming")]
use std::pin::Pin;

use crate::error::AduibRpcClientError;
use crate::types::AduibRpcRequest;
use crate::types::AduibRpcResponse;

pub(crate) mod jsonrpc;
pub(crate) mod rest;
#[cfg(feature = "grpc")]
pub(crate) mod grpc;

pub use jsonrpc::JsonRpcTransport;
pub use rest::RestTransport;
#[cfg(feature = "grpc")]
pub use grpc::GrpcTransport;

#[async_trait]
pub trait Transport {
    async fn completion(&self, request: AduibRpcRequest) -> Result<AduibRpcResponse, AduibRpcClientError>;

    #[cfg(feature = "streaming")]
    async fn completion_stream(
        &self,
        request: AduibRpcRequest,
    ) -> Result<Pin<Box<dyn futures_core::Stream<Item = Result<AduibRpcResponse, AduibRpcClientError>> + Send>>, AduibRpcClientError>;
}
