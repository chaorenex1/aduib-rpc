use std::collections::HashMap;
use std::time::Duration;

use serde_json::{json, Value};

use crate::error::{AduibRpcClientError, RemoteError};
use crate::transport::{JsonRpcTransport, RestTransport, Transport};
use crate::types::{AduibRpcRequest, AduibRpcResponse};

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum TransportKind {
    Rest,
    JsonRpc,
    #[cfg(feature = "grpc")]
    Grpc,
}

pub struct AduibRpcClient {
    transport: Box<dyn Transport + Send + Sync>,
}

impl AduibRpcClient {
    pub async fn completion(
        &self,
        method: impl Into<String>,
        data: Option<Value>,
        meta: Option<Value>,
    ) -> Result<AduibRpcResponse, AduibRpcClientError> {
        let req = AduibRpcRequest {
            aduib_rpc: "1.0".to_string(),
            method: method.into(),
            data,
            meta,
            id: None,
        };

        let resp = self.transport.completion(req).await?;
        if !resp.is_success() {
            return Err(AduibRpcClientError::Remote(RemoteError(
                resp.error.unwrap_or(crate::types::AduibRpcError {
                    code: -1,
                    message: "unknown error".to_string(),
                    data: Some(json!({"status": resp.status, "result": resp.result})),
                }),
            )));
        }
        Ok(resp)
    }

    #[cfg(feature = "streaming")]
    pub async fn completion_stream(
        &self,
        method: impl Into<String>,
        data: Option<Value>,
        meta: Option<Value>,
    ) -> Result<std::pin::Pin<Box<dyn futures_core::Stream<Item = Result<AduibRpcResponse, AduibRpcClientError>> + Send>>, AduibRpcClientError>
    {
        let req = AduibRpcRequest {
            aduib_rpc: "1.0".to_string(),
            method: method.into(),
            data,
            meta,
            id: None,
        };
        self.transport.completion_stream(req).await
    }

    #[cfg(not(feature = "streaming"))]
    pub async fn completion_stream(
        &self,
        _method: impl Into<String>,
        _data: Option<Value>,
        _meta: Option<Value>,
    ) -> Result<(), AduibRpcClientError> {
        Err(AduibRpcClientError::StreamingNotEnabled)
    }
}

#[derive(Debug, Clone)]
pub struct AduibRpcClientBuilder {
    base_url: String,
    transport: TransportKind,
    timeout: Option<Duration>,
    headers: HashMap<String, String>,
}

impl AduibRpcClientBuilder {
    pub fn new(base_url: impl Into<String>) -> Self {
        Self {
            base_url: base_url.into(),
            transport: TransportKind::JsonRpc,
            timeout: Some(Duration::from_secs(30)),
            headers: HashMap::new(),
        }
    }

    pub fn transport(mut self, kind: TransportKind) -> Self {
        self.transport = kind;
        self
    }

    pub fn timeout(mut self, timeout: Duration) -> Self {
        self.timeout = Some(timeout);
        self
    }

    /// Add a default header sent on every request.
    pub fn header(mut self, key: impl Into<String>, value: impl Into<String>) -> Self {
        self.headers.insert(key.into(), value.into());
        self
    }

    pub fn build(self) -> Result<AduibRpcClient, AduibRpcClientError> {
        let mut headers = reqwest::header::HeaderMap::new();
        for (k, v) in self.headers {
            headers.insert(
                reqwest::header::HeaderName::from_bytes(k.as_bytes()).map_err(|_| {
                    AduibRpcClientError::HttpStatus {
                        status: 400,
                        body: format!("invalid header name: {k}"),
                    }
                })?,
                reqwest::header::HeaderValue::from_str(&v).map_err(|_| AduibRpcClientError::HttpStatus {
                    status: 400,
                    body: format!("invalid header value for {k}"),
                })?,
            );
        }

        let mut builder = reqwest::Client::builder().default_headers(headers);
        if let Some(timeout) = self.timeout {
            builder = builder.timeout(timeout);
        }
        let client = builder.build()?;

        let transport: Box<dyn Transport + Send + Sync> = match self.transport {
            TransportKind::Rest => Box::new(RestTransport::new(client, self.base_url)),
            TransportKind::JsonRpc => Box::new(JsonRpcTransport::new(client, self.base_url)),
            #[cfg(feature = "grpc")]
            TransportKind::Grpc => Box::new(crate::transport::GrpcTransport::new(self.base_url)),
        };

        Ok(AduibRpcClient { transport })
    }
}
