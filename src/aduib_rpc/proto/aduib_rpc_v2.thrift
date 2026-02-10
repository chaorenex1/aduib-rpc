// Thrift v2 wire definition for Aduib RPC.
//
// This file mirrors src/aduib_rpc/proto/aduib_rpc_v2.proto.
// Notes:
// - google.protobuf.Struct/Value are represented as JSON strings.
// - Thrift has no streaming; stream RPCs are modeled with list inputs/outputs.

namespace py aduib_rpc.thrift_v2

typedef map<string, string> StringMap

enum ResponseStatus {
  RESPONSE_STATUS_UNSPECIFIED = 0,
  RESPONSE_STATUS_SUCCESS = 1,
  RESPONSE_STATUS_ERROR = 2,
  RESPONSE_STATUS_PARTIAL = 3,
}

enum AuthScheme {
  AUTH_SCHEME_UNSPECIFIED = 0,
  AUTH_SCHEME_BEARER = 1,
  AUTH_SCHEME_API_KEY = 2,
  AUTH_SCHEME_MTLS = 3,
}

enum ContentType {
  CONTENT_TYPE_UNSPECIFIED = 0,
  CONTENT_TYPE_JSON = 1,
  CONTENT_TYPE_MSGPACK = 2,
  CONTENT_TYPE_PROTOBUF = 3,
  CONTENT_TYPE_AVRO = 4,
}

enum Compression {
  COMPRESSION_UNSPECIFIED = 0,
  COMPRESSION_NONE = 1,
  COMPRESSION_GZIP = 2,
  COMPRESSION_ZSTD = 3,
  COMPRESSION_LZ4 = 4,
}

enum Priority {
  PRIORITY_UNSPECIFIED = 0,
  PRIORITY_LOW = 1,
  PRIORITY_NORMAL = 2,
  PRIORITY_HIGH = 3,
  PRIORITY_CRITICAL = 4,
}

enum HealthStatus {
  HEALTH_STATUS_UNSPECIFIED = 0,
  HEALTH_STATUS_HEALTHY = 1,
  HEALTH_STATUS_UNHEALTHY = 2,
  HEALTH_STATUS_DEGRADED = 3,
  HEALTH_STATUS_UNKNOWN = 4,
}

enum TaskStatus {
  TASK_STATUS_UNSPECIFIED = 0,
  TASK_STATUS_PENDING = 1,
  TASK_STATUS_SCHEDULED = 2,
  TASK_STATUS_RUNNING = 3,
  TASK_STATUS_SUCCEEDED = 4,
  TASK_STATUS_FAILED = 5,
  TASK_STATUS_CANCELED = 6,
  TASK_STATUS_RETRYING = 7,
}

struct TraceContext {
  1: string trace_id,
  2: string span_id,
  3: optional string parent_span_id,
  4: bool sampled,
  5: StringMap baggage,
}

struct ErrorDetail {
  1: string type,
  2: optional string field,
  3: string reason,
  4: StringMap metadata,
}

struct DebugInfo {
  1: optional string stack_trace,
  2: optional string internal_message,
  3: i64 timestamp_ms,
}

struct RpcError {
  1: i32 code,
  2: string name,
  3: string message,
  4: list<ErrorDetail> details,
  5: optional DebugInfo debug,
}

struct AuthContext {
  1: AuthScheme scheme,
  2: optional string credentials,
  3: optional string principal,
  4: list<string> roles,
}

struct Pagination {
  1: i64 total,
  2: i32 page,
  3: i32 page_size,
  4: bool has_next,
  5: optional string cursor,
}

struct RateLimitInfo {
  1: i32 limit,
  2: i32 remaining,
  3: i64 reset_at_ms,
}

struct RequestMetadata {
  1: i64 timestamp_ms,
  2: optional string client_id,
  3: optional string client_version,
  4: optional AuthContext auth,
  5: optional string tenant_id,
  6: ContentType content_type,
  7: list<ContentType> accept,
  8: optional Compression compression,
  9: StringMap headers,
  10: optional bool long_task,
  11: optional string long_task_method
  12: optional i32 long_task_timeout
}

