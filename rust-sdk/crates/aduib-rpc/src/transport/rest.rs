use async_trait::async_trait;
use serde_json::Value;

#[cfg(feature = "streaming")]
use bytes::Bytes;
#[cfg(feature = "streaming")]
use futures_core::Stream;
#[cfg(feature = "streaming")]
use futures_util::{StreamExt, TryStreamExt};
#[cfg(feature = "streaming")]
use std::pin::Pin;

use crate::error::AduibRpcClientError;
use crate::transport::Transport;
use crate::types::{AduibRpcRequest, AduibRpcResponse};

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
pub struct RestTransport {
    client: reqwest::Client,
    url: String,
}

impl RestTransport {
    pub fn new(client: reqwest::Client, base_url: String) -> Self {
        Self {
            client,
            url: normalize_base_url(base_url),
        }
    }
}

#[async_trait]
impl Transport for RestTransport {
    async fn completion(&self, request: AduibRpcRequest) -> Result<AduibRpcResponse, AduibRpcClientError> {
        // REST expects the RpcTask JSON (proto-json shape). We can build it from AduibRpcRequest.
        let rpc_task = crate::transport::rest::rest_task::to_rpc_task_json(&request)?;

        let resp = self
            .client
            .post(format!("{}/v1/message/completion", self.url))
            .json(&rpc_task)
            .send()
            .await?;

        let status = resp.status();
        let body = resp.text().await?;
        if !status.is_success() {
            return Err(AduibRpcClientError::HttpStatus {
                status: status.as_u16(),
                body,
            });
        }

        let v: Value = serde_json::from_str(&body)?;
        // Server returns RpcTaskResponse JSON (proto-json). Convert into AduibRpcResponse.
        crate::transport::rest::rest_task::from_rpc_task_response_json(v)
    }

    #[cfg(feature = "streaming")]
    async fn completion_stream(
        &self,
        request: AduibRpcRequest,
    ) -> Result<Pin<Box<dyn Stream<Item = Result<AduibRpcResponse, AduibRpcClientError>> + Send>>, AduibRpcClientError>
    {
        let rpc_task = crate::transport::rest::rest_task::to_rpc_task_json(&request)?;

        let resp = self
            .client
            .post(format!("{}/v1/message/completion/stream", self.url))
            .json(&rpc_task)
            .send()
            .await?;

        let status = resp.status();
        if !status.is_success() {
            let body = resp.text().await.unwrap_or_default();
            return Err(AduibRpcClientError::HttpStatus {
                status: status.as_u16(),
                body,
            });
        }

        let byte_stream = resp.bytes_stream();
        let out = sse_json_stream(byte_stream).map(|item| {
            let v = item?;
            crate::transport::rest::rest_task::from_rpc_task_response_json(v)
        });

        Ok(Box::pin(out))
    }
}

/// Parse a byte stream carrying SSE events, yielding each `data: <json>` payload as JSON.
///
/// Works for:
/// - REST streaming: each data is a JSON object (RpcTaskResponse proto-json)
/// - JSON-RPC streaming: each data is a JSON-RPC response object
#[cfg(feature = "streaming")]
pub(crate) fn sse_json_stream(
    byte_stream: impl Stream<Item = Result<Bytes, reqwest::Error>> + Send + 'static,
) -> impl Stream<Item = Result<Value, AduibRpcClientError>> + Send {
    use std::collections::VecDeque;

    // Convert reqwest error into our error on the stream.
    let byte_stream = byte_stream.map_err(AduibRpcClientError::Network);

    byte_stream.scan((Vec::<u8>::new(), VecDeque::<Result<Value, AduibRpcClientError>>::new()), |state, item| {
        let (buffer, queue) = state;

        // If we already have parsed events queued, flush one per poll.
        if let Some(next) = queue.pop_front() {
            return futures_util::future::ready(Some(next));
        }

        let chunk = match item {
            Ok(c) => c,
            Err(e) => return futures_util::future::ready(Some(Err(e))),
        };

        buffer.extend_from_slice(&chunk);

        // SSE events are separated by a blank line (\n\n). Extract as many complete events as possible.
        loop {
            let pos = memchr::memmem::find(buffer, b"\n\n");
            let Some(end) = pos else { break };
            let event_bytes: Vec<u8> = buffer.drain(..end + 2).collect();

            let s = String::from_utf8_lossy(&event_bytes);
            let mut data_lines = Vec::new();
            for line in s.lines() {
                let line = line.trim_end_matches('\r');
                if let Some(rest) = line.strip_prefix("data:") {
                    data_lines.push(rest.trim_start());
                }
            }
            if data_lines.is_empty() {
                continue;
            }

            let data = data_lines.join("\n");
            match serde_json::from_str::<Value>(&data) {
                Ok(v) => queue.push_back(Ok(v)),
                Err(e) => queue.push_back(Err(AduibRpcClientError::Json(e))),
            }
        }

        // After parsing, emit one item if available.
        futures_util::future::ready(queue.pop_front())
    })
}

