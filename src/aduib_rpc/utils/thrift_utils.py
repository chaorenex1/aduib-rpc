import json
from typing import Any

from aduib_rpc.thrift.ttypes import RpcTask, RpcTaskResponse, RpcError
from aduib_rpc.types import AduibRpcRequest, AduibRpcResponse, AduibRPCError
from aduib_rpc.utils.encoders import jsonable_encoder
from aduib_rpc.utils.serialization import JsonSerializer, serializer_from_meta


class FromProto:
    """Utility class for converting protobuf messages to native Python types."""

    @classmethod
    def rpc_request(cls, request: RpcTask) -> AduibRpcRequest:
        rpc_request = AduibRpcRequest(id=request.id, method=request.method)
        rpc_request.meta = json.loads(request.meta) if request.meta else {}
        serializer = serializer_from_meta(rpc_request.meta, default=JsonSerializer())
        rpc_request.data = serializer.loads(request.data)
        return rpc_request

    @classmethod
    def rpc_response(cls, response: RpcTaskResponse) -> AduibRpcResponse:
        rpc_response = AduibRpcResponse(id=response.id, status=response.status)
        if not rpc_response.is_success():
            rpc_response.error = AduibRPCError(**jsonable_encoder(obj=response.error))
        else:
            serializer = JsonSerializer()
            rpc_response.result = serializer.loads(response.result)
        return rpc_response


class ToProto:
    """Utility class for converting native Python types to protobuf messages."""

    @classmethod
    def rpc_response(cls, response: AduibRpcResponse) -> RpcTaskResponse:
        rpc_response = RpcTaskResponse(id=response.id, status=response.status)
        if rpc_response.status == 'error':
            rpc_error = RpcError(**jsonable_encoder(response.error))
            rpc_response.error = rpc_error
        else:
            serializer = JsonSerializer()
            rpc_response.result = serializer.dumps(response.result)
        return rpc_response

    @classmethod
    def metadata(cls, metadata: dict[str, Any]):
        if not metadata:
            return None
        return json.dumps(obj=metadata)

    @classmethod
    def taskData(cls, data: Any, meta: dict[str, Any] | None = None) -> bytes:
        serializer = serializer_from_meta(meta, default=JsonSerializer())
        return serializer.dumps(data)