struct ResponseMetadata {
  1: i64 timestamp_ms,
  2: i64 duration_ms,
  3: optional string server_id,
  4: optional string server_version,
  5: optional Pagination pagination,
  6: optional RateLimitInfo rate_limit,
  7: StringMap headers,
}

struct RetryConfig {
  1: i32 max_attempts,
  2: i64 initial_delay_ms,
  3: i64 max_delay_ms,
  4: double backoff_multiplier,
  5: list<i32> retryable_codes,
}

struct QosConfig {
  1: Priority priority,
  2: optional i64 timeout_ms,
  3: optional RetryConfig retry,
  4: optional string idempotency_key,
}

struct Request {
  1: string aduib_rpc,
  2: string id,
  3: string method,
  4: optional string name,
  // JSON-encoded google.protobuf.Struct
  5: string data_json,
  6: optional TraceContext trace_context,
  7: optional RequestMetadata metadata,
  8: optional QosConfig qos,
}

union ResponsePayload {
  // JSON-encoded google.protobuf.Value
  1: string result_json,
  2: RpcError error,
}

struct Response {
  1: string aduib_rpc,
  2: string id,
  3: ResponseStatus status,
  4: optional ResponsePayload payload,
  5: optional TraceContext trace_context,
  6: optional ResponseMetadata metadata,
}

struct TaskRecord {
  1: string task_id,
  2: optional string parent_task_id,
  3: TaskStatus status,
  4: Priority priority,
  5: i64 created_at_ms,
  6: optional i64 scheduled_at_ms,
  7: optional i64 started_at_ms,
  8: optional i64 completed_at_ms,
  9: i32 attempt,
  10: i32 max_attempts,
  11: optional i64 next_retry_at_ms,
  // JSON-encoded google.protobuf.Value
  12: optional string result,
  13: optional RpcError error,
  14: optional TaskProgress progress,
  15: StringMap metadata,
  16: list<string> tags,
}

struct TaskProgress {
  1: i64 current,
  2: i64 total,
  3: optional string message,
  4: optional double percentage,
}

struct TaskSubmitRequest {
  1: string target_method,
  // JSON-encoded google.protobuf.Struct
  2: optional string params_json,
  3: Priority priority,
  4: i32 max_attempts,
  5: optional i64 timeout_ms,
  6: optional i64 scheduled_at_ms,
  7: optional string idempotency_key,
  8: StringMap metadata,
}

struct TaskSubmitResponse {
  1: string task_id,
  2: TaskStatus status,
  3: i64 created_at_ms,
}

struct TaskQueryRequest {
  1: string task_id,
}

struct TaskQueryResponse {
  1: TaskRecord task,
}

struct TaskCancelRequest {
  1: string task_id,
  2: optional string reason,
}

struct TaskCancelResponse {
  1: string task_id,
  2: TaskStatus status,
  3: bool canceled,
}

struct TaskSubscribeRequest {
  1: string task_id,
  2: list<string> events,
}

struct TaskEvent {
  1: string event,
  2: TaskRecord task,
  3: i64 timestamp_ms,
}

struct HealthCheckRequest {
  1: optional string service,
}

struct HealthCheckResponse {
  1: HealthStatus status,
  2: map<string, HealthStatus> services,
}

service AduibRpcService {
  // Unary
  Response Call(1: Request request),
  // Server-streaming (modeled as list in Thrift)
  list<Response> CallServerStream(1: Request request),
  // Client-streaming (modeled as list in Thrift)
  Response CallClientStream(1: list<Request> requests),
  // Bidirectional (modeled as lists in Thrift)
  list<Response> CallBidirectional(1: list<Request> requests),
}

service TaskService {
  TaskSubmitResponse Submit(1: TaskSubmitRequest request),
  TaskQueryResponse Query(1: TaskQueryRequest request),
  TaskCancelResponse Cancel(1: TaskCancelRequest request),
  // Server-streaming (modeled as list in Thrift)
  list<TaskEvent> Subscribe(1: TaskSubscribeRequest request),
}

service HealthService {
  HealthCheckResponse Check(1: HealthCheckRequest request),
  // Server-streaming (modeled as list in Thrift)
  list<HealthCheckResponse> Watch(1: HealthCheckRequest request),
}