// Non-stream builds don't need SSE helpers.
#[cfg(not(feature = "streaming"))]
pub(crate) fn sse_json_stream(_: ()) {}

pub(crate) mod rest_task {
    use base64::Engine;
    use serde_json::{json, Value};

    use crate::error::AduibRpcClientError;
    use crate::types::{AduibRpcError, AduibRpcRequest, AduibRpcResponse};

    /// Build the proto-json RpcTask body expected by RESTHandler.
    pub fn to_rpc_task_json(req: &AduibRpcRequest) -> Result<Value, AduibRpcClientError> {
        let id = req
            .id
            .clone()
            .and_then(|v| v.as_str().map(|s| s.to_string()))
            .unwrap_or_else(|| "".to_string());

        let meta_json = match &req.meta {
            Some(m) => serde_json::to_string(m)?,
            None => "{}".to_string(),
        };

        // Python ToProto.taskData encodes JSON -> bytes. RESTHandler uses Parse into bytes,
        // so here we send base64-encoded bytes per protobuf JSON mapping.
        // We encode the JSON value as UTF-8 bytes.
        let data_bytes = match &req.data {
            Some(v) => serde_json::to_vec(v)?,
            None => Vec::new(),
        };
        let data_b64 = base64::engine::general_purpose::STANDARD.encode(data_bytes);

        Ok(json!({
            "id": id,
            "method": req.method,
            "meta": meta_json,
            "data": data_b64,
        }))
    }

    /// Convert proto-json RpcTaskResponse into AduibRpcResponse.
    pub fn from_rpc_task_response_json(v: Value) -> Result<AduibRpcResponse, AduibRpcClientError> {
        let id = v.get("id").cloned();
        let status = v
            .get("status")
            .and_then(|s| s.as_str())
            .unwrap_or("success")
            .to_string();

        let result_b64 = v.get("result").and_then(|r| r.as_str()).unwrap_or("");
        let result_bytes = if result_b64.is_empty() {
            Vec::new()
        } else {
            base64::engine::general_purpose::STANDARD
                .decode(result_b64)
                .map_err(|e| AduibRpcClientError::HttpStatus {
                    status: 500,
                    body: format!("invalid base64 result: {e}"),
                })?
        };

        let result = if result_bytes.is_empty() {
            None
        } else {
            Some(serde_json::from_slice::<Value>(&result_bytes)?)
        };

        let error = if let Some(err) = v.get("error") {
            // proto-json: error.code is string in proto. We'll parse to i64 when possible.
            let code = err
                .get("code")
                .and_then(|c| c.as_str())
                .and_then(|s| s.parse::<i64>().ok())
                .unwrap_or(-1);
            let message = err
                .get("message")
                .and_then(|m| m.as_str())
                .unwrap_or("")
                .to_string();
            let data = err.get("data").cloned();
            Some(AduibRpcError { code, message, data })
        } else {
            None
        };

        Ok(AduibRpcResponse {
            aduib_rpc: "1.0".to_string(),
            result,
            error,
            id,
            status,
        })
    }
}
