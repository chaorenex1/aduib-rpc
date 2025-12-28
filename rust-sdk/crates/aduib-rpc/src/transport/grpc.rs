use async_trait::async_trait;
use serde_json::Value;

#[cfg(feature = "streaming")]
use std::pin::Pin;

use crate::error::{AduibRpcClientError, RemoteError};
use crate::transport::Transport;
use crate::types::{AduibRpcError, AduibRpcRequest, AduibRpcResponse};

use crate::grpc::pb;

fn normalize_grpc_endpoint(base: String) -> String {
    // Accept "127.0.0.1:50051" or "http://127.0.0.1:50051".
    if base.starts_with("http://") || base.starts_with("https://") {
        base
    } else {
        format!("http://{base}")
    }
}

#[derive(Clone)]
pub struct GrpcTransport {
    endpoint: String,
}

impl GrpcTransport {
    pub fn new(base_url: String) -> Self {
        Self {
            endpoint: normalize_grpc_endpoint(base_url),
        }
    }

    async fn connect(&self) -> Result<pb::aduib_rpc_service_client::AduibRpcServiceClient<tonic::transport::Channel>, AduibRpcClientError> {
        let channel = tonic::transport::Channel::from_shared(self.endpoint.clone())
            .map_err(|e| AduibRpcClientError::HttpStatus { status: 400, body: format!("invalid grpc endpoint: {e}") })?
            .connect()
            .await
            .map_err(|e| AduibRpcClientError::HttpStatus { status: 503, body: format!("grpc connect failed: {e}") })?;
        Ok(pb::aduib_rpc_service_client::AduibRpcServiceClient::new(channel))
    }
}

#[async_trait]
impl Transport for GrpcTransport {
    async fn completion(&self, request: AduibRpcRequest) -> Result<AduibRpcResponse, AduibRpcClientError> {
        let mut client = self.connect().await?;

        let task = to_rpc_task(&request)?;
        let resp = client
            .completion(tonic::Request::new(task))
            .await
            .map_err(|e| AduibRpcClientError::HttpStatus {
                status: tonic_code_to_status(&e),
                body: e.to_string(),
            })?
            .into_inner();

        from_rpc_task_response(resp)
    }

    #[cfg(feature = "streaming")]
    async fn completion_stream(
        &self,
        request: AduibRpcRequest,
    ) -> Result<Pin<Box<dyn futures_core::Stream<Item = Result<AduibRpcResponse, AduibRpcClientError>> + Send>>, AduibRpcClientError>
    {
        use futures_util::StreamExt;

        let mut client = self.connect().await?;
        let task = to_rpc_task(&request)?;

        let stream = client
            .stream_completion(tonic::Request::new(task))
            .await
            .map_err(|e| AduibRpcClientError::HttpStatus {
                status: tonic_code_to_status(&e),
                body: e.to_string(),
            })?
            .into_inner();

        let out = stream.map(|item| {
            let resp = item.map_err(|e| AduibRpcClientError::HttpStatus {
                status: tonic_code_to_status(&e),
                body: e.to_string(),
            })?;
            from_rpc_task_response(resp)
        });

        Ok(Box::pin(out))
    }
}

fn tonic_code_to_status(e: &tonic::Status) -> u16 {
    match e.code() {
        tonic::Code::Ok => 200,
        tonic::Code::InvalidArgument => 400,
        tonic::Code::NotFound => 404,
        tonic::Code::DeadlineExceeded => 408,
        tonic::Code::Unauthenticated => 401,
        tonic::Code::PermissionDenied => 403,
        tonic::Code::Unavailable => 503,
        _ => 500,
    }
}

fn to_rpc_task(req: &AduibRpcRequest) -> Result<pb::RpcTask, AduibRpcClientError> {
    let id = req
        .id
        .clone()
        .and_then(|v| v.as_str().map(|s| s.to_string()))
        .unwrap_or_else(|| "".to_string());

    let meta = match &req.meta {
        Some(m) => serde_json::to_string(m)?,
        None => "{}".to_string(),
    };

    let data = match &req.data {
        Some(v) => serde_json::to_vec(v)?,
        None => Vec::new(),
    };

    Ok(pb::RpcTask {
        id,
        method: req.method.clone(),
        meta,
        data,
    })
}

fn from_rpc_task_response(resp: pb::RpcTaskResponse) -> Result<AduibRpcResponse, AduibRpcClientError> {
    let result = if resp.result.is_empty() {
        None
    } else {
        Some(serde_json::from_slice::<Value>(&resp.result)?)
    };

    let error = resp.error.map(|e| {
        let code = e.code.parse::<i64>().unwrap_or(-1);
        let data = e.data.map(|s| prost_struct_to_json(&s));
        AduibRpcError {
            code,
            message: e.message,
            data,
        }
    });

    let status = if error.is_some() {
        "error".to_string()
    } else if resp.status.is_empty() {
        "success".to_string()
    } else {
        resp.status
    };

    let out = AduibRpcResponse {
        aduib_rpc: "1.0".to_string(),
        result,
        error,
        id: Some(Value::String(resp.id)),
        status,
    };

    if !out.is_success() {
        return Err(AduibRpcClientError::Remote(RemoteError(
            out.error.clone().unwrap_or(AduibRpcError {
                code: -1,
                message: "unknown error".to_string(),
                data: None,
            }),
        )));
    }

    Ok(out)
}

fn prost_struct_to_json(s: &prost_types::Struct) -> Value {
    let mut map = serde_json::Map::new();
    for (k, v) in &s.fields {
        map.insert(k.clone(), prost_value_to_json(v));
    }
    Value::Object(map)
}

fn prost_value_to_json(v: &prost_types::Value) -> Value {
    use prost_types::value::Kind;

    match &v.kind {
        None => Value::Null,
        Some(Kind::NullValue(_)) => Value::Null,
        Some(Kind::NumberValue(n)) => {
            serde_json::Number::from_f64(*n).map(Value::Number).unwrap_or(Value::Null)
        }
        Some(Kind::StringValue(s)) => Value::String(s.clone()),
        Some(Kind::BoolValue(b)) => Value::Bool(*b),
        Some(Kind::StructValue(st)) => prost_struct_to_json(st),
        Some(Kind::ListValue(list)) => {
            Value::Array(list.values.iter().map(prost_value_to_json).collect())
        }
    }
}
