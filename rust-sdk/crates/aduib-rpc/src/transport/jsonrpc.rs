use async_trait::async_trait;
use serde_json::json;
#[cfg(feature = "streaming")]
use serde_json::Value;
#[cfg(feature = "streaming")]
use std::pin::Pin;

use crate::error::{AduibRpcClientError, RemoteError};
use crate::transport::Transport;
use crate::types::{AduibRpcRequest, AduibRpcResponse, JsonRpcRequest, JsonRpcResponse};

fn normalize_base_url(mut base: String) -> String {
    if base.ends_with('/') {
        base.pop();
    }
    if !base.ends_with("/aduib_rpc") {
        base.push_str("/aduib_rpc");
    }
    base
}

#[derive(Clone)]
pub struct JsonRpcTransport {
    client: reqwest::Client,
    url: String,
}

impl JsonRpcTransport {
    pub fn new(client: reqwest::Client, base_url: String) -> Self {
        Self {
            client,
            url: normalize_base_url(base_url),
        }
    }
}

#[async_trait]
impl Transport for JsonRpcTransport {
    async fn completion(&self, request: AduibRpcRequest) -> Result<AduibRpcResponse, AduibRpcClientError> {
        let payload = JsonRpcRequest {
            jsonrpc: "2.0".to_string(),
            id: json!(uuid_like()),
            method: "message/completion".to_string(),
            params: Some(request),
        };

        let resp = self.client.post(&self.url).json(&payload).send().await?;
        let status = resp.status();
        let body = resp.text().await?;
        if !status.is_success() {
            return Err(AduibRpcClientError::HttpStatus {
                status: status.as_u16(),
                body,
            });
        }

        let decoded: JsonRpcResponse<AduibRpcResponse> = serde_json::from_str(&body)?;
        match decoded {
            JsonRpcResponse::Success(s) => Ok(s.result),
            JsonRpcResponse::Error(e) => Err(AduibRpcClientError::Remote(RemoteError(e.error))),
        }
    }

    #[cfg(feature = "streaming")]
    async fn completion_stream(
        &self,
        request: AduibRpcRequest,
    ) -> Result<Pin<Box<dyn futures_core::Stream<Item = Result<AduibRpcResponse, AduibRpcClientError>> + Send>>, AduibRpcClientError>
    {
        use futures_util::StreamExt;

        let payload = JsonRpcRequest {
            jsonrpc: "2.0".to_string(),
            id: json!(uuid_like()),
            method: "message/completion/stream".to_string(),
            params: Some(request),
        };

        let resp = self.client.post(&self.url).json(&payload).send().await?;
        let status = resp.status();
        if !status.is_success() {
            let body = resp.text().await.unwrap_or_default();
            return Err(AduibRpcClientError::HttpStatus {
                status: status.as_u16(),
                body,
            });
        }

        let byte_stream = resp.bytes_stream();
        let out = crate::transport::rest::sse_json_stream(byte_stream).map(|item| {
            let v: Value = item?;
            let decoded: JsonRpcResponse<AduibRpcResponse> = serde_json::from_value(v)?;
            match decoded {
                JsonRpcResponse::Success(s) => {
                    if !s.result.is_success() {
                        Err(AduibRpcClientError::Remote(RemoteError(
                            s.result.error.unwrap_or(crate::types::AduibRpcError {
                                code: -1,
                                message: "unknown error".to_string(),
                                data: Some(json!({"status": s.result.status})),
                            }),
                        )))
                    } else {
                        Ok(s.result)
                    }
                }
                JsonRpcResponse::Error(e) => Err(AduibRpcClientError::Remote(RemoteError(e.error))),
            }
        });

        Ok(Box::pin(out))
    }
}

fn uuid_like() -> String {
    // Avoid an extra dependency; a unique-enough value for client-side correlation.
    format!("{}", std::time::SystemTime::now().duration_since(std::time::UNIX_EPOCH).unwrap().as_nanos())
}
