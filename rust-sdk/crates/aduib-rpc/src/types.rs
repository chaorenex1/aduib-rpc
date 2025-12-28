use serde::{Deserialize, Serialize};
use serde_json::Value;

/// Canonical error shape used across transports.
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct AduibRpcError {
    pub code: i64,
    pub message: String,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub data: Option<Value>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct AduibRpcRequest {
    #[serde(default = "aduib_rpc_version")]
    pub aduib_rpc: String,
    pub method: String,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub data: Option<Value>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub meta: Option<Value>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub id: Option<Value>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct AduibRpcResponse {
    #[serde(default = "aduib_rpc_version")]
    pub aduib_rpc: String,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub result: Option<Value>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub error: Option<AduibRpcError>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub id: Option<Value>,
    #[serde(default = "default_success")]
    pub status: String,
}

impl AduibRpcResponse {
    pub fn is_success(&self) -> bool {
        self.status == "success" && self.error.is_none()
    }
}

fn aduib_rpc_version() -> String {
    "1.0".to_string()
}

fn default_success() -> String {
    "success".to_string()
}

/// JSON-RPC 2.0 request envelope.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct JsonRpcRequest<T> {
    pub jsonrpc: String,
    pub id: Value,
    pub method: String,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub params: Option<T>,
}

/// JSON-RPC 2.0 success response envelope.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct JsonRpcSuccessResponse<T> {
    pub jsonrpc: String,
    pub id: Option<Value>,
    pub result: T,
}

/// JSON-RPC 2.0 error response envelope.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct JsonRpcErrorResponse {
    pub jsonrpc: String,
    pub id: Option<Value>,
    pub error: AduibRpcError,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(untagged)]
pub enum JsonRpcResponse<T> {
    Success(JsonRpcSuccessResponse<T>),
    Error(JsonRpcErrorResponse),
}

