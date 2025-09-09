namespace py src.aduib_rpc.proto

struct RpcError {
    1: map<string, string> data,
    2: string message,
    3: string code
}

struct RpcTask {
    1: string id,
    2: string method
    4: string meta,
    5: binary data
}

struct RpcTaskResponse {
    1: string id,
    2: string status,
    3: binary result,
    4: optional RpcError error
}

union RpcTaskStream {
    1: RpcTask task,
    2: RpcTaskResponse task_response
}

service AduibRpcService {
    RpcTaskResponse completion(1: RpcTask task),
}
