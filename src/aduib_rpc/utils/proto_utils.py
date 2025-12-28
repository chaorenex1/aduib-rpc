import json
from typing import Any

from google.protobuf.json_format import ParseDict, MessageToDict

from aduib_rpc.grpc import aduib_rpc_pb2
from aduib_rpc.types import AduibRpcRequest, AduibRpcResponse, AduibRPCError
from aduib_rpc.utils.encoders import jsonable_encoder
from aduib_rpc.utils.serialization import JsonSerializer, serializer_from_meta


class FromProto:
    """Utility class for converting protobuf messages to native Python types."""

    @classmethod
    def rpc_request(cls, request: aduib_rpc_pb2.RpcTask) -> AduibRpcRequest:
        request_dict = MessageToDict(request)
        rpc_request = AduibRpcRequest(id=request.id, method=request.method)
        rpc_request.meta = json.loads(request_dict['meta']) if request.meta else {}

        serializer = serializer_from_meta(rpc_request.meta, default=JsonSerializer())
        rpc_request.data = serializer.loads(request.data)
        return rpc_request

    @classmethod
    def rpc_response(cls, response: aduib_rpc_pb2.RpcTaskResponse) -> AduibRpcResponse:
        rpc_response = AduibRpcResponse(id=response.id, status=response.status)
        if not rpc_response.is_success():
            rpc_response.error = AduibRPCError(**MessageToDict(response.error))
        else:
            # There's no meta on response itself; default safe JSON.
            serializer = JsonSerializer()
            rpc_response.result = serializer.loads(response.result)
        return rpc_response


class ToProto:
    """Utility class for converting native Python types to protobuf messages."""

    @classmethod
    def rpc_response(cls, response: AduibRpcResponse) -> aduib_rpc_pb2.RpcTaskResponse:
        rpc_response = aduib_rpc_pb2.RpcTaskResponse(id=response.id, status=response.status)
        if rpc_response.status == 'error':
            rpc_error = aduib_rpc_pb2.RpcError()
            err_dict = jsonable_encoder(response.error)
            # proto schema defines code as string
            if isinstance(err_dict, dict) and 'code' in err_dict and err_dict['code'] is not None:
                err_dict['code'] = str(err_dict['code'])
            ParseDict(err_dict, rpc_error)
            rpc_response.error.CopyFrom(rpc_error)
        else:
            # Response encoding uses safe JSON by default.
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


# NOTE: dict_to_struct was removed because it was unused in this project and
# caused noisy IDE type warnings with protobuf's dynamic Struct implementation.
