use crate::types::AduibRpcError;
use thiserror::Error;

#[derive(Debug, Clone)]
pub struct RemoteError(pub AduibRpcError);

#[derive(Debug, Error)]
pub enum AduibRpcClientError {
    #[error("http status {status}: {body}")]
    HttpStatus { status: u16, body: String },

    #[error("network error: {0}")]
    Network(#[from] reqwest::Error),

    #[error("json error: {0}")]
    Json(#[from] serde_json::Error),

    #[error("remote returned error: {0:?}")]
    Remote(RemoteError),

    #[error("streaming feature not enabled")]
    StreamingNotEnabled,
}

